"""
Text Parser Module
Intelligent parsing to extract specific fields and values from OCR results
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any

from fontTools.misc.cython import returns
from rapidfuzz import fuzz, process
from datetime import datetime

logger = logging.getLogger(__name__)


class TextParser:
    """
    Intelligent text parser for extracting structured metadata from OCR results
    """

    def __init__(self, config: Dict):
        """
        Initialize text parser with configuration

        Args:
            config: Configuration dictionary containing parsing settings
        """
        self.config = config
        self.parsing_config = config.get('parsing', {})
        # Validation rules
        self.REQUIRED_FIELDS = {
            'nosert',
            'jenis_sert',
            'noreg',
            'nmkpl'
        }

        self.OPTIONAL_FIELDS = {
            'jenis_survey',
            'tgl_sert',
            'divisi',
            'tgl_survey1',
            'tgl_survey2',
            'tgl_berlaku',
            'mem01'
        }

        # Certificate type mapping
        self.cert_type_mapping = self.parsing_config.get('certificate_type_mapping', {})

        # Templates configuration
        self.templates = self.parsing_config.get('templates', {})

        # Legacy support: if no templates, use fields directly
        self.fields_config = self.parsing_config.get('fields', {})

        self.confidence_threshold = self.parsing_config.get('confidence_threshold', 0.5)
        self.use_fuzzy_matching = self.parsing_config.get('use_fuzzy_matching', True)
        self.fuzzy_threshold = self.parsing_config.get('fuzzy_threshold', 80)

        # Current templates being used
        self.current_template = None
        self.current_template_name = None

        if self.templates:
            logger.info(f"Text Parser initialized with {len(self.templates)} templates")
        else:
            logger.info(f"Text Parser initialized with {len(self.fields_config)} field definitions")

    def parse(self, ocr_result: Dict) -> Dict:
        self.global_full_text = ocr_result.get("full_text", "")
        pages = ocr_result.get("pages", [])

        # === SINGLE CERT FALLBACK ===
        if not pages:
            metadata = self._parse_single_certificate(ocr_result)
            return {
                "multiple_certificates": False,
                "count": 1,
                "certificates": [metadata]
            }

        certificate_groups = []
        current_group = None

        def detect_cert_type(page_text: str) -> Optional[str]:
            t = page_text.lower()
            if "sertifikat klasifikasi lambung" in t:
                return "lambung"
            if "sertifikat klasifikasi mesin" in t:
                return "mesin"
            if "sertifikat nasional garis muat" in t or "national load line certificate" in t:
                return "muat"
            return None

        # === STEP 1: GROUP HALAMAN ===
        for page in pages:
            page_text = page.get("text", "")
            cert_type = detect_cert_type(page_text)

            if cert_type:
                current_group = {
                    "type": cert_type,
                    "pages": [page]
                }
                certificate_groups.append(current_group)
            elif current_group:
                current_group["pages"].append(page)

        # fallback kalau gagal detect
        if not certificate_groups:
            metadata = self._parse_single_certificate(ocr_result)
            return {
                "multiple_certificates": False,
                "count": 1,
                "certificates": [metadata]
            }

        # === STEP 2: PARSE PER SERTIFIKAT ===
        results = []

        for group in certificate_groups:
            combined_text = self._build_cert_text(group["pages"])

            cert_ocr = {
                "full_text": combined_text,
                "lines": [],
                "words": []
            }

            metadata = self._parse_single_certificate(cert_ocr)
            if isinstance(metadata, tuple):
                metadata = metadata[0]

            metadata["certificate_type"] = group["type"]
            metadata["page_range"] = [
                group["pages"][0]["page_number"],
                group["pages"][-1]["page_number"]
            ]

            results.append(metadata)

        # === STEP 3: REUSE LOKASI SURVEY DARI HULL / MACH UNTUK MUAT ===
        shared_lokasi = None

        # Ambil lokasi referensi dari HULL atau MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                raw_lokasi = meta["extracted_fields"].get("lokasi_survey")
                clean_lokasi = self._normalize_lokasi_survey(raw_lokasi)
                if clean_lokasi:
                    shared_lokasi = clean_lokasi
                    break

        # Terapkan ke MUAT
        if shared_lokasi:
            for meta in results:
                if meta.get("certificate_type") == "muat":
                    meta["extracted_fields"]["lokasi_survey"] = shared_lokasi
                    meta["confidence_scores"]["lokasi_survey"] = 0.95
                    meta["extraction_status"]["lokasi_survey"] = "SUCCESS"
                    logger.info(f"Reused lokasi_survey for MUAT: {shared_lokasi}")

        # ======================================================
        # STEP 4: REUSE TGL_SURVEY2 DARI HULL / MACH KE MUAT
        # ======================================================
        shared_survey2 = None

        # Ambil TGL_SURVEY2 dari HULL atau MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                val = meta["extracted_fields"].get("tgl_survey2")
                if val and val != "NOT FOUND":
                    shared_survey2 = val
                    break

        # Terapkan ke MUAT
        if shared_survey2:
            for meta in results:
                if meta.get("certificate_type") == "muat":
                    # BIARKAN tgl_survey1 NULL
                    meta["extracted_fields"]["tgl_survey1"] = "NOT FOUND"
                    meta["confidence_scores"]["tgl_survey1"] = 0.0
                    meta["extraction_status"]["tgl_survey1"] = "NOT_FOUND"

                    # REUSE ke tgl_survey2
                    meta["extracted_fields"]["tgl_survey2"] = shared_survey2
                    meta["confidence_scores"]["tgl_survey2"] = 0.95
                    meta["extraction_status"]["tgl_survey2"] = "SUCCESS"

                    logger.info(
                        f"Reused TGL_SURVEY2 for MUAT from HULL/MACH: {shared_survey2}"
                    )

        # ======================================================
        # STEP 5: REUSE TGL_BERLAKU DARI HULL / MACH KE MUAT
        # ======================================================
        shared_berlaku = None

        # Ambil tgl_berlaku dari HULL atau MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                val = meta["extracted_fields"].get("tgl_berlaku")
                if val and val != "NOT FOUND":
                    shared_berlaku = val
                    break

        # Terapkan ke MUAT
        if shared_berlaku:
            for meta in results:
                if meta.get("certificate_type") == "muat":
                    meta["extracted_fields"]["tgl_berlaku"] = shared_berlaku
                    meta["confidence_scores"]["tgl_berlaku"] = 0.95
                    meta["extraction_status"]["tgl_berlaku"] = "SUCCESS"

                    logger.info(
                        f"Reused TGL_BERLAKU for MUAT from HULL/MACH: {shared_berlaku}"
                    )

        # ======================================================
        # STEP 6: REUSE DIVISI DARI HULL / MACH KE MUAT
        # ======================================================
        shared_divisi = None

        # Ambil DIVISI referensi dari HULL atau MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                val = meta["extracted_fields"].get("divisi")
                if val and val != "NOT FOUND":
                    shared_divisi = val
                    break

        # Terapkan ke MUAT jika kosong
        if shared_divisi:
            for meta in results:
                if meta.get("certificate_type") == "muat":
                    current_val = meta["extracted_fields"].get("divisi")
                    if not current_val or current_val == "NOT FOUND":
                        meta["extracted_fields"]["divisi"] = shared_divisi
                        meta["confidence_scores"]["divisi"] = 0.80
                        meta["extraction_status"]["divisi"] = "SUCCESS"

                        logger.info(
                            f"Reused DIVISI for MUAT from HULL/MACH: {shared_divisi}"
                        )

        # ======================================================
        # STEP 7: REUSE NMKPL DARI HULL / MACH KE MUAT (PM39 & ILLC)
        # ======================================================
        shared_nmkpl = None

        # Ambil NMKPL paling valid dari HULL / MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                val = meta["extracted_fields"].get("nmkpl")
                if self._is_valid_nmkpl(val):
                    shared_nmkpl = val
                    break

        # Terapkan ke MUAT (PM39 & ILLC P88)
        if shared_nmkpl:
            for meta in results:
                if meta.get("certificate_type") == "muat":
                    cur = meta["extracted_fields"].get("nmkpl")

                    if not self._is_valid_nmkpl(cur):
                        meta["extracted_fields"]["nmkpl"] = shared_nmkpl
                        meta["confidence_scores"]["nmkpl"] = 0.85
                        meta["extraction_status"]["nmkpl"] = "SUCCESS"

                        logger.info(
                            f"Reused NMKPL for MUAT from HULL/MACH: {shared_nmkpl}"
                        )

        # ==========================
        # REUSE CALL & TGL_LASTDOK (MEM01 ONLY)
        # ==========================
        shared_call = None
        shared_nmkpl = None
        shared_tgl_lastdok = None

        for meta in results:
            if meta["certificate_type"] == "muat":
                shared_call = meta["extracted_fields"].get("call")

            if meta["certificate_type"] in ("lambung", "mesin"):
                shared_tgl_lastdok = meta["extracted_fields"].get("tgl_survey2")
                shared_nmkpl = meta["extracted_fields"].get("nmkpl")

        for meta in results:
            if meta["certificate_type"] == "lambung":

                # reuse CALL (boleh jadi null)
                if shared_call:
                    meta["extracted_fields"]["call"] = shared_call

                # ⬇⬇⬇ MASUK KE MEM01 SAJA ⬇⬇⬇
                if shared_tgl_lastdok:
                    mem01_val = meta["extracted_fields"].get("mem01")

                    if mem01_val:
                        meta["extracted_fields"]["mem01"] = (
                            f"{mem01_val}, Dok Terakhir: {shared_tgl_lastdok}"
                        )

        return {
            "multiple_certificates": True,
            "count": len(results),
            "certificates": results
        }

    def _build_cert_text(self, pages: List[Dict]) -> str:
        """
        Build clean certificate text from page range
        (SOLUSI #4: page-aware parsing)
        """
        texts = []
        for p in pages:
            txt = p.get("text", "")
            if txt:
                texts.append(txt.strip())
        return "\n".join(texts)

    def _parse_single_certificate(self, ocr_result: Dict) -> Dict:
        """
        Parse a single certificate from OCR result
        """
        metadata = {
            'extracted_fields': {},
            'raw_text': ocr_result.get('full_text', ''),
            'confidence_scores': {},
            'extraction_status': {},
            'template_used': None
        }

        # OCR content
        lines = self._get_text_lines(ocr_result)
        full_text = ocr_result.get('full_text', '')
        shared_noreg = self._extract_shared_noreg(self.global_full_text)

        # =========================
        # TEMPLATE DETECTION
        # =========================
        if self.templates:
            template_name = self._detect_template(full_text)
            if template_name:
                self.current_template_name = template_name
                self.current_template = self.templates[template_name]
                self.fields_config = self.current_template.get('fields', {})
                metadata['template_used'] = template_name
                logger.info(f"Using templates: {template_name}")
            else:
                template_name = list(self.templates.keys())[0]
                self.current_template_name = template_name
                self.current_template = self.templates[template_name]
                self.fields_config = self.current_template.get('fields', {})
                metadata['template_used'] = template_name
                logger.warning(f"No templates detected, using default: {template_name}")

        # =========================
        # FIELD EXTRACTION
        # =========================
        for field_name, field_config in self.fields_config.items():
            logger.debug(f"Extracting field: {field_name}")

            extracted_value, confidence = self._extract_field(
                field_name,
                field_config,
                lines,
                ocr_result
            )

            # MAP JENIS SERT
            if field_name == 'jenis_sert' and field_config.get('map_to_code', False):
                extracted_value = self._map_certificate_type(extracted_value, full_text)

            # CLEAN NOSERT
            if field_name == 'nosert' and extracted_value:
                match = re.match(r'^(\d+)', str(extracted_value))
                if match:
                    extracted_value = match.group(1)
                    logger.info(f"Cleaned NOSERT: {extracted_value}")

            metadata['extracted_fields'][field_name] = extracted_value
            metadata['confidence_scores'][field_name] = confidence

            if field_config.get('required', False) and extracted_value is None:
                metadata['extraction_status'][field_name] = 'MISSING_REQUIRED'
            elif extracted_value is not None:
                metadata['extraction_status'][field_name] = 'SUCCESS'
            else:
                metadata['extraction_status'][field_name] = 'NOT_FOUND'

        # =========================
        # NORMALISASI LOKASI SURVEY
        # =========================
        raw_lokasi = metadata["extracted_fields"].get("lokasi_survey")
        clean_lokasi = self._normalize_lokasi_survey(raw_lokasi)

        if clean_lokasi:
            metadata["extracted_fields"]["lokasi_survey"] = clean_lokasi
            metadata["confidence_scores"]["lokasi_survey"] = 0.95
            metadata["extraction_status"]["lokasi_survey"] = "SUCCESS"

        # =========================
        # SHARED NOREG HANDLING
        # =========================
        if shared_noreg:
            if self.current_template_name == "template_muat":
                # MUAT HARUS REUSE NOREG
                metadata["extracted_fields"]["noreg"] = shared_noreg
                metadata["confidence_scores"]["noreg"] = 0.95
                metadata["extraction_status"]["noreg"] = "SUCCESS"
            else:
                if metadata["extracted_fields"].get("noreg") in [None, "NOT FOUND"]:
                    metadata["extracted_fields"]["noreg"] = shared_noreg
                    metadata["confidence_scores"]["noreg"] = 0.85
                    metadata["extraction_status"]["noreg"] = "SUCCESS"

        # =========================
        # ENSURE OPTIONAL FIELDS
        # =========================
        for field_name in self.OPTIONAL_FIELDS:
            if field_name not in metadata['extracted_fields']:
                metadata['extracted_fields'][field_name] = 'NOT FOUND'
                metadata['confidence_scores'][field_name] = 0.0
                metadata['extraction_status'][field_name] = 'MISSING_OPTIONAL'

        # =========================
        # QUALITY SCORE
        # =========================
        metadata['overall_quality'] = self._calculate_quality_score(metadata)

        return metadata

    def _extract_shared_noreg(self, full_text: str) -> Optional[str]:
        """
        Extract shared NOREG from full document text (robust OCR-safe)
        """

        patterns = [
            # No. Register : 10542
            r'No\.?\s*Register\s*[:\-]?\s*(\d{4,6})',

            # Nomor Register 10542
            r'Nomor\s+Register\s*[:\-]?\s*(\d{4,6})',

            # Register No 10542
            r'Register\s*No\.?\s*[:\-]?\s*(\d{4,6})',
        ]

        for pat in patterns:
            match = re.search(pat, full_text, re.IGNORECASE)
            if match:
                noreg = match.group(1)
                logger.info(f"[GLOBAL] Extracted shared NOREG: {noreg}")
                return noreg

        logger.warning("[GLOBAL] Shared NOREG not found in full document")
        return None

    def _split_certificates(self, full_text: str, ocr_result: Dict) -> List[Dict]:
        """
        Split document into multiple certificates if present

        Args:
            full_text: Full text from OCR
            ocr_result: Original OCR result

        Returns:
            List of certificate data dictionaries
        """
        certificates = []

        # Define certificate boundary patterns (more specific to avoid duplicates)
        cert_patterns = [
            (r'SERTIFIKAT LAMBUNG\s+CERTIFICATET? OF LAMBUNG\s+No\.', 'lambung'),
            (r'SERTIF[IT]KAT MESIN\s+Certificate of Machinery\s+No', 'mesin'),
            (r'SERTIFIKAT\s+NASIONAL\s+MUAT|NATIONAL\s+LOAD\s+CERTIFICATE', 'muat')
        ]

        # Find all certificate boundaries
        boundaries = []
        for pattern, cert_type in cert_patterns:
            matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
            for match in matches:
                # Check if this position is not too close to existing boundary (avoid duplicates)
                is_duplicate = False
                for existing in boundaries:
                    if abs(match.start() - existing['start']) < 50:  # Within 50 chars
                        is_duplicate = True
                        break

                if not is_duplicate:
                    boundaries.append({
                        'start': match.start(),
                        'type': cert_type,
                        'pattern': pattern
                    })

        # Sort boundaries by position
        boundaries.sort(key=lambda x: x['start'])

        if len(boundaries) <= 1:
            # Single certificate or no clear boundaries
            return [{'type': 'unknown', 'ocr_result': ocr_result}]

        # Split text into certificate sections
        for i, boundary in enumerate(boundaries):
            start_pos = boundary['start']
            end_pos = boundaries[i + 1]['start'] if i + 1 < len(boundaries) else len(full_text)

            # Extract certificate text
            cert_text = full_text[start_pos:end_pos]

            # Create new OCR result for this certificate
            cert_ocr_result = {
                'full_text': cert_text,
                'words': [],  # We'll filter words later if needed
                'lines': []
            }

            certificates.append({
                'type': boundary['type'],
                'ocr_result': cert_ocr_result
            })

        logger.info(f"Split document into {len(certificates)} certificates: {[c['type'] for c in certificates]}")
        return certificates

    def _detect_template(self, full_text: str) -> Optional[str]:
        """
        Detect which templates to use based on document content

        Args:
            full_text: Full text from OCR (lowercase)

        Returns:
            Template name or None
        """
        best_match = None
        best_score = 0

        for template_name, template_config in self.templates.items():
            keywords = template_config.get('detection_keywords', [])
            score = 0

            for keyword in keywords:
                if keyword.lower() in full_text:
                    score += 1

            # Prioritize template_muat if "muat" is found (to avoid confusion with lambung)
            if template_name == 'template_muat' and score > 0:
                score += 10  # Boost score for muat templates

            if score > best_score:
                best_score = score
                best_match = template_name

        return best_match if best_score > 0 else None

    def _map_certificate_type(self, raw_value: Optional[str], full_text: str) -> Optional[str]:
        """
        Map certificate type to standard code (HULL, MACH, PM39, ILLC P88)

        Args:
            raw_value: Raw extracted value
            full_text: Full text from OCR (lowercase)

        Returns:
            Mapped certificate code or original value
        """
        if not raw_value:
            return raw_value

        raw_lower = raw_value.lower()

        # Special handling for template_muat: check nasional vs internasional
        if self.current_template_name == 'template_muat':

            # ==========================
            # PRIORITY 1 — PM 39 (legal basis)
            # ==========================
            if re.search(r'PM\s*39', full_text, re.IGNORECASE):
                logger.info("Detected PM 39 regulation -> PM39")
                return 'PM39'

            # ==========================
            # PRIORITY 2 — Nasional wording
            # ==========================
            if 'garis muat nasional' in full_text.lower():
                logger.info("Detected: Garis Muat Nasional -> PM39")
                return 'PM39'

            # ==========================
            # PRIORITY 3 — Internasional
            # ==========================
            if (
                    'garis muat internasional' in full_text.lower()
                    or 'international load line' in full_text.lower()
                    or 'load line' in full_text.lower()
                    or 'plimsoll' in full_text.lower()
                    or 'il lc' in full_text.lower()
                    or 'illc' in full_text.lower()
            ):
                logger.info("Detected: International Load Line -> ILLC P88")
                return 'ILLC P88'

            # ==========================
            # FALLBACK (AMAN)
            # ==========================
            logger.info("Detected: Muat (fallback) -> PM39")
            return 'PM39'

        # For other templates, use mapping table
        for key, code in self.cert_type_mapping.items():
            if key.lower() in raw_lower or key.lower() in full_text:
                logger.info(f"Mapped '{raw_value}' -> '{code}'")
                return code

        # If no mapping found, return original value
        logger.debug(f"No mapping found for '{raw_value}', keeping original")
        return raw_value

    def _get_text_lines(self, ocr_result: Dict) -> List[Dict]:
        """
        Extract text lines with their metadata from OCR result

        Args:
            ocr_result: OCR result dictionary

        Returns:
            List of line dictionaries with text and metadata
        """
        lines = []

        # Extract from structured lines
        for line in ocr_result.get('lines', []):
            line_data = {
                'text': line.get('text', ''),
                'words': line.get('words', []),
                'geometry': line.get('geometry')
            }
            lines.append(line_data)

        # Also create lines from full text as fallback
        if not lines:
            full_text = ocr_result.get('full_text', '')
            for text_line in full_text.split('\n'):
                if text_line.strip():
                    lines.append({'text': text_line.strip(), 'words': [], 'geometry': None})

        return lines

    def _extract_field(self, field_name, field_config, lines, ocr_result):
        labels = field_config.get("labels", [])
        pattern = field_config.get("pattern")
        full_text = ocr_result.get("full_text", "")

        # ================= GLOBAL FALLBACK =================

        # NOREG
        if field_name == "noreg":
            m = re.search(r'(No\.?\s*Register|Register\s*No)[^\d]*(\d{3,6})', full_text, re.IGNORECASE)
            if m:
                return m.group(2), 0.95

        # NOSERT
        if field_name == "nosert":
            m = re.search(r'No\.?\s*[^\d]*(\d{3,7})', full_text, re.IGNORECASE)
            if m:
                return m.group(1), 0.9

        # JENIS_SURVEY
        if field_name == "jenis_survey":
            return self._extract_jenis_survey(full_text, lines)

        # NMKPL
        if field_name == "nmkpl":
            value, confidence = self._extract_nmkpl(full_text, lines)

            value = self._normalize_nmkpl(value)

            return value, confidence

        # TGL SERTIFIKAT
        if field_name == "tgl_sert":
            return self._extract_tgl_sert(full_text, lines)

        # LOKASI SURVEY
        if field_name == "lokasi_survey":
            m = re.search(r'di\s+([A-Z\s&]{3,40})', full_text)
            if m:
                return m.group(1).strip(), 0.9

        # DIVISI / SURVEYOR
        if field_name == "divisi":
            return self._extract_surveyor(full_text, lines)

        # MEM01
        if field_name == "mem01":
            return self._extract_mem01(full_text, lines)

        # TGL SURVEY
        if field_name == "tgl_survey1":
            return self._extract_survey_date1(full_text, lines)

        if field_name == "tgl_survey2":
            return self._extract_survey_date2(full_text, lines)

        # TGL BERLAKU
        if field_name == "tgl_berlaku":
            return self._extract_valid_date(full_text, lines)

        # ================= LABEL-BASED =================
        value_label, conf_label = self._extract_by_label(labels, lines, pattern)
        if value_label:
            return value_label, conf_label

        if labels and pattern:
            for i, line in enumerate(lines):
                for label in labels:
                    if label.lower() in line["text"].lower():
                        window = " ".join(l["text"] for l in lines[i:i + 3])
                        val = self._search_pattern(pattern, window)
                        if val:
                            return val, 0.75

        if pattern:
            val = self._search_pattern(pattern, full_text)
            if val:
                return val, 0.7

        if field_name in ["tgl_berlaku", "tgl_sert"]:
            guess = self._guess_date(full_text)
            if guess:
                return guess, 0.6

        if field_name in ["nosert", "noreg"]:
            guess = self._guess_number(full_text)
            if guess:
                return guess, 0.55

        return None, 0.0

    def _search_pattern(self, pattern, text: str):
        if not pattern or not text:
            return None

        patterns = pattern if isinstance(pattern, list) else [pattern]

        for pat in patterns:
            try:
                match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
                if match:
                    if match.lastindex and match.lastindex >= 1:
                        return match.group(1).strip()
                    else:
                        # fallback → seluruh match
                        return match.group(0).strip()
            except re.error:
                continue

        return None

    def _guess_date(self, text: str):
        patterns = [
            r'(\d{1,2}\s+(JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|SEPTEMBER|OKTOBER|NOVEMBER|DESEMBER)\s+\d{4})',
            r'(\d{1,2}\s+[A-Z]{3,9}\s+\d{4})',
            r'(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4})'
        ]

        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _guess_number(self, text: str):
        matches = re.findall(r'\b\d{4,7}\b', text)
        if matches:
            # ambil angka yang paling sering muncul
            return max(set(matches), key=matches.count)
        return None

    def _extract_by_label(self, labels: List[str], lines: List[Dict],
                         pattern: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Extract value by finding label and getting nearby text

        Args:
            labels: List of possible label names
            lines: List of text lines
            pattern: Optional regex pattern to validate value

        Returns:
            Tuple of (extracted_value, confidence_score)
        """
        if not labels:
            return None, 0.0

        best_match = None
        best_confidence = 0.0

        for line_idx, line in enumerate(lines):
            line_text = line['text']

            # Check each possible label
            for label in labels:
                # Skip very short labels (1-2 chars) unless exact word match
                if len(label) <= 2:
                    # For short labels, require word boundary
                    pattern_word = r'\b' + re.escape(label) + r'\b'
                    if not re.search(pattern_word, line_text, re.IGNORECASE):
                        continue

                # Exact match
                if label.lower() in line_text.lower():
                    # Try to extract from same line
                    value, conf = self._extract_value_from_line(line_text, label, pattern)

                    # If no value on same line, try next line
                    if (value is None or conf < 0.5) and line_idx + 1 < len(lines):
                        next_line = lines[line_idx + 1]['text']
                        value_next, conf_next = self._extract_value_from_next_line(next_line, pattern)
                        if conf_next > conf:
                            value, conf = value_next, conf_next * 0.9  # Slightly lower confidence

                    if conf > best_confidence:
                        best_match = value
                        best_confidence = conf

                # Fuzzy match (only for longer labels)
                elif self.use_fuzzy_matching and len(label) > 3:
                    ratio = fuzz.partial_ratio(label.lower(), line_text.lower())
                    if ratio >= self.fuzzy_threshold:
                        value, conf = self._extract_value_from_line(line_text, label, pattern)

                        # Try next line if needed
                        if (value is None or conf < 0.5) and line_idx + 1 < len(lines):
                            next_line = lines[line_idx + 1]['text']
                            value_next, conf_next = self._extract_value_from_next_line(next_line, pattern)
                            if conf_next > conf:
                                value, conf = value_next, conf_next * 0.85

                        # Adjust confidence by fuzzy match ratio
                        conf = conf * (ratio / 100.0)
                        if conf > best_confidence:
                            best_match = value
                            best_confidence = conf

        return best_match, best_confidence

    def _extract_value_from_next_line(self, line_text: str,
                                      pattern: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Extract value from next line (when label and value are on different lines)

        Args:
            line_text: Text of the next line
            pattern: Optional regex pattern to validate value

        Returns:
            Tuple of (extracted_value, confidence_score)
        """
        if not line_text or not line_text.strip():
            return None, 0.0

        value_text = line_text.strip()

        # If pattern provided, try to match it
        if pattern:
            for pat in self._iter_patterns(pattern):
                match = re.search(pat, value_text, re.IGNORECASE)
                if match:
                    matched_value = match.group(0).strip()
                    matched_value = self._clean_extracted_value(matched_value)
                    return matched_value, 0.9

        # No pattern or no match - return the whole line (cleaned)
        # Split by common delimiters
        for delimiter in [',', ';', '\t', '  ']:
            if delimiter in value_text:
                value_text = value_text.split(delimiter)[0].strip()
                break

        # Limit to reasonable length
        words = value_text.split()
        if words:
            extracted = ' '.join(words[:10]).strip()
            extracted = self._clean_extracted_value(extracted)
            return extracted, 0.75

        return None, 0.0

    def _extract_value_from_line(self, line_text: str, label: str,
                                 pattern: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Extract value from a line containing a label

        Args:
            line_text: Text of the line
            label: Label to look for
            pattern: Optional regex pattern to validate value

        Returns:
            Tuple of (extracted_value, confidence_score)
        """
        # Common separators between label and value
        separators = [':', '=', '-', '|', ',']

        # Try to find label position (case insensitive)
        label_lower = label.lower()
        line_lower = line_text.lower()

        # Find label position
        label_pos = line_lower.find(label_lower)
        if label_pos == -1:
            return None, 0.0

        # Get text after label
        value_text = line_text[label_pos + len(label):].strip()

        # Remove leading separators
        for sep in separators:
            value_text = value_text.lstrip(sep).strip()

        # If value is empty, return None
        if not value_text:
            return None, 0.0

        # If pattern provided, try to match it
        if pattern:
            for pat in self._iter_patterns(pattern):
                match = re.search(pat, value_text, re.IGNORECASE)
                if match:
                    matched_value = match.group(0).strip()
                    # Clean up the matched value
                    matched_value = self._clean_extracted_value(matched_value)
                    return matched_value, 0.95
                else:
                    # Try to extract first meaningful part
                    # Split by common delimiters
                    for delimiter in [',', ';', '\n', '\t', '  ']:
                        if delimiter in value_text:
                            value_text = value_text.split(delimiter)[0].strip()
                            break

                # Return first few words
                words = value_text.split()
                if words:
                    extracted = ' '.join(words[:10]).strip()
                    extracted = self._clean_extracted_value(extracted)
                    return extracted, 0.6
        else:
            # No pattern - extract until delimiter or end of line
            for delimiter in [',', ';', '\n', '\t']:
                if delimiter in value_text:
                    value_text = value_text.split(delimiter)[0].strip()
                    break

            # Return first meaningful part
            words = value_text.split()
            if words:
                extracted = ' '.join(words[:10]).strip()
                extracted = self._clean_extracted_value(extracted)
                return extracted, 0.8

        return None, 0.0

    def _extract_vessel_name(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract vessel name with regex + line fallback
        (SOLUSI #5)
        """

        # === REGEX UTAMA ===
        pattern1 = r'No\.\s?IMO\s+\d+\s+([A-Z0-9\-\s]{3,50})'
        match = re.search(pattern1, full_text, re.IGNORECASE)
        if match:
            name = match.group(1)
            name = re.split(r'\s+(Dengan|Ex\.|Telah)', name)[0]
            name = self._clean_extracted_value(name)
            return name, 0.95

        # === REGEX MUAT ===
        pattern2 = r'Nama\s+Kapal\s*[:\-]?\s*([A-Z0-9\-\s]{3,50})'
        match = re.search(pattern2, full_text, re.IGNORECASE)
        if match:
            name = self._clean_extracted_value(match.group(1))
            return name, 0.95

        # === FALLBACK LINE-BASED (INI YANG MENYELAMATKAN CERT 2 & 3) ===
        for line in lines:
            text = line.get("text", "")
            if not text:
                continue

            t = text.lower()
            if "nama kapal" in t or "name of ship" in t:
                # ambil setelah label
                value = text.split(":")[-1]
                value = self._clean_extracted_value(value)
                if len(value) >= 3:
                    return value, 0.85

        return None, 0.0

    def _extract_nmkpl(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        FINAL DEADLY FIX — NMKPL PM39 & ILLC P88 (ANTI NGAWUR)
        """

        import re

        if not full_text:
            return None, 0.0

        text = re.sub(r'\s+', ' ', full_text)
        lower = text.lower()

        # ===============================
        # 1️⃣ DETEKSI ILLC (PALING AWAL!)
        # ===============================
        is_illc = any(k in lower for k in (
            'illc',
            'international load line',
            'sertifikat garis muat internasional'
        ))

        # ===============================
        # 2️⃣ ILLC P88 — HARD RULE (LL ONLY)
        # ===============================
        if is_illc:
            # Ambil LL xxxx dari BARIS DATA
            for line in lines:
                row = line.get("text", "").strip()
                if not row:
                    continue

                m = re.match(r'^(LL\s?\d{3,5})\b', row)
                if m:
                    return m.group(1), 0.95

            # Fallback terakhir — tetap ketat
            m = re.search(r'\bLL\s?\d{3,5}\b', text)
            if m:
                return m.group(0), 0.85

            # ⛔ ILLC TIDAK BOLEH AMBIL YANG LAIN
            return None, 0.0

        # ===============================
        # 3️⃣ PM39 — BOLEH BARU JALAN
        # ===============================
        m = re.search(
            r'Nama\s+Kapal\s*[:\-]?\s*([A-Z0-9][A-Z0-9\- ]{2,40})',
            text,
            re.IGNORECASE
        )
        if m:
            return self._clean_extracted_value(m.group(1)), 0.95

        for i, line in enumerate(lines):
            if line.get("text", "").strip().lower() == "nama kapal":
                if i + 1 < len(lines):
                    candidate = lines[i + 1].get("text", "").strip()
                    if (
                            5 <= len(candidate) <= 40
                            and not re.search(
                        r'pendaftaran|pelabuhan|nomor|imo|gt|panjang|tipe',
                        candidate,
                        re.IGNORECASE
                    )
                    ):
                        return self._clean_extracted_value(candidate), 0.93

        return None, 0.0

    def _normalize_nmkpl(self, value: Optional[str]) -> Optional[str]:
        """
        Normalize vessel name (NMKPL)
        """
        if not value:
            return value

        value = value.upper().strip()

        stopwords = [
            " EX",
            " NO",
            " NAME OF SHIP",
            " TANDA PANGGILAN",
            " CALL SIGN",
            " DISTINCTIVE",
            " IMO",
        ]

        for sw in stopwords:
            if sw in value:
                value = value.split(sw)[0]

        value = re.sub(r'[^A-Z0-9\-\s]', '', value)
        value = re.sub(r'\s+', ' ', value).strip()

        if len(value) < 3:
            return None

        return value

    def _normalize_nmkpl(self, value: Optional[str]) -> Optional[str]:
        """
        Normalize vessel name (NMKPL)
        """
        if not value:
            return value

        value = value.upper().strip()

        stopwords = [
            " EX",
            " NO",
            " NAME OF SHIP",
            " TANDA PANGGILAN",
            " CALL SIGN",
            " DISTINCTIVE",
            " IMO",
        ]

        for sw in stopwords:
            if sw in value:
                value = value.split(sw)[0]

        value = re.sub(r'[^A-Z0-9\-\s]', '', value)
        value = re.sub(r'\s+', ' ', value).strip()

        if len(value) < 3:
            return None

        return value

    def _is_valid_nmkpl(self, value: str) -> bool:
        if not value:
            return False

        v = value.upper()

        # ❌ kalimat dokumen (INI PENYEBAB NGACO)
        blacklist = [
            "PENGENAL",
            "PENDAFTARAN",
            "DITETAPKAN",
            "DALAM PAS",
            "SERTIFIKAT",
            "CERTIFICATE",
            "DITERBITKAN",
            "BERDASARKAN"
        ]

        if any(b in v for b in blacklist):
            return False

        # panjang wajar nama kapal
        if not (3 <= len(v) <= 40):
            return False

        # hanya huruf / angka / spasi / dash
        if not re.match(r'^[A-Z0-9\- ]+$', v):
            return False

        return True

    def _extract_issue_date(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract certificate issue date

        Args:
            full_text: Full text from OCR
            lines: List of text lines

        Returns:
            Tuple of (date, confidence)
        """
        # Pattern: "Dikeluarkan di JAKARTA.tanggal 081 MEI 2020"
        pattern = r'Dikeluarkan\s+di\.?\s+[A-Z]+\.?\s*tanggal\s+(\d{2,3})\s?([A-Z]{3,9})\s?(\d{4})'
        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            day = match.group(1)
            month = match.group(2)
            year = match.group(3)

            # Fix OCR errors: 081 -> 08, 091 -> 09, etc.
            if len(day) == 3 and day.startswith('0'):
                # OCR error: 081 -> 08
                day = day[:2]
            elif len(day) == 2 and int(day) > 31:
                # OCR error: 81 -> 08, 91 -> 09
                day = '0' + day[1]

            # Convert month name to number
            month_map = {
                'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
                'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
                'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11', 'DESEMBER': '12'
            }

            if month.upper() in month_map:
                date_str = f"{year}/{month_map[month.upper()]}/{day.zfill(2)}"
                logger.info(f"Extracted issue date: {date_str}")
                return date_str, 0.95

        # Pattern 2: "Tanggal 08 APRIL 2024" (for Muat)
        pattern2 = r'(?:ADINDA WINDU KARSA|JAKARTA)\s+Tanggal\s+(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})'
        match = re.search(pattern2, full_text, re.IGNORECASE)

        if match:
            day = match.group(1)
            month = match.group(2)
            year = match.group(3)

            # Convert month name to number
            month_map = {
                'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
                'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
                'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11', 'DESEMBER': '12'
            }

            if month.upper() in month_map:
                date_str = f"{year}/{month_map[month.upper()]}/{day.zfill(2)}"
                logger.info(f"Extracted issue date (Muat): {date_str}")
                return date_str, 0.95

        return None, 0.0

    def _normalize_lokasi_survey(self, raw_value: Optional[str]) -> Optional[str]:
        """
        Normalize lokasi survey to city name only (e.g. SEMARANG, JAKARTA)
        """
        if not raw_value:
            return None

        raw = raw_value.upper()

        # Daftar kota utama BKI (bisa kamu tambah)
        kota_list = [
            "JAKARTA", "SEMARANG", "SURABAYA", "BATAM", "BELAWAN",
            "MAKASSAR", "BALIKPAPAN", "PALEMBANG", "PONTIANAK"
        ]

        for kota in kota_list:
            if kota in raw:
                return kota

        return None

    def _extract_surveyor(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract surveyor/division information

        Args:
            full_text: Full text from OCR
            lines: List of text lines

        Returns:
            Tuple of (surveyor, confidence)
        """
        # Pattern 1: "oleh Surveyor padat" (for Mesin)
        pattern1 = r'(Surveyor|Pengawas)(?:\s+[A-Z\s]+)?'
        match = re.search(pattern1, full_text, re.IGNORECASE)

        if match:
            surveyor = match.group(1)
            logger.info(f"Extracted surveyor (pattern 1): {surveyor}")
            return match.group(1), 0.95

        # Pattern 2: "di TEGAL & MERAK Pengawas" (for Lambung)
        pattern2 = r'di\s+[A-Z\s&]+\s+(Pengawas|Surveyor)\s+([A-Z\s]+)'
        match = re.search(pattern2, full_text)

        if match:
            surveyor = match.group(1)
            logger.info(f"Extracted surveyor (pattern 2): {surveyor}")
            return surveyor, 0.95

        # Pattern 3:
        # For Muat certificates, we'll return "Surveyor" as default
        if 'SERTIFIKAT NASIONAL MUAT' in full_text or 'National Load Certificate' in full_text:
            # Check if there's "Pengawas Operasional" or similar
            if 'Pengawas Operasional' in full_text or 'Pengawas Bisnis' in full_text:
                logger.info(f"Extracted surveyor (Muat default): Surveyor")
                return "Surveyor", 0.90

        return None, 0.0

    def _extract_survey_date1(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract first survey date (MUAT) based on 'pemeriksaan pertama / pembaruan'
        """

        month_map = {
            'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
            'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
            'SEPTEMBER': '09', 'OKTOBER': '10',
            'NOVEMBER': '11', 'NOPEMBER': '11',
            'DESEMBER': '12'
        }

        text = re.sub(r'\s+', ' ', full_text.upper())

        # =====================================================
        # 1️⃣ AMBIL BLOK KALIMAT PEMERIKSAAN (OCR REAL)
        # =====================================================
        context_pattern = (
            r'TANGGAL\s+PEMERIKSAAN.*?'
            r'(PERTAMA|PEMBARUAN).*?'
            r'(\d{1,2})\s+'
            r'(JANUARI|FEBRUARI|MARET|APRIL|MEI|JUNI|JULI|AGUSTUS|'
            r'SEPTEMBER|OKTOBER|NOVEMBER|NOPEMBER|DESEMBER)'
            r'\s+(\d{4})'
        )

        m = re.search(context_pattern, text, re.DOTALL)
        if m:
            day = m.group(2).zfill(2)
            month_raw = m.group(3)
            year = m.group(4)

            month = month_map.get(month_raw)
            if month:
                date_str = f"{year}-{month}-{day}"
                logger.info(f"Extracted TGL_SURVEY1 (MUAT CONTEXT): {date_str}")
                return date_str, 0.99

        # =====================================================
        # 2️⃣ FALLBACK LAMBUNG / MESIN (NUMERIC)
        # =====================================================
        fallback = r'(PADAT|PADA)\s+TANGGAL\s+(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})'
        m = re.search(fallback, text)

        if m:
            day = m.group(2).zfill(2)
            month = m.group(3).zfill(2)
            year = m.group(4)
            date_str = f"{year}-{month}-{day}"
            logger.info(f"Extracted TGL_SURVEY1 (FALLBACK): {date_str}")
            return date_str, 0.95

        return None, 0.0

    def _extract_survey_date2(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract second survey date

        Args:
            full_text: Full text from OCR
            lines: List of text lines

        Returns:
            Tuple of (date, confidence)
        """
        # Pattern: "s/d 01.03. 2020"
        pattern = r's/d\s+(\d{1,2})[\.\-\/](\d{1,2})[\.\-\/]?\s?(\d{4})'
        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            day = match.group(1).zfill(2)
            month = match.group(2).zfill(2)
            year = match.group(3)
            date_str = f"{year}-{month}-{day}"
            logger.info(f"Extracted survey date 2: {date_str}")
            return date_str, 0.95

        return None, 0.0

    def _extract_valid_date(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract certificate validity end date (TGL_BERLAKU)
        """

        month_map = {
            'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
            'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
            'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11',
            'NOPEMBER': '11',  # OCR typo
            'DESEMBER': '12'
        }

        # ===============================
        # PATTERN 1 — berlaku sampai 17 NOPEMBER 2021
        # ===============================
        pattern1 = (
            r'(berlaku\s+sampai|valid\s+until|paling\s+lambat\s+sampai(?:\s+dengan)?)'
            r'.*?(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})'
        )

        match = re.search(pattern1, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            day = match.group(2).zfill(2)
            month_raw = match.group(3).upper()
            year = match.group(4)

            if month_raw in month_map:
                date_str = f"{year}-{month_map[month_raw]}-{day}"
                logger.info(f"Extracted TGL_BERLAKU (text month): {date_str}")
                return date_str, 0.95

        # ===============================
        # PATTERN 2 — berlaku sampai s/d 17.11.2021
        # ===============================
        pattern2 = (
            r'(berlaku\s+sampai|valid\s+until|paling\s+lambat\s+sampai)'
            r'.*?(\d{1,2})[.\-\/](\d{1,2})[.\-\/](\d{4})'
            r'(Sertifikat ini\s+sampai|berlaku\s+until|sampai\s+pemeriksaan\s+pembaharuan\s+berikutnya)'
            r'.*?(\d{1,2})[.\-\/](\d{1,2})[.\-\/](\d{4})'
        )

        match = re.search(pattern2, full_text, re.IGNORECASE | re.DOTALL)
        if match:
            day = match.group(2).zfill(2)
            month = match.group(3).zfill(2)
            year = match.group(4)
            date_str = f"{year}-{month}-{day}"
            logger.info(f"Extracted TGL_BERLAKU (numeric): {date_str}")
            return date_str, 0.95

        return None, 0.0

    def _extract_tgl_sert(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        month_map = {
            'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
            'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
            'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11',
            'NOPEMBER': '11',  # OCR typo
            'DESEMBER': '12'
        }

        pattern = r'tanggal\s+(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})'

        match = re.search(pattern, full_text.upper(), re.IGNORECASE)
        if match:
            day = match.group(1).zfill(2)
            month_text = match.group(2).upper()
            year = match.group(3)

            month = month_map.get(month_text)
            if not month:
                return None, 0.0

            date_str = f"{year}-{month}-{day}"
            logger.info(f"Extracted TGL_SERT (numeric): {date_str}")
            return date_str, 0.95

        return None, 0.0

# ========================
# START MEM01 PARSING HERE
# ========================

    def _extract_pembaruanke(self, text):
        romawi_map = {
            "I": "satu",
            "II": "dua",
            "III": "tiga",
            "IV": "empat",
            "V": "lima",
            "VI": "enam",
            "VII": "tujuh",
            "VIII": "delapan",
            "IX": "sembilan",
            "X": "sepuluh",
        }

        m = re.search(
            r'pembaruan\s+kelas\s+([ivx]+)',
            text,
            re.IGNORECASE
        )
        if not m:
            return None, 0.0

        romawi = m.group(1).upper()
        kata = romawi_map.get(romawi, "")

        return f"Pembaruan Ke: {romawi} ({kata})", 0.95

    def _extract_noimo(self, text):
        m = re.search(r'No\.?\s*IMO\s*[:\-]?\s*(\d{6,7})', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_exkpl(self, text):
        m = re.search(
            r'Ex\.?\s*([A-Z0-9\- ]{3,50})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        value = m.group(1)
        value = re.split(
            r'\b(dengan|yang|mt|kapal|survey|diterangkan)\b',
            value,
            flags=re.IGNORECASE
        )[0]

        return value.strip()

    def _extract_jenis(self, text):
        m = re.search(
            r'kapal\s+([A-Z ]{5,40})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        return f"KAPAL {m.group(1).strip()}"

    def _extract_brt(self, text):
        m = re.search(r'Tonase\s+Kotor\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_nrt(self, text):
        m = re.search(r'Tonase\s+Bersih\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_nmgal(self, text):
        """
        Extract NAMA GALANGAN KAPAL (BUKAN SURVEYOR)
        """
        m = re.search(
            r'Dibangun\s+di\s+[A-Z\s]{3,40}\s+oleh\s+([A-Z0-9\s\.\-&]{5,80})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        value = m.group(1)

        # bersihkan noise
        value = re.sub(
            r'\b(PT|LTD|K\.K|CO|CORP)\b.*$',
            '',
            value,
            flags=re.IGNORECASE
        )

        return value.strip()

    def _extract_lgal(self, text):
        m = re.search(
            r'Dibangun\s+di\s+([A-Z\s]{3,40})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        value = m.group(1)
        value = re.sub(r'\b(oleh)\b.*$', '', value, flags=re.IGNORECASE)
        return value.strip()

    def _extract_thba(self, text):
        m = re.search(
            r'Tahun\s+Bangun\s*[:\-]?\s*(\d{4})',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_kota(self, text):
        m = re.search(
            r'Pelabuhan\s+Pendaftaran\s+([A-Z\s]{3,40})',
            text,
            re.IGNORECASE
        )
        return m.group(1).strip() if m else None

    def _extract_flag(self, text):
        m = re.search(r'Bendera\s*[:\-]?\s*([A-Z\s]+)', text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _extract_nama1(self, text):
        m = re.search(
            r'(Pemilik|Owner)\s*[:\-]?\s*([A-Z0-9\.\s]{5,60})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        value = m.group(2)
        value = re.sub(r'\bOWNER\b.*$', '', value, flags=re.IGNORECASE)
        return value.strip()

    def _extract_notasi(self, text):
        m = re.search(r'✠\s*A100\s*P\s*Tug', text)
        return "A100 P Tug" if m else None

    def _extract_tandatangan(self, text):
        m = re.search(r'\n([A-Z\s]+)\nNUP', text)
        return m.group(1).strip() if m else None

    def _extract_nup(self, text):
        m = re.search(r'NUP\s*[:\-]?\s*(\d{4,6}\-KI)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_tgl_lastdok(self, text):
        m = re.search(
            r'(\d{1,2})\s+SEPTEMBER\s+(\d{4})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None
        day = m.group(1).zfill(2)
        return f"{m.group(2)}-09-{day}"

    def _extract_periode_poros(self, text):
        angka_map = {
            "1": "satu",
            "2": "dua",
            "3": "tiga",
            "4": "empat",
            "5": "lima",
            "6": "enam",
            "7": "tujuh",
            "8": "delapan",
            "9": "sembilan",
            "10": "sepuluh",
        }

        m = re.search(
            r'(?:periode|periodicity).*?(?:survey)?.*?(\d{1,2})\s*(?:tahun|year)',
            text,
            re.IGNORECASE
        )
        if not m:
            return None, 0.0

        angka = m.group(1)
        kata = angka_map.get(angka, "")

        if kata:
            return f"Periode Poros: {angka} ({kata})", 0.95

        return f"Periode Poros: {angka}", 0.95

    def _extract_sme(self, text):
        m = re.search(
            r'(?:main\s+engine|mesin\s+utama).*?(\d+)\s*\(?(?:dua|tiga|empat|lima)?\)?\s*buah',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_ehpme(self, text):
        m = re.search(
            r'(?:tenaga\s+efektif|effective\s+power).*?(\d{2,5})\s*hp',
            text,
            re.IGNORECASE
        )
        if m:
            return m.group(1)

        # fallback: "2 x 353 HP"
        m = re.search(r'\b\d+\s*x\s*(\d{2,5})\s*hp\b', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_rpmme(self, text):
        m = re.search(
            r'(\d{3,5})\s*rpm',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_serime(self, text):
        m = re.search(
            r'No\.?\s*Mesin\s*[:\-]?\s*([A-Z0-9\-]+)',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_smb(self, text):
        m = re.search(
            r'(?:auxiliary\s+engine|mesin\s+bantu).*?(\d+)\s*(?:buah|unit)?',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    # =========================
    # MEM01 MUAT
    # =========================

    def _extract_call(self, text):
        m = re.search(
            r'nomor\s+atau\s+huruf\s+pengenal\s*[:\-]?\s*([A-Z0-9]{2,10})',
            text,
            re.IGNORECASE
        )
        return m.group(1).upper() if m else None

    def _extract_panjang(self, text):
        m = re.search(
            r'panjang\s*\(?L\)?\s*[:\-]?\s*([\d]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_tipe(self, text):
        m = re.search(
            r'tipe\s+kapal\s*[:\-]?\s*([A-Z])\b',
            text,
            re.IGNORECASE
        )
        return m.group(1).upper() if m else None

    def _extract_ll(self, text, code):
        m = re.search(rf'(\d+)\s*mm\s*\({code}\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_ts(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(T\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_s66(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(S\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_sw(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(W\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_swna(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(WNA\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lss(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(LS\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslt(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(LT\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslw(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(LW\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslwna(self, text):
        m = re.search(r'([\d.,]+)\s*mm\s*\(LWNA\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_jn_kapal(self, text):
        if re.search(r'lambung\s+timbul\s+kayu', text, re.IGNORECASE):
            return "Kayu"
        if re.search(r'lambung\s+timbul', text, re.IGNORECASE):
            return "Non Kayu"
        return None

    def _extract_nonkayu(self, text):
        m = re.search(
            r'penyesuaian\s+pada\s+air\s+tawar\s*([\d.,]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_kayu(self, text):
        m = re.search(
            r'untuk\s+lambung\s+timbul\s+kayu\s*([\d.,]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    # =========================
    # GELADAK
    # =========================

    def _extract_diukur(self, text):
        m = re.search(
            r'tepi\s+atas\s+garis\s+geladak\s*([\d.,]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_geladakaind(self, text):
        m = re.search(
            r'di\s+pada\s+sisi\s+kapal\s*([A-Z]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_geladakeng(self, text):
        m = re.search(
            r'at\s+side\s*([A-Z]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_nosah(self, text):
        m = re.search(
            r'No\s*Pengesahan\s*[:\-]?\s*([0-9\/\-]+)',
            text, re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_barulama(self, text):
        if re.search(r'\bbaru\b', text, re.IGNORECASE):
            return "Baru"
        if re.search(r'\blama\b', text, re.IGNORECASE):
            return "Lama"
        return None

    def _extract_mem01_hull(self, text: str):
        mem_parts = []

        pembaruanke, _ = self._extract_pembaruanke(text)
        if pembaruanke:
            mem_parts.append(pembaruanke)

        noimo = self._extract_noimo(text)
        if noimo:
            mem_parts.append(f"No. IMO: {noimo}")

        ex = self._extract_exkpl(text)
        if ex:
            mem_parts.append(f"Ex: {ex}")

        jenis = self._extract_jenis(text)
        if jenis:
            mem_parts.append(f"Jenis: {jenis}")

        brt = self._extract_brt(text)
        if brt:
            mem_parts.append(f"BRT: {brt}")

        nrt = self._extract_nrt(text)
        if nrt:
            mem_parts.append(f"NRT: {nrt}")

        nmgal = self._extract_nmgal(text)
        if nmgal:
            mem_parts.append(f"Galangan: {nmgal}")

        lgal = self._extract_lgal(text)
        if lgal:
            mem_parts.append(f"Dibangun di: {lgal}")

        thba = self._extract_thba(text)
        if thba:
            mem_parts.append(f"Tahun Bangun: {thba}")

        kota = self._extract_kota(text)
        if kota:
            mem_parts.append(f"Kota: {kota}")

        flag = self._extract_flag(text)
        if flag:
            mem_parts.append(f"Bendera: {flag}")

        owner = self._extract_nama1(text)
        if owner:
            mem_parts.append(f"Pemilik: {owner}")

        tgl_lastdok = self._extract_tgl_lastdok(text)
        if tgl_lastdok:
            mem_parts.append(f"Dok Terakhir: {tgl_lastdok[0]}")

        if mem_parts:
            return ", ".join(mem_parts), 0.95

        return None, 0.0

    def _extract_mem01_mach(self, text: str):
        mem_parts = []

        periode_poros, _ = self._extract_periode_poros(text)
        if periode_poros:
            mem_parts.append(periode_poros)

        noimo = self._extract_noimo(text)
        if noimo:
            mem_parts.append(f"No. IMO: {noimo}")

        ex = self._extract_exkpl(text)
        if ex:
            mem_parts.append(f"Ex: {ex}")

        jenis = self._extract_jenis(text)
        if jenis:
            mem_parts.append(f"Jenis: {jenis}")

        sme = self._extract_sme(text)
        if sme:
            mem_parts.append(f"Main Engine: {sme} unit")

        ehpme = self._extract_ehpme(text)
        if ehpme:
            mem_parts.append(f"Daya Mesin: {ehpme} HP")

        rpmme = self._extract_rpmme(text)
        if rpmme:
            mem_parts.append(f"Putaran: {rpmme} RPM")

        serime = self._extract_serime(text)
        if serime:
            mem_parts.append(f"No Mesin: {serime}")

        smb = self._extract_smb(text)
        if smb:
            mem_parts.append(f"Mesin Bantu: {smb} unit")

        lgal = self._extract_lgal(text)
        if lgal:
            mem_parts.append(f"Dibangun di: {lgal}")

        nmgal = self._extract_nmgal(text)
        if nmgal:
            mem_parts.append(f"Galangan: {nmgal}")

        thba = self._extract_thba(text)
        if thba:
            mem_parts.append(f"Tahun Bangun: {thba}")

        if mem_parts:
            return ", ".join(mem_parts), 0.95

        return None, 0.0

    def _normalize_muat_text(self, text: str) -> str:
        text = text.replace("\n", " ")
        text = re.sub(r'\s+', ' ', text)

        # Satukan hasil OCR yang terpisah: "730 mm T" / "730 mm ( T )"
        text = re.sub(
            r'(\d+)\s*mm\s*\(?\s*([A-Z]{1,3})\s*\)?',
            r'\1 mm (\2)',
            text,
            flags=re.IGNORECASE
        )

        return text

    def _extract_mem01_muat(self, text: str):
        logger.error("=== DEBUG MUAT TEXT START ===")
        logger.error(text[:1500])
        logger.error("=== DEBUG MUAT TEXT END ===")

        mem_parts = []

        call = self._extract_call(text)
        if call:
            mem_parts.append(f"Call: {call}")

        panjang = self._extract_panjang(text)
        if panjang:
            mem_parts.append(f"Panjang: {panjang} m")

        tipe = self._extract_tipe(text)
        if tipe:
            mem_parts.append(f"Tipe: {tipe}")

        jenis = self._extract_jn_kapal(text)
        if jenis:
            mem_parts.append(f"Jenis Kapal: {jenis}")

        for code in ["T", "S", "W", "WNA", "LS", "LT", "LW", "LWNA"]:
            val = self._extract_ll(text, code)
            if val:
                mem_parts.append(f"{code}: {val}")

        if mem_parts:
            return ", ".join(mem_parts), 0.95

        return None, 0.0

    def _extract_mem01(self, full_text: str, lines: List[Dict]):
        text = re.sub(r'\s+', ' ', full_text)
        lower = text.lower()

        # Deteksi jenis sertifikat dari konteks
        if 'sertifikat klasifikasi lambung' in lower:
            return self._extract_mem01_hull(text)

        if 'sertifikat klasifikasi mesin' in lower:
            return self._extract_mem01_mach(text)

        if any(k in lower for k in [
            'sertifikat garis muat',
            'nasional garis muat',
            'international load line',
            'load line certificate',
            'illc',
            'pm 39'
        ]):
            return self._extract_mem01_muat(text)

        return None, 0.0

    def _clean_extracted_value(self, value: str) -> str:
        """
        Clean extracted value by removing unwanted characters

        Args:
            value: Raw extracted value

        Returns:
            Cleaned value
        """
        if not value:
            return value

        # Remove multiple spaces
        value = re.sub(r'\s{2,}', ' ', value)

        # Remove trailing punctuation (but keep internal ones)
        value = value.rstrip('.,;:')

        # Remove leading/trailing whitespace
        value = value.strip()

        # Normalize date formats (if looks like a date)
        date_pattern = r'\d{1,2}[-/\s]\d{1,2}[-/\s]\d{2,4}'
        if re.match(date_pattern, value):
            # Normalize separators to /
            value = re.sub(r'[-\s]', '/', value)

        return value

    def _extract_by_pattern(self, pattern: Optional[str],
                           lines: List[Dict]) -> Tuple[Optional[str], float]:
        """
        Extract value by pattern matching across all text

        Args:
            pattern: Regex pattern to match
            lines: List of text lines

        Returns:
            Tuple of (extracted_value, confidence_score)
        """
        if not pattern:
            return None, 0.0

        all_matches = []

        # Search in each line and collect all matches
        for pat in self._iter_patterns(pattern):
            for line in lines:
                line_text = line['text']
                matches = re.finditer(pat, line_text, re.IGNORECASE)
                for match in matches:
                    matched_text = self._clean_extracted_value(match.group(0))
                    if matched_text:
                        all_matches.append(matched_text)

        # Return first match with good confidence
        if all_matches:
            # Prefer longer matches (usually more specific)
            all_matches.sort(key=len, reverse=True)
            return all_matches[0], 0.75

        return None, 0.0

    def _iter_patterns(self, pattern):
        """
        Normalize pattern to iterable list
        """
        if pattern is None:
            return []
        if isinstance(pattern, list):
            return pattern
        return [pattern]

    def _calculate_quality_score(self, metadata: Dict) -> float:
        """
        Calculate overall quality score for extraction

        Args:
            metadata: Metadata dictionary with extraction results

        Returns:
            Quality score between 0.0 and 1.0
        """
        total_fields = len(self.fields_config)
        if total_fields == 0:
            return 0.0

        # Count successful extractions
        successful = sum(1 for status in metadata['extraction_status'].values()
                        if status == 'SUCCESS')

        # Average confidence of successful extractions
        confidences = [conf for conf in metadata['confidence_scores'].values()
                      if conf > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Weighted score
        extraction_rate = successful / total_fields
        quality_score = (extraction_rate * 0.7) + (avg_confidence * 0.3)

        return round(quality_score, 3)

    def format_output(self, metadata: Dict, format_type: str = 'json') -> Any:
        """
        Format extracted metadata for output

        Args:
            metadata: Metadata dictionary
            format_type: Output format ('json', 'dict', 'text')

        Returns:
            Formatted output
        """
        if format_type == 'text':
            output = []
            output.append("=" * 50)
            output.append("EXTRACTED METADATA")
            output.append("=" * 50)

            for field_name, value in metadata['extracted_fields'].items():
                confidence = metadata['confidence_scores'].get(field_name, 0)
                status = metadata['extraction_status'].get(field_name, 'UNKNOWN')

                output.append(f"\n{field_name.upper()}:")
                output.append(f"  Value: {value if value else 'NOT FOUND'}")
                output.append(f"  Confidence: {confidence:.2%}")
                output.append(f"  Status: {status}")

            output.append(f"\nOVERALL QUALITY: {metadata['overall_quality']:.2%}")
            output.append("=" * 50)

            return '\n'.join(output)

        elif format_type == 'dict':
            return metadata

        else:  # json
            import json
            return json.dumps(metadata, indent=2, ensure_ascii=False)

    def validate_extraction(self, metadata: Dict) -> Tuple[bool, List[str]]:
        """
        Validate that all required fields were extracted
        OPTIONAL fields do NOT invalidate the certificate
        Supports legacy string-based fields and dict-based fields
        """
        errors = []
        extracted = metadata.get('extracted_fields', {})

        for field_name in self.REQUIRED_FIELDS:
            field_data = extracted.get(field_name)

            # Case 1: field tidak ada sama sekali
            if field_data is None:
                errors.append(f"Required field '{field_name}' is missing")
                continue

            # Case 2: legacy format → string
            if isinstance(field_data, str):
                if field_data in ['', 'NOT FOUND']:
                    errors.append(f"Required field '{field_name}' is missing")
                continue

            # Case 3: new format → dict
            if isinstance(field_data, dict):
                value = field_data.get('value')
                if value in [None, '', 'NOT FOUND']:
                    errors.append(f"Required field '{field_name}' is missing")
                continue

            # Case 4: unexpected type
            errors.append(f"Required field '{field_name}' is missing")

        is_valid = len(errors) == 0
        return is_valid, errors
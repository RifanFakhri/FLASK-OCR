"""
Text Parser Module
Parsing to extract specific fields and values from OCR results
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any

from fontTools.misc.cython import returns
from rapidfuzz import fuzz, process
from datetime import datetime

logger = logging.getLogger(__name__)


class TextParser:
    def __init__(self, config: Dict):
        #Inisiasi dict text parser menggunakan config
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

        self.shared_nmkpl = None
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

        # SINGLE CERT FALLBACK
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
            # Normalize whitespace and special characters for detection
            t_normalized = re.sub(r'[\s\!]', ' ', t)  # Replace whitespace/special chars with space
            t_normalized = re.sub(r'\s+', ' ', t_normalized)  # Normalize multiple spaces
            
            # Lambung detection - handle OCR errors like "KLA ASIFIKASI", "KLASIFIASI LAMBUNG"
            # Pattern: sertifikat + (optional: kla/klasifi prefix) + asifikasi + lambung
            if re.search(r'sertifikat\s+(kla\s+)?asifikasi\s+lambung', t_normalized):
                return "lambung"
            if "sertifikat klasifikasi lambung" in t_normalized:
                return "lambung"
                
            # Mesin detection - handle OCR errors:
            # "KLASIFIASI" (missing k), "KLASIFIKSI" (missing a), "KLASIFIKASI" (normal)
            # Using fuzzy pattern: sertifikat + klasifi + (letters) + mesin
            if re.search(r'sertifikat\s+klasifi\w*\s+mesin', t_normalized):
                return "mesin"
            # Fallback: direct search for key components
            if "sertifikat" in t_normalized and "mesin" in t_normalized and ("klasifi" in t_normalized or "machinery" in t_normalized):
                return "mesin"
                
            # Muat detection
            if "sertifikat nasional garis muat" in t_normalized or "national load line certificate" in t:
                return "muat"
                
            return None

        # GROUP HALAMAN TEMPAT SERTIFIKAT BERADA
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

        # PARSE PER SERTIFIKAT
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

        # REUSE LOKASI SURVEY DARI HULL / MACH UNTUK MUAT
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

        # REUSE TGL-SURVEY1 & TGL_SURVEY2 DARI HULL / MACH KE MUAT
        shared_survey1 = None
        shared_survey2 = None

        # Ambil TGL_SURVEY1 dari HULL atau MACH
        for meta in results:
            if meta.get("certificate_type") in ["lambung", "mesin"]:
                val = meta["extracted_fields"].get("tgl_survey1")
                if val and val != "NOT FOUND":
                    shared_survey1 = val
                    break

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
                    # REUSE ke tgl_survey1
                    meta["extracted_fields"]["tgl_survey1"] = shared_survey1
                    meta["confidence_scores"]["tgl_survey1"] = 0.0
                    meta["extraction_status"]["tgl_survey1"] = "SUCCESS"

                    # REUSE ke tgl_survey2
                    meta["extracted_fields"]["tgl_survey2"] = shared_survey2
                    meta["confidence_scores"]["tgl_survey2"] = 0.95
                    meta["extraction_status"]["tgl_survey2"] = "SUCCESS"

                    logger.info(
                        f"Reused TGL_SURVEY1 for MUAT from HULL/MACH: {shared_survey1}"
                        f"Reused TGL_SURVEY2 for MUAT from HULL/MACH: {shared_survey2}"
                    )

        # REUSE TGL_BERLAKU DARI HULL / MACH KE MUAT
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

        # REUSE DIVISI DARI HULL / MACH KE MUAT

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

        # REUSE NMKPL DARI HULL / MACH KE MUAT (PM39 & ILLC)
        shared_nmkpl = None

        # Ambil dari HULL & MACH
        for meta in results:
            cert_type = meta.get("certificate_type", "").lower()

            if "lambung" in cert_type or "mesin" in cert_type:
                val = meta["extracted_fields"].get("nmkpl")
                if self._is_valid_nmkpl(val):
                    shared_nmkpl = val
                    break

        # Terapkan ke MUAT & ILLC
        if shared_nmkpl:
            for meta in results:
                cert_type = meta.get("certificate_type", "").lower()

                # REUSE DI HULL
                if "lambung" in cert_type:
                    meta["extracted_fields"]["nmkpl"] = shared_nmkpl
                    meta["confidence_scores"]["nmkpl"] = 0.0
                    meta["extraction_status"]["nmkpl"] = "SUCCESS"

                    logger.info(
                        f"Backfilled NMKPL for Hull: {shared_nmkpl}"
                    )

                #REUSE DI LOADLINE
                if "PM" in cert_type or "illc" in cert_type:
                    meta["extracted_fields"]["nmkpl"] = shared_nmkpl
                    meta["confidence_scores"]["nmkpl"] = 0.85
                    meta["extraction_status"]["nmkpl"] = "SUCCESS"

                    logger.info(
                        f"Reused NMKPL for {cert_type.upper()}: {shared_nmkpl}"
                    )

        # REUSE JENIS_SURVEY DARI HULL / MACH KE MUAT

        shared_jenis_survey = None

        # Ambil dari HULL & MACH
        for meta in results:
            cert_type = meta.get("certificate_type", "").lower()

            if "lambung" in cert_type or "mesin" in cert_type:
                val = meta["extracted_fields"].get("jenis_survey")
                if val and val != "NOT FOUND":
                    shared_jenis_survey = val
                    break

        # Terapkan ke MUAT
        if shared_jenis_survey:
            for meta in results:
                cert_type = meta.get("certificate_type", "").lower()

                if "muat" in cert_type or "pm" in cert_type or "illc" in cert_type:
                    meta["extracted_fields"]["jenis_survey"] = shared_jenis_survey
                    meta["confidence_scores"]["jenis_survey"] = 0.90
                    meta["extraction_status"]["jenis_survey"] = "SUCCESS"

                    logger.info(
                        f"Reused JENIS_SURVEY for {cert_type.upper()}: {shared_jenis_survey}"
                    )

        # REUSE CALL & TGL_LASTDOK (MEM01 ONLY)
        shared_call = None
        shared_nmkpl = None
        shared_tgl_surveyawal = None
        shared_tgl_surveyakhir = None

        for meta in results:
            if meta["certificate_type"] == "muat":
                shared_call = meta["extracted_fields"].get("call")

            if meta["certificate_type"] in ("lambung", "mesin"):
                shared_tgl_surveyawal = meta["extracted_fields"].get("tgl_survey1")
                shared_tgl_surveyakhir = meta["extracted_fields"].get("tgl_survey2")
                shared_nmkpl = meta["extracted_fields"].get("nmkpl")

        for meta in results:
            if meta["certificate_type"] == "lambung":

                # reuse CALL
                if shared_call:
                    meta["extracted_fields"]["call"] = shared_call

                if shared_tgl_surveyawal:
                    mem01_val = meta["extracted_fields"].get("mem01")

                    if mem01_val:
                        meta["extracted_fields"]["mem01"] = (
                            f"{mem01_val}, Survey Awal: {shared_tgl_surveyawal}"
                        )

                # HANYA UNTUK MEM01
                if shared_tgl_surveyakhir:
                    mem01_val = meta["extracted_fields"].get("mem01")

                    if mem01_val:
                        meta["extracted_fields"]["mem01"] = (
                            f"{mem01_val}, Survey Terakhir: {shared_tgl_surveyakhir}"
                        )

        return {
            "multiple_certificates": True,
            "count": len(results),
            "certificates": results
        }

    def _build_cert_text(self, pages: List[Dict]) -> str:
        texts = []
        for p in pages:
            txt = p.get("text", "")
            if txt:
                texts.append(txt.strip())
        return "\n".join(texts)

    # PARSE SINGLE CERTIFICATE
    def _parse_single_certificate(self, ocr_result: Dict) -> Dict:
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

        # TEMPLATE DETECTION
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

        # FIELD EXTRACTION
        mapped_cert_type = None
        for field_name, field_config in self.fields_config.items():
            logger.debug(f"Extracting field: {field_name}")

            extracted_value, confidence = self._extract_field(
                field_name,
                field_config,
                lines,
                ocr_result,
            )

            # MAP JENIS SERT
            if field_name == 'jenis_sert' and field_config.get('map_to_code', False):
                extracted_value = self._map_certificate_type(extracted_value, full_text)
                mapped_cert_type = extracted_value

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

        # CERTIFICATE TYPE (LEGAL TYPE)
        certificate_type = (mapped_cert_type or "").upper()

        # NORMALISASI LOKASI SURVEY
        raw_lokasi = metadata["extracted_fields"].get("lokasi_survey")
        clean_lokasi = self._normalize_lokasi_survey(raw_lokasi)

        if clean_lokasi:
            metadata["extracted_fields"]["lokasi_survey"] = clean_lokasi
            metadata["confidence_scores"]["lokasi_survey"] = 0.95
            metadata["extraction_status"]["lokasi_survey"] = "SUCCESS"

        # SHARED NOREG HANDLING
        if shared_noreg:
            if self.current_template_name == "template_muat":
                # MUAT HARUS REUSE NOREG KARENA DI SERTIF MUAT GK ADA NOREG SECARA EKSPLISIT
                metadata["extracted_fields"]["noreg"] = shared_noreg
                metadata["confidence_scores"]["noreg"] = 0.95
                metadata["extraction_status"]["noreg"] = "SUCCESS"
            else:
                if metadata["extracted_fields"].get("noreg") in [None, "NOT FOUND"]:
                    metadata["extracted_fields"]["noreg"] = shared_noreg
                    metadata["confidence_scores"]["noreg"] = 0.85
                    metadata["extraction_status"]["noreg"] = "SUCCESS"

        # SHARED NMKPL HANDLING

        # SIMPAN NMKPL DARI HULL & MACH
        if (
                certificate_type in ("HULL", "MACH")
                and self._is_valid_nmkpl(metadata["extracted_fields"].get("nmkpl"))
        ):
            self.shared_nmkpl = metadata["extracted_fields"]["nmkpl"]
            logger.info(f"[NMKPL] Stored from {certificate_type}: {self.shared_nmkpl}")

        # REUSE KE MUAT
        if (
                certificate_type in ("MUAT", "ILLC P88", "PM39", "P88")
                and not self._is_valid_nmkpl(metadata["extracted_fields"].get("nmkpl"))
                and getattr(self, "shared_nmkpl", None)
        ):
            metadata["extracted_fields"]["nmkpl"] = self.shared_nmkpl
            metadata["confidence_scores"]["nmkpl"] = 0.85
            metadata["extraction_status"]["nmkpl"] = "SUCCESS"
            logger.info(f"[NMKPL] Reused for {certificate_type}: {self.shared_nmkpl}")

        # FIELDS TAMBAHAN
        for field_name in self.OPTIONAL_FIELDS:
            if field_name not in metadata['extracted_fields']:
                metadata['extracted_fields'][field_name] = 'NOT FOUND'
                metadata['confidence_scores'][field_name] = 0.0
                metadata['extraction_status'][field_name] = 'MISSING_OPTIONAL'

        # QUALITY SCORE
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

    # SPLIT CERTIFICATE BUAT YG MULTIPLE CERT
    def _split_certificates(self, full_text: str, ocr_result: Dict) -> List[Dict]:
        certificates = []

        # CERT PATTERNS
        cert_patterns = [
            (r'SERTIFIKAT LAMBUNG\s+CERTIFICATET? OF LAMBUNG\s+No\.', 'lambung'), # HULL
            (r'SERTIF[IT]KAT MESIN\s+Certificate of Machinery\s+No', 'mesin'), # MACH
            (r'SERTIFIKAT\s+NASIONAL\s+MUAT|NATIONAL\s+LOAD\s+CERTIFICATE', 'muat') # LOADLINE
        ]

        # CARI PATTERN
        boundaries = []
        for pattern, cert_type in cert_patterns:
            matches = list(re.finditer(pattern, full_text, re.IGNORECASE))
            for match in matches:
                is_duplicate = False
                for existing in boundaries:
                    if abs(match.start() - existing['start']) < 50:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    boundaries.append({
                        'start': match.start(),
                        'type': cert_type,
                        'pattern': pattern
                    })

        boundaries.sort(key=lambda x: x['start'])

        if len(boundaries) <= 1:
            return [{'type': 'unknown', 'ocr_result': ocr_result}]

        for i, boundary in enumerate(boundaries):
            start_pos = boundary['start']
            end_pos = boundaries[i + 1]['start'] if i + 1 < len(boundaries) else len(full_text)

            # Extract certificate text
            cert_text = full_text[start_pos:end_pos]

            # Create new OCR result for this certificate
            cert_ocr_result = {
                'full_text': cert_text,
                'words': [],
                'lines': []
            }

            certificates.append({
                'type': boundary['type'],
                'ocr_result': cert_ocr_result
            })

        logger.info(f"Split document into {len(certificates)} certificates: {[c['type'] for c in certificates]}")
        return certificates

    # DETECT TEMPLATE
    def _detect_template(self, full_text: str) -> Optional[str]:
        best_match = None
        best_score = 0

        for template_name, template_config in self.templates.items():
            keywords = template_config.get('detection_keywords', [])
            score = 0

            for keyword in keywords:
                if keyword.lower() in full_text:
                    score += 1

            if template_name == 'template_muat' and score > 0:
                score += 10

            if score > best_score:
                best_score = score
                best_match = template_name

        return best_match if best_score > 0 else None

    # MAP CERT TYPE
    def _map_certificate_type(self, raw_value: Optional[str], full_text: str) -> Optional[str]:
        if not raw_value:
            return raw_value

        raw_lower = raw_value.lower()

        # Special handling untuk template_muat: check nasional vs internasional
        if self.current_template_name == 'template_muat':

            # PM 39
            if re.search(r'PM\s*39', full_text, re.IGNORECASE):
                logger.info("Detected PM 39 regulation -> PM39")
                return 'PM39'

            # Untuk Loadline Nasional
            if 'garis muat nasional' in full_text.lower():
                logger.info("Detected: Garis Muat Nasional -> PM39")
                return 'PM39'

            # Untuk Loadline Internasional
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

            # FALLBACK (AMAN)
            logger.info("Detected: Muat (fallback) -> PM39")
            return 'PM39'

        # Template hull/mach pake cert_type_map
        for key, code in self.cert_type_mapping.items():
            if key.lower() in raw_lower or key.lower() in full_text:
                logger.info(f"Mapped '{raw_value}' -> '{code}'")
                return code

        # Kalo gk nemu, pake yang original
        logger.debug(f"No mapping found for '{raw_value}', keeping original")
        return raw_value

    # EXTRACT TEXT LINE DARI OCR UNTUK DICT PARSING
    def _get_text_lines(self, ocr_result: Dict) -> List[Dict]:
        lines = []

        for line in ocr_result.get('lines', []):
            line_data = {
                'text': line.get('text', ''),
                'words': line.get('words', []),
                'geometry': line.get('geometry')
            }
            lines.append(line_data)

        if not lines:
            full_text = ocr_result.get('full_text', '')
            for text_line in full_text.split('\n'):
                if text_line.strip():
                    lines.append({'text': text_line.strip(), 'words': [], 'geometry': None})

        return lines

    # EXTRACT VALUE UNTUK FIELD
    def _extract_field(self, field_name, field_config, lines, ocr_result):
        labels = field_config.get("labels", [])
        pattern = field_config.get("pattern")
        full_text = ocr_result.get("full_text", "")

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
            cert_type = self.current_template_name.replace("template_", "").lower() if self.current_template_name else "unknown"
            extracted_value, confidence, allow_reuse = self._extract_nmkpl(
                full_text,
                lines,
                cert_type
            )

            # Normalisasi kalo hasilnya tidak sesuai keinginan
            if extracted_value:
                value = self._normalize_nmkpl(extracted_value)
            else:
                value = None

            # Kalau value nya null pake dari reuse
            if value is None and allow_reuse:
                return None, 0.0

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

        # LABEL-BASED
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
                        return match.group(0).strip()
            except re.error:
                continue

        return None

    # FORMAT DATE
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

    # FORMAT NUMBER
    def _guess_number(self, text: str):
        matches = re.findall(r'\b\d{4,7}\b', text)
        if matches:
            return max(set(matches), key=matches.count)
        return None

    # EXTRACT VALUE DARI LABEL TEXT
    def _extract_by_label(self, labels: List[str], lines: List[Dict],
                         pattern: Optional[str] = None) -> Tuple[Optional[str], float]:

        if not labels:
            return None, 0.0

        best_match = None
        best_confidence = 0.0

        for line_idx, line in enumerate(lines):
            line_text = line['text']

            # Check setiap label
            for label in labels:
                if len(label) <= 2:
                    pattern_word = r'\b' + re.escape(label) + r'\b'
                    if not re.search(pattern_word, line_text, re.IGNORECASE):
                        continue

                # Exact match
                if label.lower() in line_text.lower():
                    # Extract value dari line yang sama
                    value, conf = self._extract_value_from_line(line_text, label, pattern)

                    # Extract value dari line selanjutnya
                    if (value is None or conf < 0.5) and line_idx + 1 < len(lines):
                        next_line = lines[line_idx + 1]['text']
                        value_next, conf_next = self._extract_value_from_next_line(next_line, pattern)
                        if conf_next > conf:
                            value, conf = value_next, conf_next * 0.9

                    if conf > best_confidence:
                        best_match = value
                        best_confidence = conf

                # Fuzzy match (buat labels panjang)
                elif self.use_fuzzy_matching and len(label) > 3:
                    ratio = fuzz.partial_ratio(label.lower(), line_text.lower())
                    if ratio >= self.fuzzy_threshold:
                        value, conf = self._extract_value_from_line(line_text, label, pattern)

                        # Ambil Value di Next Line untuk labels panjang
                        if (value is None or conf < 0.5) and line_idx + 1 < len(lines):
                            next_line = lines[line_idx + 1]['text']
                            value_next, conf_next = self._extract_value_from_next_line(next_line, pattern)
                            if conf_next > conf:
                                value, conf = value_next, conf_next * 0.85

                        # Score confidence dari fuzzy match ratio
                        conf = conf * (ratio / 100.0)
                        if conf > best_confidence:
                            best_match = value
                            best_confidence = conf

        return best_match, best_confidence

    # Extract Value dari baris selanjutnya
    def _extract_value_from_next_line(self, line_text: str,
                                      pattern: Optional[str] = None) -> Tuple[Optional[str], float]:

        if not line_text or not line_text.strip():
            return None, 0.0

        value_text = line_text.strip()

        # MATCH KE PATTERN
        if pattern:
            for pat in self._iter_patterns(pattern):
                match = re.search(pat, value_text, re.IGNORECASE)
                if match:
                    matched_value = match.group(0).strip()
                    matched_value = self._clean_extracted_value(matched_value)
                    return matched_value, 0.9

        # Split pke simbol
        for delimiter in [',', ';', '\t', '  ']:
            if delimiter in value_text:
                value_text = value_text.split(delimiter)[0].strip()
                break

        words = value_text.split()
        if words:
            extracted = ' '.join(words[:10]).strip()
            extracted = self._clean_extracted_value(extracted)
            return extracted, 0.75

        return None, 0.0

    # EXTRACT VALUE DARI BARIS
    def _extract_value_from_line(self, line_text: str, label: str,
                                 pattern: Optional[str] = None) -> Tuple[Optional[str], float]:

        # Common separators between label and value
        separators = [':', '=', '-', '|', ',']

        # Cari label position
        label_lower = label.lower()
        line_lower = line_text.lower()

        # Cari label position
        label_pos = line_lower.find(label_lower)
        if label_pos == -1:
            return None, 0.0

        # Ambil text setelah label
        value_text = line_text[label_pos + len(label):].strip()

        # Hapus leading separators
        for sep in separators:
            value_text = value_text.lstrip(sep).strip()

        # Klo gk ada value return none
        if not value_text:
            return None, 0.0

        # Match Pattern
        if pattern:
            for pat in self._iter_patterns(pattern):
                match = re.search(pat, value_text, re.IGNORECASE)
                if match:
                    matched_value = match.group(0).strip()
                    matched_value = self._clean_extracted_value(matched_value)
                    return matched_value, 0.95
                else:
                    for delimiter in [',', ';', '\n', '\t', '  ']:
                        if delimiter in value_text:
                            value_text = value_text.split(delimiter)[0].strip()
                            break

                # Return beberapa kata awal
                words = value_text.split()
                if words:
                    extracted = ' '.join(words[:10]).strip()
                    extracted = self._clean_extracted_value(extracted)
                    return extracted, 0.6
        else:
            for delimiter in [',', ';', '\n', '\t']:
                if delimiter in value_text:
                    value_text = value_text.split(delimiter)[0].strip()
                    break

            words = value_text.split()
            if words:
                extracted = ' '.join(words[:10]).strip()
                extracted = self._clean_extracted_value(extracted)
                return extracted, 0.8

        return None, 0.0
    
    # EXTRACT VALUE UNTUK FIELD NMKPL
    def _extract_nmkpl(
            self,
            full_text: str,
            lines: List[Dict],
            certificate_type: str
    ) -> Tuple[Optional[str], float, bool]:

        import re

        # MUAT / ILLC / PM
        if certificate_type in ("muat", "illc", "pm39", "p88"):
            return None, 0.0, True

        # HULL & MACH
        if not full_text:
            return None, 0.0, False

        text = re.sub(r'\s+', ' ', full_text).upper()

        # PATTERN NMKPL
        patterns_direct = [
            # "Nama Kapal"
            r'Nama\s+Kapal\s*[:=\-]?\s*([A-Z0-9][A-Z0-9\-\s]{2,39}?)(?:\s+(?:Ex\.|No\.|Register|Tanda|IMO|Nomor)|\n|$)',
            # "NAME OF SHIP"
            r'NAME\s+OF\s+SHIP\s*[:=\-]?\s*([A-Z0-9][A-Z0-9\-\s]{2,39}?)(?:\s+(?:Ex\.|No\.|Register)|\n|$)',
            # "Ex."
            r'^([A-Z][A-Z0-9\-\s]{2,39}?)\s+Ex\.\s+',
        ]
        
        for pat in patterns_direct:
            try:
                m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
                if m:
                    candidate = m.group(1).strip()
                    candidate = re.sub(r'\s+(EX\.|NO\.|REGISTER|TANDA|IMO|NOMOR).*$', '', candidate)
                    candidate = candidate.strip()
                    cleaned = self._clean_extracted_value(candidate)
                    if cleaned and 3 <= len(cleaned) <= 40:
                        processed = self._postprocess_nmkpl(cleaned, text)
                        if processed:
                            return processed, 0.95, False
            except Exception:
                pass

        # Line-by-line scan label
        label_keywords = ["nama kapal", "name of ship", "vessel name", "ship's name"]
        
        for i, line in enumerate(lines or []):
            line_text = (line.get("text", "") or "").strip()
            line_lower = line_text.lower()
            
            # check baris yang ada pattern
            for kw in label_keywords:
                if kw in line_lower:
                    # extract value dari baris yang sama
                    parts = re.split(r'[:=\-]', line_text)
                    if len(parts) > 1:
                        candidate = parts[-1].strip()
                        if candidate and 3 <= len(candidate) <= 40:
                            cleaned = self._clean_extracted_value(candidate)
                            if cleaned:
                                processed = self._postprocess_nmkpl(cleaned, text)
                                if processed:
                                    return processed, 0.93, False
                    
                    # extract value dari baris selanjutnya
                    if i + 1 < len(lines):
                        next_line = (lines[i + 1].get("text", "") or "").strip()
                        if next_line and 3 <= len(next_line) <= 40:
                            if not re.search(r'(ex\.|tanda|no\.|register|imo|gt|panjang|type)', next_line, re.IGNORECASE):
                                cleaned = self._clean_extracted_value(next_line)
                                if cleaned:
                                    processed = self._postprocess_nmkpl(cleaned, text)
                                    if processed:
                                        return processed, 0.90, False
                    break
                    break

        try:
            m_imo = re.search(r'([A-Z][A-Z0-9\-\s]{2,50}?)\s+(?:NO\.?\s*IMO|IMO)\b', text, re.IGNORECASE)
            if m_imo:
                candidate = m_imo.group(1).strip()
                cleaned = self._clean_extracted_value(candidate)
                if cleaned:
                    processed = self._postprocess_nmkpl(cleaned, text)
                    if processed:
                        return processed, 0.94, False
        except Exception:
            pass

        lines_list = lines or []
        for i, line in enumerate(lines_list):
            if i >= 15:
                break
            
            line_text = (line.get("text", "") or "").strip()

            if not line_text or len(line_text) < 4 or len(line_text) > 50:
                continue

            if re.search(r'(SERTIFIKAT|KLASIFIKASI|LAMBUNG|MESIN|MUAT|INDONESIA|REGISTER|IMO|BIRO|No\.|Nomor)', line_text, re.IGNORECASE):
                continue

            if re.match(r'^\d', line_text):
                continue

            if re.match(r'^[A-Z][A-Z0-9\-\s]{3,49}$', line_text):
                word_count = len(re.findall(r'\b\w+\b', line_text))
                if 1 <= word_count <= 4:
                    num_count = sum(1 for c in line_text if c.isdigit())
                    if num_count <= len(line_text) * 0.15:
                        if not re.match(r'^\d+', line_text):
                            cleaned = self._clean_extracted_value(line_text)
                            if cleaned and len(cleaned) >= 3:
                                processed = self._postprocess_nmkpl(cleaned, text)
                                if processed:
                                    return processed, 0.75, False

        return None, 0.0, False

    # Normalize nmkpl (biasanya ada kata yang ngikut)
    def _normalize_nmkpl(self, value: Optional[str]) -> Optional[str]:
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

    # validasi nmkpl
    def _is_valid_nmkpl(self, value: str) -> bool:
        if not value:
            return False

        v = value.upper()

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

        # panjang nama kapal
        if not (3 <= len(v) <= 40):
            return False

        # hanya huruf / angka / spasi / dash
        if not re.match(r'^[A-Z0-9\- ]+$', v):
            return False

        return True

    def _postprocess_nmkpl(self, candidate: str, full_text: str) -> Optional[str]:
        """
        Post-process NMKPL candidates:
        - Reject REV-like artifacts (e.g., '2024REV', '2013REVO')
        - Try to expand short single-token candidates by including adjacent uppercase tokens
        - Validate final candidate with _is_valid_nmkpl
        """
        if not candidate:
            return None

        cand = candidate.upper().strip()

        try:
            m_label = re.search(r'NAMA.{0,12}KAPAL', full_text, re.IGNORECASE)
            if m_label:
                pos = m_label.end()
                snippet = full_text[pos:pos+120]
                snippet = re.sub(r'^[\s:\-\.:]+', '', snippet)
                candidate_label = re.split(r'(?:No\.?\s*IMO|IMO|NO\.|REGISTER|TANDA|EX\.|F31|Certificat|Certificate)', snippet, 1, flags=re.IGNORECASE)[0]
                candidate_label = self._clean_extracted_value(candidate_label)
                if candidate_label:
                    cand_label = candidate_label.upper().strip()
                    if self._is_valid_nmkpl(cand_label):
                        logger.debug(f"[NMKPL] override tolerant 'Nama Kapal' -> {cand_label}")
                        return cand_label
        except Exception:
            pass

        # Reject common REV artifacts or year+REV patterns
        if re.search(r'\b\d{3,4}\s*REV\b', cand) or re.search(r'\bREV\d{0,2}\b', cand) or re.match(r'^\d{3,4}REV', cand):
            logger.debug(f"[NMKPL] rejected as REV-like: {cand}")
            return None

        # Reject values that are mostly numeric or too-short tokens like '2013' or 'STA'
        if re.match(r'^\d{3,}$', cand):
            return None

        # If candidate is a single short token (likely truncated, e.g. 'TRANS'), try to expand
        tokens = re.findall(r"\b[A-Z][A-Z0-9\-]{1,}\b", full_text.upper())
        if len(cand.split()) == 1 and len(cand) <= 6:
            for idx, t in enumerate(tokens):
                if t == cand:
                    # attempt to append up to 3 following tokens that look like name parts
                    parts = [t]
                    for j in range(1, 4):
                        if idx + j < len(tokens):
                            nxt = tokens[idx + j]
                            # skip if nxt looks like REV or label or numeric-only
                            if re.search(r'REV|EX|NO|REGISTER|TANDA|IMO', nxt):
                                break
                            if re.match(r'^\d+$', nxt):
                                break
                            parts.append(nxt)
                            # try short expansions first (1-2 tokens)
                            candidate_try = ' '.join(parts)
                            if self._is_valid_nmkpl(candidate_try):
                                return candidate_try

        # Final validation
        if self._is_valid_nmkpl(cand):
            return cand

        return None

    # EXTRACT TGL_SERT
    def _extract_issue_date(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        # Pattern: "Dikeluarkan di JAKARTA.tanggal XX XXX XXXX"
        pattern = r'Dikeluarkan\s+di\.?\s+[A-Z]+\.?\s*tanggal\s+(\d{2,3})\s?([A-Z]{3,9})\s?(\d{4})'
        match = re.search(pattern, full_text, re.IGNORECASE)

        if match:
            day = match.group(1)
            month = match.group(2)
            year = match.group(3)

            # Fix OCR Error klo day nya 3 angka
            if len(day) == 3 and day.startswith('0'):
                # gnti jadi 2 angka
                day = day[:2]
            elif len(day) == 2 and int(day) > 31:
                day = '0' + day[1]

            # Convert bulan ke angka
            month_map = {
                'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
                'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
                'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11', 'DESEMBER': '12'
            }

            if month.upper() in month_map:
                date_str = f"{year}/{month_map[month.upper()]}/{day.zfill(2)}"
                logger.info(f"Extracted issue date: {date_str}")
                return date_str, 0.95

        # Pattern 2: "Tanggal 08 APRIL 2024" (untuk Muat)
        pattern2 = r'(?:NMKPL|JAKARTA)\s+Tanggal\s+(\d{1,2})\s+([A-Z]{3,9})\s+(\d{4})'
        match = re.search(pattern2, full_text, re.IGNORECASE)

        if match:
            day = match.group(1)
            month = match.group(2)
            year = match.group(3)

            # Convert bulan ke angka
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

    # NORMALIZE LOKASI SURVEY
    def _normalize_lokasi_survey(self, raw_value: Optional[str]) -> Optional[str]:
        if not raw_value:
            return None

        raw = raw_value.upper()

        # Daftar kota utama branch BKI
        kota_list = [
            "JAKARTA", "SEMARANG", "SURABAYA", "BATAM", "BELAWAN",
            "MAKASSAR", "BALIKPAPAN", "PALEMBANG", "PONTIANAK",
            "BANJARMASIN", "TANJUNG PRIOK", "CIREBON", "BITUNG",
            "SORONG", "AMBON", "SAMARINDA", "SINGAPORE", "JAMBI",
            "PEKANBARU", "BANTEN"
        ]

        for kota in kota_list:
            if kota in raw:
                return kota

        return None

    # EXTRACT DIVISI SURVEYOR
    def _extract_surveyor(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
        # Pattern 1: "oleh Surveyor pada"
        pattern1 = r'(Surveyor|Pengawas)(?:\s+[A-Z\s]+)?'
        match = re.search(pattern1, full_text, re.IGNORECASE)

        if match:
            surveyor = match.group(1)
            logger.info(f"Extracted surveyor (pattern 1): {surveyor}")
            return match.group(1), 0.95

        # Pattern 2: "di {lokasi_survey}"
        pattern2 = r'di\s+[A-Z\s&]+\s+(Pengawas|Surveyor)\s+([A-Z\s]+)'
        match = re.search(pattern2, full_text)

        if match:
            surveyor = match.group(1)
            logger.info(f"Extracted surveyor (pattern 2): {surveyor}")
            return surveyor, 0.95

        # Pattern 3: buat muat langsung default surveyor
        if 'SERTIFIKAT NASIONAL MUAT' in full_text or 'National Load Certificate' in full_text:
            # Check if there's "Pengawas Operasional" or similar
            if 'Pengawas Operasional' in full_text or 'Pengawas Bisnis' in full_text:
                logger.info(f"Extracted surveyor (Muat default): Surveyor")
                return "Surveyor", 0.90

        return None, 0.0

    # EXTRACT TGL_SURVEY1
    def _extract_survey_date1(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:

        month_map = {
            'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
            'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
            'SEPTEMBER': '09', 'OKTOBER': '10',
            'NOVEMBER': '11', 'NOPEMBER': '11',
            'DESEMBER': '12'
        }

        text = re.sub(r'\s+', ' ', full_text.upper())

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

        fallback = r'(PADAT|PADA)\s+TANGGAL\s+(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})'
        m = re.search(fallback, text)

        if m:
            day = m.group(2).zfill(2)
            month = m.group(3).zfill(2)
            year = m.group(4)
            date_str = f"{year}-{month}-{day}"
            logger.info(f"Extracted TGL_SURVEY1 (FALLBACK): {date_str}")
            return date_str, 0.95

        try:
            range_pat = r'(\d{1,2}\s*[./\-\s]\s*\d{1,2}\s*[./\-\s]\s*\d{2,4})\s*(?:S/?D|S\/D|SD|SAMPai|SAMPai|SAMPaI)\s*(\d{1,2}\s*[./\-\s]\s*\d{1,2}\s*[./\-\s]\s*\d{2,4})'
            m2 = re.search(range_pat, full_text, re.IGNORECASE)
            if m2:
                start = m2.group(1)
                parts = re.split(r'[./\-\s]+', start)
                if len(parts) >= 3:
                    d = parts[0].zfill(2)
                    mo = parts[1].zfill(2)
                    y = parts[2]
                    if len(y) == 2:
                        y = '20' + y
                    date_str = f"{y}-{mo}-{d}"
                    logger.info(f"Extracted TGL_SURVEY1 (range robust): {date_str}")
                    return date_str, 0.93
        except Exception:
            pass

        return None, 0.0

    # EXTRACT TGL_SURVEY2
    def _extract_survey_date2(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:
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

    # EXTRACT TGL_BERLAKU
    def _extract_valid_date(self, full_text: str, lines: List[Dict]) -> Tuple[Optional[str], float]:

        month_map = {
            'JANUARI': '01', 'FEBRUARI': '02', 'MARET': '03', 'APRIL': '04',
            'MEI': '05', 'JUNI': '06', 'JULI': '07', 'AGUSTUS': '08',
            'SEPTEMBER': '09', 'OKTOBER': '10', 'NOVEMBER': '11',
            'NOPEMBER': '11',  # OCR typo
            'DESEMBER': '12'
        }

        # PATTERN 1 — berlaku sampai 17 NOPEMBER 2021
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

        # PATTERN 2 — berlaku sampai s/d 17.11.2021
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

    # EXTRACT TGL_SERT
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

    # EXTRACT MEMO1
    def _extract_pembaruanke(self, text): # EXTRACT PEMBARUAN KE (HULL)
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

    def _extract_noimo(self, text): # EXTRACT NO IMO
        m = re.search(r'No\.?\s*IMO\s*[:\-]?\s*(\d{6,7})', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_exkpl(self, text): # EXTRACT EX KPL
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

    def _extract_jenis(self, text): # EXTRACT JENIS KAPAL
        m = re.search(
            r'kapal\s+([A-Z ]{5,40})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None

        return f"KAPAL {m.group(1).strip()}"

    def _extract_brt(self, text): # EXTRACT BRT
        m = re.search(r'Tonase\s+Kotor\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_nrt(self, text): # EXTRACT NRT
        m = re.search(r'Tonase\s+Bersih\s*[:\-]?\s*(\d+)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_nmgal(self, text): # EXTRACT NMGAL
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

    def _extract_lgal(self, text): # EXTRACT LGAL
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

    def _extract_thba(self, text): # EXTRACT THBA
        m = re.search(
            r'Tahun\s+Bangun\s*[:\-]?\s*(\d{4})',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_kota(self, text): # EXTRACT KOTA
        m = re.search(
            r'Pelabuhan\s+Pendaftaran\s+([A-Z\s]{3,40})',
            text,
            re.IGNORECASE
        )
        return m.group(1).strip() if m else None

    def _extract_flag(self, text): # EXTRACT BENDERA
        m = re.search(r'Bendera\s*[:\-]?\s*([A-Z\s]+)', text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _extract_nama1(self, text): # EXTRACT NAMA PEMILIK
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

    def _extract_notasi(self, text): # EXTRACT PLAT
        m = re.search(r'✠\s*A100\s*P\s*Tug', text)
        return "A100 P Tug" if m else None

    def _extract_tandatangan(self, text): # EXTRACT TTD
        m = re.search(r'\n([A-Z\s]+)\nNUP', text)
        return m.group(1).strip() if m else None

    def _extract_nup(self, text): # EXTRACT NUP
        m = re.search(r'NUP\s*[:\-]?\s*(\d{4,6}\-KI)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_tgl_lastdok(self, text): # EXTRACT TGL_BERLAKU
        m = re.search(
            r'(\d{1,2})\s+SEPTEMBER\s+(\d{4})',
            text,
            re.IGNORECASE
        )
        if not m:
            return None
        day = m.group(1).zfill(2)
        return f"{m.group(2)}-09-{day}"

    def _extract_periode_poros(self, text): # EXTRACT PERIODE POROS (MESIN)
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

    def _extract_sme(self, text): # EXTRACT SME
        m = re.search(
            r'(?:main\s+engine|mesin\s+utama).*?(\d+)\s*\(?(?:dua|tiga|empat|lima)?\)?\s*buah',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_ehpme(self, text): # EXTTRACT EHPME
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

    def _extract_rpmme(self, text): # EXTRACT RPMME
        m = re.search(
            r'(\d{3,5})\s*rpm',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_serime(self, text): # EXTRACT SERIME
        m = re.search(
            r'No\.?\s*Mesin\s*[:\-]?\s*([A-Z0-9\-]+)',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_smb(self, text): # EXTRACT SMB
        m = re.search(
            r'(?:auxiliary\s+engine|mesin\s+bantu).*?(\d+)\s*(?:buah|unit)?',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    # EXTRACT MEM01
    def _extract_call(self, text): # EXTRACT TANDA PENGENAL
        m = re.search(
            r'nomor\s+atau\s+huruf\s+pengenal\s*[:\-]?\s*([A-Z0-9]{2,10})',
            text,
            re.IGNORECASE
        )
        return m.group(1).upper() if m else None

    def _extract_panjang(self, text): # EXTRACT PANJANG
        m = re.search(
            r'panjang\s*\(?L\)?\s*[:\-]?\s*([\d]+(?:\.\d{1,2})?)',
            text,
            re.IGNORECASE
        )
        return m.group(1) if m else None

    def _extract_tipe(self, text): # EXTRACT TIPE KAPAL
        m = re.search(
            r'tipe\s+kapal\s*[:\-]?\s*([A-Z])\b',
            text,
            re.IGNORECASE
        )
        return m.group(1).upper() if m else None

    def _extract_ll(self, text, code): # EXTRACT LL
        m = re.search(rf'(\d+)\s*mm\s*\({code}\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_ts(self, text): # EXTRACT TS
        m = re.search(r'([\d.,]+)\s*mm\s*\(T\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_s66(self, text): # EXTRACT S66
        m = re.search(r'([\d.,]+)\s*mm\s*\(S\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_sw(self, text): # EXTRACT SW
        m = re.search(r'([\d.,]+)\s*mm\s*\(W\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_swna(self, text): # EXTRACT SWNA
        m = re.search(r'([\d.,]+)\s*mm\s*\(WNA\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lss(self, text): # EXTRACT LSS
        m = re.search(r'([\d.,]+)\s*mm\s*\(LS\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslt(self, text): # EXTRACT LSLT
        m = re.search(r'([\d.,]+)\s*mm\s*\(LT\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslw(self, text): # EXTRACT LSLW
        m = re.search(r'([\d.,]+)\s*mm\s*\(LW\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_lslwna(self, text): # EXTRACT LSLWNA
        m = re.search(r'([\d.,]+)\s*mm\s*\(LWNA\)', text, re.IGNORECASE)
        return m.group(1) if m else None

    def _extract_jn_kapal(self, text): # EXTRACT JENIS KAPAL
        if re.search(r'lambung\s+timbul\s+kayu', text, re.IGNORECASE):
            return "Kayu"
        if re.search(r'lambung\s+timbul', text, re.IGNORECASE):
            return "Non Kayu"
        return None

    # EXTRACT JENIS_SURVEY
    def _extract_jenis_survey(
            self,
            full_text: str,
            lines: List[Dict]
    ) -> Tuple[Optional[str], float]:

        if not full_text:
            return None, 0.0

        import re

        text = re.sub(r'\s+', ' ', full_text.upper())

        # BKI STANDARD JENIS_SURVEY
        patterns = [
            (r'SURVEY\s+PEMBARUAN\s+KLA[SZ]', 'Survey Pembaruan Klas'),
            (r'SURVEY\s+PENERIMAAN\s+KLA[SZ]\s+KEMBALI', 'Survey Penerimaan Klas Kembali'),
            (r'SURVEY\s+PENERIMAAN\s+KLA[SZ]', 'Survey Penerimaan Klas'),
            (r'SURVEY\s+MODIFIKASI', 'Survey Modifikasi'),
            (r'PEMBARUAN\s+KLA[SZ]\s+DAN\s+MODIFIKASI', 'Pembaruan Klas dan Modifikasi'),

            # bilingual / formal
            (r'SURVEYED\s+FOR\s+CLASS\s+RENEWAL', 'Survey Pembaruan Klas'),
            (r'SURVEYED\s+FOR\s+REINSTATEMENT', 'Survey Penerimaan Klas Kembali'),

            # tahunan / berkala
            (r'PEMERIKSAAN\s+TAHUNAN', 'Pemeriksaan Tahunan'),
            (r'\bTAHUNAN\b', 'Pemeriksaan Tahunan'),
            (r'\bBERKALA\b', 'Pemeriksaan Berkala'),
        ]

        for pat, label in patterns:
            if re.search(pat, text):
                return label, 0.95

        # LINE-BASED CONTEXT
        for line in (lines or []):
            lt = (line.get("text") or "").upper()

            if "SURVEY" not in lt:
                continue

            for pat, label in patterns:
                if re.search(pat, lt):
                    return label, 0.9

            if "PEMBARUAN" in lt:
                return "Survey Pembaruan Klas", 0.75
            if "PENERIMAAN" in lt:
                return "Survey Penerimaan Klas", 0.75
            if "MODIFIK" in lt:
                return "Survey Modifikasi", 0.7

        return None, 0.0

    # EXTRACT MEM01 MUAT
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

    # EXTRACT MEMO1 HULL
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

    # EXTRACT MEM01 MACH
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

    # NORMALISASI TEXT MUAT
    def _normalize_muat_text(self, text: str) -> str:
        text = text.replace("\n", " ")
        text = re.sub(r'\s+', ' ', text)

        text = re.sub(
            r'(\d+)\s*mm\s*\(?\s*([A-Z]{1,3})\s*\)?',
            r'\1 mm (\2)',
            text,
            flags=re.IGNORECASE
        )

        return text

    # EXTRACT MEM01 MUAT
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

    # EXTRACT MEM01 (3 SERTIFIKAT)
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
        if not value:
            return value

        # Remove multiple spaces
        value = re.sub(r'\s{2,}', ' ', value)

        # Remove simbol
        value = value.rstrip('.,;:')

        # Remove whitespace
        value = value.strip()

        # Normalize date formats
        date_pattern = r'\d{1,2}[-/\s]\d{1,2}[-/\s]\d{2,4}'
        if re.match(date_pattern, value):
            # Spasi diganti dengan simbol /
            value = re.sub(r'[-\s]', '/', value)

        return value

    def _extract_by_pattern(self, pattern: Optional[str],
                           lines: List[Dict]) -> Tuple[Optional[str], float]:
        if not pattern:
            return None, 0.0

        all_matches = []

        for pat in self._iter_patterns(pattern):
            for line in lines:
                line_text = line['text']
                matches = re.finditer(pat, line_text, re.IGNORECASE)
                for match in matches:
                    matched_text = self._clean_extracted_value(match.group(0))
                    if matched_text:
                        all_matches.append(matched_text)

        if all_matches:
            all_matches.sort(key=len, reverse=True)
            return all_matches[0], 0.75

        return None, 0.0

    def _iter_patterns(self, pattern):
        if pattern is None:
            return []
        if isinstance(pattern, list):
            return pattern
        return [pattern]

    def _calculate_quality_score(self, metadata: Dict) -> float:
        total_fields = len(self.fields_config)
        if total_fields == 0:
            return 0.0

        successful = sum(1 for status in metadata['extraction_status'].values()
                        if status == 'SUCCESS')

        confidences = [conf for conf in metadata['confidence_scores'].values()
                      if conf > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        extraction_rate = successful / total_fields
        quality_score = (extraction_rate * 0.7) + (avg_confidence * 0.3)

        return round(quality_score, 3)

    def format_output(self, metadata: Dict, format_type: str = 'json') -> Any:
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

        else:
            import json
            return json.dumps(metadata, indent=2, ensure_ascii=False)

    def validate_extraction(self, metadata: Dict) -> Tuple[bool, List[str]]:
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
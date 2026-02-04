"""
OCR Engine Module using docTR
Handles text extraction from images and PDFs with high accuracy
"""

import os
import logging
from typing import List, Dict, Tuple, Union, Optional
import numpy as np
from pathlib import Path

# docTR imports
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from doctr.models.predictor import OCRPredictor

# Image processing
import cv2
from PIL import Image

logger = logging.getLogger(__name__)


class OCREngine:
    """
    High-accuracy OCR engine using docTR for text extraction
    """
    
    def __init__(self, config: Dict):
        """
        Initialize OCR engine with configuration
        
        Args:
            config: Configuration dictionary containing OCR settings
        """
        self.config = config
        self.ocr_config = config.get('ocr', {})
        self.preprocessing_config = config.get('preprocessing', {})
        
        # Initialize docTR model
        self.model = self._initialize_model()
        
        logger.info(f"OCR Engine initialized with detection: {self.ocr_config.get('detection_model')} "
                   f"and recognition: {self.ocr_config.get('recognition_model')}")
    
    def _initialize_model(self) -> OCRPredictor:
        """
        Initialize docTR OCR predictor model
        
        Returns:
            OCRPredictor instance
        """
        det_arch = self.ocr_config.get('detection_model', 'db_resnet50')
        reco_arch = self.ocr_config.get('recognition_model', 'crnn_vgg16_bn')
        pretrained = self.ocr_config.get('pretrained', True)
        assume_straight_pages = self.ocr_config.get('assume_straight_pages', True)
        straighten_pages = self.ocr_config.get('straighten_pages', False)
        preserve_aspect_ratio = self.ocr_config.get('preserve_aspect_ratio', True)
        symmetric_pad = self.ocr_config.get('symmetric_pad', True)
        
        # Create OCR predictor
        predictor = ocr_predictor(
            det_arch=det_arch,
            reco_arch=reco_arch,
            pretrained=pretrained,
            assume_straight_pages=assume_straight_pages,
            straighten_pages=straighten_pages,
            preserve_aspect_ratio=preserve_aspect_ratio,
            symmetric_pad=symmetric_pad
        )
        
        # Move to GPU if available and configured
        if self.ocr_config.get('use_gpu', True):
            try:
                import torch
                if torch.cuda.is_available():
                    predictor.to('cuda')
                    logger.info("Using GPU for OCR processing")
                else:
                    logger.info("GPU not available, using CPU")
            except Exception as e:
                logger.warning(f"Could not move model to GPU: {e}")
        
        return predictor
    
    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR accuracy
        
        Args:
            image: Input image as numpy array
            
        Returns:
            Preprocessed image
        """
        # Resize if needed
        max_width = self.preprocessing_config.get('max_width')
        max_height = self.preprocessing_config.get('max_height')
        
        if max_width or max_height:
            h, w = image.shape[:2]
            if max_width and w > max_width:
                ratio = max_width / w
                image = cv2.resize(image, (max_width, int(h * ratio)))
            if max_height and image.shape[0] > max_height:
                h, w = image.shape[:2]
                ratio = max_height / h
                image = cv2.resize(image, (int(w * ratio), max_height))
        
        # Enhance contrast
        if self.preprocessing_config.get('enhance_contrast', True):
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            image = cv2.merge([l, a, b])
            image = cv2.cvtColor(image, cv2.COLOR_LAB2BGR)
        
        # Denoise
        if self.preprocessing_config.get('denoise', False):
            image = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
        
        return image

    def detect_dataset_quality(self, image: np.ndarray) -> str:
        """
        Detect scan quality from image
        """
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

        # =========================
        # 1. Blur Detection
        # =========================
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

        # =========================
        # 2. Contrast Detection
        # =========================
        contrast_score = gray.std()

        logger.info(
            f"Scan quality metrics | Blur: {blur_score:.2f} | Contrast: {contrast_score:.2f}"
        )

        # =========================
        # THRESHOLD EMPIRIS
        # =========================
        if blur_score < 100 or contrast_score < 40:
            return "scan_poor"

        return "scan_good"

    def get_parsing_threshold(self, dataset_quality: str) -> Dict:
        parsing_cfg = self.config.get("parsing", {})

        return parsing_cfg.get(
            dataset_quality,
            parsing_cfg.get("default", {
                "confidence_threshold": 0.45,
                "fuzzy_threshold": 80
            })
        )

    def extract_text_from_image(self, image_path: Union[str, Path]) -> Dict:
        """
        Extract text from a single image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary containing extracted text and metadata
        """
        logger.info(f"Processing image: {image_path}")
        
        # Load and preprocess image
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        image = self.preprocess_image(image)
        
        # Convert to RGB for docTR
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Run OCR
        result = self.model([image_rgb])
        
        # Extract structured data
        extracted_data = self._parse_doctr_result(result, image.shape)
        extracted_data['source_file'] = str(image_path)
        extracted_data['source_type'] = 'image'
        
        return extracted_data

    def extract_text_from_pdf(self, pdf_path: Union[str, Path]) -> Dict:
        """
        Extract text from PDF file

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary containing extracted text and metadata from all pages
        """
        logger.info(f"Processing PDF: {pdf_path}")

        # Load PDF using docTR's DocumentFile
        doc = DocumentFile.from_pdf(str(pdf_path))

        page_img = doc[0]

        dataset_quality = self.detect_dataset_quality(doc[0])

        # Run OCR on all pages
        result = self.model(doc)

        # Extract structured data
        extracted_data = self._parse_doctr_result(result, None)
        extracted_data['source_file'] = str(pdf_path)
        extracted_data['source_type'] = 'pdf'
        extracted_data["dataset_quality"] = dataset_quality
        extracted_data["thresholds"] = self.get_parsing_threshold(dataset_quality)
        extracted_data['num_pages'] = len(result.pages)

        return extracted_data

    def _parse_doctr_result(self, result, image_shape: Optional[Tuple] = None) -> Dict:
        """
        Parse docTR result into structured format

        Args:
            result: docTR OCR result
            image_shape: Shape of the image (height, width, channels) for coordinate conversion

        Returns:
            Dictionary with structured text data
        """
        extracted_data = {
            'pages': [],
            'full_text': '',
            'words': [],
            'lines': [],
            'blocks': []
        }

        # Process each page
        for page_idx, page in enumerate(result.pages):
            page_data = {
                'page_number': page_idx + 1,
                'blocks': [],
                'text': ''
            }

            # Process each block
            for block in page.blocks:
                block_data = {
                    'lines': [],
                    'text': '',
                    'geometry': block.geometry if hasattr(block, 'geometry') else None
                }

                # Process each line
                for line in block.lines:
                    line_text = ''
                    line_words = []

                    # Process each word
                    for word in line.words:
                        word_data = {
                            'text': word.value,
                            'confidence': float(word.confidence),
                            'geometry': word.geometry
                        }

                        # Convert relative coordinates to absolute if image_shape provided
                        if image_shape is not None and word.geometry is not None:
                            h, w = image_shape[:2]
                            coords = word.geometry
                            word_data['bbox'] = {
                                'x1': int(coords[0][0] * w),
                                'y1': int(coords[0][1] * h),
                                'x2': int(coords[1][0] * w),
                                'y2': int(coords[1][1] * h)
                            }

                        line_words.append(word_data)
                        line_text += word.value + ' '

                        # Add to global words list
                        extracted_data['words'].append(word_data)

                    line_data = {
                        'text': line_text.strip(),
                        'words': line_words,
                        'geometry': line.geometry if hasattr(line, 'geometry') else None
                    }

                    block_data['lines'].append(line_data)
                    block_data['text'] += line_text

                    # Add to global lines list
                    extracted_data['lines'].append(line_data)

                page_data['blocks'].append(block_data)
                page_data['text'] += block_data['text'] + '\n'

                # Add to global blocks list
                extracted_data['blocks'].append(block_data)

            extracted_data['pages'].append(page_data)
            extracted_data['full_text'] += page_data['text'] + '\n'

        # Clean up full text
        extracted_data['full_text'] = extracted_data['full_text'].strip()

        return extracted_data

    def process_document(self, file_path: Union[str, Path]) -> Dict:
        """
        Process any document (image or PDF) and extract text

        Args:
            file_path: Path to document file

        Returns:
            Dictionary containing extracted text and metadata
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine file type and process accordingly
        extension = file_path.suffix.lower()

        if extension == '.pdf':
            return self.extract_text_from_pdf(file_path)
        elif extension in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
            return self.extract_text_from_image(file_path)
        else:
            raise ValueError(f"Unsupported file format: {extension}")

    def save_annotated_image(self, image_path: Union[str, Path],
                            ocr_result: Dict,
                            output_path: Union[str, Path],
                            show_confidence: bool = True):
        """
        Save image with bounding boxes around detected text

        Args:
            image_path: Path to original image
            ocr_result: OCR result dictionary
            output_path: Path to save annotated image
            show_confidence: Whether to show confidence scores
        """
        # Load image
        image = cv2.imread(str(image_path))
        if image is None:
            logger.error(f"Could not load image for annotation: {image_path}")
            return

        # Draw bounding boxes for each word
        for word in ocr_result.get('words', []):
            if 'bbox' in word:
                bbox = word['bbox']
                confidence = word.get('confidence', 0)

                # Color based on confidence (green = high, red = low)
                color = (0, int(255 * confidence), int(255 * (1 - confidence)))

                # Draw rectangle
                cv2.rectangle(image,
                            (bbox['x1'], bbox['y1']),
                            (bbox['x2'], bbox['y2']),
                            color, 2)

                # Add text and confidence
                if show_confidence:
                    label = f"{word['text']} ({confidence:.2f})"
                    cv2.putText(image, label,
                              (bbox['x1'], bbox['y1'] - 5),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Save annotated image
        cv2.imwrite(str(output_path), image)
        logger.info(f"Saved annotated image to: {output_path}")


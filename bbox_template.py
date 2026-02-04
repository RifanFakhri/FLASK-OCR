"""
Bounding Box Template System
Template-based extraction using bounding box coordinates
Similar to: https://github.com/nayyhah/PDFAutomation-OCRTextRecognition
"""

import logging
from typing import Dict, List, Optional, Tuple
import re

logger = logging.getLogger(__name__)


class BBoxTemplate:
    """
    Template for extracting fields based on bounding box coordinates
    """
    
    def __init__(self, template_config: Dict):
        """
        Initialize bbox templates
        
        Args:
            template_config: Template configuration with bbox regions
        """
        self.name = template_config.get('name', 'unknown')
        self.description = template_config.get('description', '')
        self.regions = template_config.get('regions', {})
        self.page_size = template_config.get('page_size', {'width': 1000, 'height': 1400})
        
        logger.info(f"BBox Template '{self.name}' initialized with {len(self.regions)} regions")
    
    def extract_from_ocr(self, ocr_result: Dict) -> Dict:
        """
        Extract fields from OCR result using bbox regions
        
        Args:
            ocr_result: OCR result with words and bboxes
            
        Returns:
            Dictionary with extracted fields
        """
        extracted = {}
        confidence_scores = {}
        
        words = ocr_result.get('words', [])
        
        for field_name, region_config in self.regions.items():
            bbox_region = region_config.get('bbox', {})
            pattern = region_config.get('pattern', None)
            
            # Extract text from bbox region
            text_in_region, confidence = self._extract_text_from_region(
                words, bbox_region, pattern
            )
            
            extracted[field_name] = text_in_region
            confidence_scores[field_name] = confidence
            
            logger.debug(f"Field '{field_name}': '{text_in_region}' (conf: {confidence:.2f})")
        
        return {
            'template_name': self.name,
            'extracted_fields': extracted,
            'confidence_scores': confidence_scores
        }
    
    def _extract_text_from_region(self, words: List[Dict], bbox_region: Dict, 
                                  pattern: Optional[str] = None) -> Tuple[Optional[str], float]:
        """
        Extract text from words that fall within bbox region
        
        Args:
            words: List of word dictionaries with bbox
            bbox_region: Region coordinates {x1, y1, x2, y2}
            pattern: Optional regex pattern to filter text
            
        Returns:
            Tuple of (extracted_text, confidence)
        """
        if not bbox_region:
            return None, 0.0
        
        x1 = bbox_region.get('x1', 0)
        y1 = bbox_region.get('y1', 0)
        x2 = bbox_region.get('x2', self.page_size['width'])
        y2 = bbox_region.get('y2', self.page_size['height'])
        
        # Find words within region
        words_in_region = []
        confidences = []
        
        for word in words:
            if 'bbox' not in word:
                continue
            
            word_bbox = word['bbox']
            word_x1 = word_bbox.get('x1', 0)
            word_y1 = word_bbox.get('y1', 0)
            word_x2 = word_bbox.get('x2', 0)
            word_y2 = word_bbox.get('y2', 0)
            
            # Check if word center is within region
            word_center_x = (word_x1 + word_x2) / 2
            word_center_y = (word_y1 + word_y2) / 2
            
            if (x1 <= word_center_x <= x2) and (y1 <= word_center_y <= y2):
                words_in_region.append(word)
                confidences.append(word.get('confidence', 0.0))
        
        if not words_in_region:
            return None, 0.0
        
        # Sort words by position (top to bottom, left to right)
        words_in_region.sort(key=lambda w: (w['bbox']['y1'], w['bbox']['x1']))
        
        # Combine text
        text = ' '.join([w['text'] for w in words_in_region])
        
        # Apply pattern if provided
        if pattern:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                text = match.group(0).strip()
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                return text, avg_confidence * 0.95  # High confidence for pattern match
            else:
                # Return text even if pattern doesn't match, but lower confidence
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
                return text, avg_confidence * 0.6
        
        # No pattern - return all text in region
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return text, avg_confidence * 0.85
    
    def visualize_regions(self, image_path: str, output_path: str):
        """
        Visualize templates regions on image
        
        Args:
            image_path: Path to input image
            output_path: Path to save visualization
        """
        try:
            import cv2
            import numpy as np
            
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Could not load image: {image_path}")
                return
            
            # Draw each region
            for field_name, region_config in self.regions.items():
                bbox = region_config.get('bbox', {})
                if not bbox:
                    continue
                
                x1 = bbox.get('x1', 0)
                y1 = bbox.get('y1', 0)
                x2 = bbox.get('x2', 100)
                y2 = bbox.get('y2', 100)
                
                # Random color for each region
                color = tuple(np.random.randint(0, 255, 3).tolist())
                
                # Draw rectangle
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                
                # Add label
                cv2.putText(image, field_name, (x1, y1 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            cv2.imwrite(output_path, image)
            logger.info(f"Saved templates visualization to: {output_path}")
            
        except ImportError:
            logger.warning("OpenCV not available for visualization")


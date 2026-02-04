"""
BBox Template Manager
Manages multiple bbox templates and auto-selects the best one
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from bbox_template import BBoxTemplate
from typing import Union

logger = logging.getLogger(__name__)

class BBoxTemplateManager:
    """
    Manager for multiple bbox templates
    Auto-selects best templates based on document content
    """
    
    def __init__(self, config: Union[str, Path, dict]):
        """
        Initialize templates manager
        
        Args:
            config_path: Path to bbox templates configuration file
        """
        self.templates = {}
        self.template_configs = {}

        if isinstance(config, (str, Path)):
            self.config_path = Path(config)
            self._load_templates_from_file()
        elif isinstance(config, dict):
            self.config_path = None
            self._load_templates_from_dict(config)
        else:
            raise TypeError("config must be path or dict")

    def _load_templates_from_file(self):
        if not self.config_path.exists():
            logger.warning(f"BBox templates config not found: {self.config_path}")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            self._load_templates_from_dict(config)

        except Exception as e:
            logger.error(f"Error loading bbox templates: {e}")

    def _load_templates_from_dict(self, config: dict):
        for key, value in config.items():
            if key.startswith('templates'):
                template_name = value.get('name', key)
                self.template_configs[template_name] = value
                self.templates[template_name] = BBoxTemplate(value)
                logger.info(f"Loaded bbox templates: {template_name}")

        logger.info(f"Loaded {len(self.templates)} bbox templates")

    def detect_template(self, ocr_result: Dict) -> Optional[str]:
        """
        Auto-detect which templates to use based on OCR result
        
        Args:
            ocr_result: OCR result with full_text and words
            
        Returns:
            Template name or None
        """
        if not self.templates:
            logger.warning("No bbox templates available")
            return None
        
        full_text = ocr_result.get('full_text', '').lower()
        
        # Strategy 1: Check for specific keywords
        # Template 1 = Nasional format (Indonesian keywords)
        # Template 2 = International format (English keywords)
        
        nasional_keywords = ['nasional', 'divisi', 'oleh', 'di jakarta', 'di surabaya']
        international_keywords = ['international', 'division', 'by', 'at singapore', 'certificate']
        
        nasional_score = sum(1 for kw in nasional_keywords if kw in full_text)
        international_score = sum(1 for kw in international_keywords if kw in full_text)
        
        if nasional_score > international_score:
            logger.info(f"Detected template1 (nasional) - score: {nasional_score}")
            return 'template1'
        elif international_score > nasional_score:
            logger.info(f"Detected template2 (international) - score: {international_score}")
            return 'template2'
        else:
            # Default to template1
            logger.info("No clear templates match, using template1 as default")
            return 'template1'
    
    def extract_with_template(self, template_name: str, ocr_result: Dict) -> Dict:
        """
        Extract fields using specific templates
        
        Args:
            template_name: Name of templates to use
            ocr_result: OCR result
            
        Returns:
            Extraction result
        """
        if template_name not in self.templates:
            logger.error(f"Template not found: {template_name}")
            return {
                'error': f'Template {template_name} not found',
                'extracted_fields': {},
                'confidence_scores': {}
            }
        
        template = self.templates[template_name]
        return template.extract_from_ocr(ocr_result)
    
    def extract_auto(self, ocr_result: Dict) -> Dict:
        """
        Auto-detect templates and extract fields
        
        Args:
            ocr_result: OCR result
            
        Returns:
            Extraction result with templates info
        """
        template_name = self.detect_template(ocr_result)
        
        if not template_name:
            return {
                'error': 'No templates detected',
                'template_name': None,
                'extracted_fields': {},
                'confidence_scores': {}
            }
        
        result = self.extract_with_template(template_name, ocr_result)
        result['auto_detected'] = True
        
        return result
    
    def get_available_templates(self) -> List[str]:
        """Get list of available templates names"""
        return list(self.templates.keys())
    
    def visualize_template(self, template_name: str, image_path: str, output_path: str):
        """
        Visualize templates regions on image
        
        Args:
            template_name: Name of templates
            image_path: Path to input image
            output_path: Path to save visualization
        """
        if template_name not in self.templates:
            logger.error(f"Template not found: {template_name}")
            return
        
        template = self.templates[template_name]
        template.visualize_regions(image_path, output_path)


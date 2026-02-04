"""
Test script for BBox Template System
Demonstrates how to use bbox templates for extraction
"""

import logging
import json
from pathlib import Path

from ocr_engine import OCREngine
from bbox_template_manager import BBoxTemplateManager
from config_loader import CONFIG, BBOX_CONFIG

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_bbox_template(image_path: str):
    """
    Test bbox templates extraction on an image
    
    Args:
        image_path: Path to test image
    """
    logger.info("="*60)
    logger.info("BBOX TEMPLATE TEST")
    logger.info("="*60)
    
    # Initialize OCR engine
    logger.info("Initializing OCR engine...")
    ocr_engine = OCREngine(CONFIG)
    
    # Initialize BBox templates manager
    logger.info("Initializing BBox templates manager...")
    bbox_manager = BBoxTemplateManager(BBOX_CONFIG)

    available_templates = bbox_manager.get_available_templates()
    logger.info(f"Available templates: {available_templates}")
    
    # Process image
    logger.info(f"\nProcessing image: {image_path}")
    ocr_result = ocr_engine.process_document(image_path)
    logger.info(f"OCR extracted {len(ocr_result.get('words', []))} words")
    
    # Auto-detect and extract
    logger.info("\n--- AUTO-DETECTION ---")
    result_auto = bbox_manager.extract_auto(ocr_result)
    
    logger.info(f"Template detected: {result_auto.get('template_name', 'N/A')}")
    logger.info(f"Auto-detected: {result_auto.get('auto_detected', False)}")
    
    logger.info("\nExtracted Fields:")
    for field, value in result_auto.get('extracted_fields', {}).items():
        confidence = result_auto.get('confidence_scores', {}).get(field, 0.0)
        logger.info(f"  {field:15s}: {str(value):30s} (conf: {confidence:.2f})")
    
    # Test each templates explicitly
    logger.info("\n" + "="*60)
    for template_name in available_templates:
        logger.info(f"\n--- TESTING {template_name.upper()} ---")
        result = bbox_manager.extract_with_template(template_name, ocr_result)
        
        logger.info(f"Template: {result.get('template_name', 'N/A')}")
        logger.info("\nExtracted Fields:")
        for field, value in result.get('extracted_fields', {}).items():
            confidence = result.get('confidence_scores', {}).get(field, 0.0)
            logger.info(f"  {field:15s}: {value:30s} (conf: {confidence:.2f})")
    
    # Save results
    output_dir = Path(__file__).parent / 'output'
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / 'bbox_test_result.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_auto, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n\nResults saved to: {output_file}")
    
    # Visualize templates
    logger.info("\n" + "="*60)
    logger.info("GENERATING TEMPLATE VISUALIZATIONS")
    logger.info("="*60)
    
    for template_name in available_templates:
        viz_output = output_dir / f'{template_name}_visualization.jpg'
        logger.info(f"Visualizing {template_name}...")
        bbox_manager.visualize_template(template_name, image_path, str(viz_output))
    
    logger.info("\n" + "="*60)
    logger.info("TEST COMPLETE")
    logger.info("="*60)


def compare_bbox_vs_label(image_path: str):
    """
    Compare bbox-based vs label-based extraction
    
    Args:
        image_path: Path to test image
    """
    from .text_parser import TextParser
    
    logger.info("="*60)
    logger.info("COMPARISON: BBOX vs LABEL-BASED")
    logger.info("="*60)
    
    # Initialize
    ocr_engine = OCREngine(CONFIG)
    bbox_manager = BBoxTemplateManager(BBOX_CONFIG)
    text_parser = TextParser(CONFIG)
    
    # Process
    logger.info(f"Processing: {image_path}")
    ocr_result = ocr_engine.process_document(image_path)
    
    # BBox extraction
    logger.info("\n--- BBOX-BASED EXTRACTION ---")
    bbox_result = bbox_manager.extract_auto(ocr_result)
    logger.info(f"Template: {bbox_result.get('template_name', 'N/A')}")
    
    # Label-based extraction
    logger.info("\n--- LABEL-BASED EXTRACTION ---")
    label_result = text_parser.parse(ocr_result)
    logger.info(f"Template: {label_result.get('template_used', 'N/A')}")
    logger.info(f"Quality: {label_result.get('overall_quality', 0.0):.2%}")
    
    # Compare
    logger.info("\n" + "="*60)
    logger.info("COMPARISON")
    logger.info("="*60)
    logger.info(f"{'Field':<15} {'BBox Result':<30} {'Label Result':<30}")
    logger.info("-"*75)
    
    bbox_fields = bbox_result.get('extracted_fields', {})
    label_fields = label_result.get('extracted_fields', {})
    
    all_fields = set(bbox_fields.keys()) | set(label_fields.keys())
    
    for field in sorted(all_fields):
        bbox_val = bbox_fields.get(field, 'N/A')
        label_val = label_fields.get(field, 'N/A')
        
        # Truncate long values
        bbox_val_str = str(bbox_val)[:28] if bbox_val else 'N/A'
        label_val_str = str(label_val)[:28] if label_val else 'N/A'
        
        match = "✓" if bbox_val == label_val else "✗"
        logger.info(f"{field:<15} {bbox_val_str:<30} {label_val_str:<30} {match}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python test_bbox_template.py <image_path> [--compare]")
        print("\nExamples:")
        print("  python test_bbox_template.py dataset/raw/sertifikat.jpg")
        print("  python test_bbox_template.py dataset/raw/sertifikat.jpg --compare")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if '--compare' in sys.argv:
        compare_bbox_vs_label(image_path)
    else:
        test_bbox_template(image_path)
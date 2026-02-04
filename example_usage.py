"""
Example Usage Script
Demonstrates how to use the OCR pipeline programmatically
"""
import copy
from pathlib import Path
from .ocr_engine import OCREngine
from .text_parser import TextParser
from config_loader import CONFIG


def example_single_image():
    """
    Example: Process a single image
    """
    print("="*60)
    print("EXAMPLE 1: Processing a single image")
    print("="*60)

    # Initialize components
    ocr_engine = OCREngine(CONFIG)
    text_parser = TextParser(CONFIG)
    
    # Process image
    image_path = 'dataset/raw/sample_invoice.jpg'  # Change to your image path
    
    if Path(image_path).exists():
        # Extract text with OCR
        print(f"\n1. Running OCR on: {image_path}")
        ocr_result = ocr_engine.extract_text_from_image(image_path)
        
        print(f"   - Extracted {len(ocr_result['words'])} words")
        print(f"   - Full text preview:")
        print(f"     {ocr_result['full_text'][:200]}...")
        
        # Parse metadata
        print(f"\n2. Parsing metadata...")
        metadata = text_parser.parse(ocr_result)
        
        print(f"   - Extraction quality: {metadata['overall_quality']:.2%}")
        print(f"\n3. Extracted fields:")
        for field_name, value in metadata['extracted_fields'].items():
            confidence = metadata['confidence_scores'][field_name]
            print(f"   - {field_name}: {value} (confidence: {confidence:.2%})")
        
        # Save annotated image
        output_path = 'output/example_annotated.jpg'
        Path('output').mkdir(exist_ok=True)
        ocr_engine.save_annotated_image(image_path, ocr_result, output_path)
        print(f"\n4. Saved annotated image to: {output_path}")
    else:
        print(f"Image not found: {image_path}")
        print("Please update the image_path variable with your image file")


def example_single_pdf():
    """
    Example: Process a single PDF
    """
    print("\n" + "="*60)
    print("EXAMPLE 2: Processing a PDF document")
    print("="*60)
    
    # Initialize components
    ocr_engine = OCREngine(CONFIG)
    text_parser = TextParser(CONFIG)
    
    # Process PDF
    pdf_path = 'dataset/raw/sample_document.pdf'  # Change to your PDF path
    
    if Path(pdf_path).exists():
        # Extract text with OCR
        print(f"\n1. Running OCR on: {pdf_path}")
        ocr_result = ocr_engine.extract_text_from_pdf(pdf_path)
        
        print(f"   - Processed {ocr_result['num_pages']} pages")
        print(f"   - Extracted {len(ocr_result['words'])} words")
        
        # Parse metadata
        print(f"\n2. Parsing metadata...")
        metadata = text_parser.parse(ocr_result)
        
        print(f"   - Extraction quality: {metadata['overall_quality']:.2%}")
        print(f"\n3. Extracted fields:")
        for field_name, value in metadata['extracted_fields'].items():
            confidence = metadata['confidence_scores'][field_name]
            print(f"   - {field_name}: {value} (confidence: {confidence:.2%})")
    else:
        print(f"PDF not found: {pdf_path}")
        print("Please update the pdf_path variable with your PDF file")


def example_custom_fields():
    """
    Example: Using custom field definitions
    """
    print("\n" + "="*60)
    print("EXAMPLE 3: Custom field definitions")
    print("="*60)

    config = copy.deepcopy(CONFIG)
    
    # Customize fields for specific document type
    config['parsing']['fields'] = {
        'order_id': {
            'labels': ['Order ID', 'Order Number', 'No. Order'],
            'pattern': r'ORD-\d{6}',
            'required': True
        },
        'customer_email': {
            'labels': ['Email', 'Customer Email'],
            'pattern': r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            'required': True
        },
        'total_price': {
            'labels': ['Total', 'Total Price', 'Amount'],
            'pattern': r'\$\d+\.\d{2}',
            'required': True
        }
    }
    
    print("\nCustom fields configured:")
    for field_name, field_config in config['parsing']['fields'].items():
        print(f"  - {field_name}: {field_config['labels']}")
    
    # Initialize with custom config
    ocr_engine = OCREngine(config)
    text_parser = TextParser(config)
    
    print("\nReady to process documents with custom field definitions!")


def example_batch_processing():
    """
    Example: Process multiple documents
    """
    print("\n" + "="*60)
    print("EXAMPLE 4: Batch processing")
    print("="*60)
    
    from .dataset_handler import DatasetHandler
    
    # Initialize dataset handler
    dataset_path = 'dataset'
    dataset_handler = DatasetHandler(dataset_path)
    
    # Create dataset structure
    dataset_handler.create_dataset_structure()
    print(f"\nDataset structure created at: {dataset_path}")
    
    # Get statistics
    stats = dataset_handler.get_statistics()
    print(f"\nDataset statistics:")
    print(f"  - Total documents: {stats['total_documents']}")
    print(f"  - Images: {stats['total_images']}")
    print(f"  - PDFs: {stats['total_pdfs']}")
    print(f"  - Processed: {stats['processed_count']}")
    
    print("\nTo process all documents, run:")
    print(f"  python main.py {dataset_path}/raw -o {dataset_path}/output")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("OCR PIPELINE - USAGE EXAMPLES")
    print("="*60)
    
    # Run examples
    example_single_image()
    example_single_pdf()
    example_custom_fields()
    example_batch_processing()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60)

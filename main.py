"""
Main OCR Pipeline Application
Orchestrates OCR extraction and metadata parsing from images and PDFs
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Optional, Union
import yaml
import json
from tqdm import tqdm
from flask import Flask, render_template, request, jsonify
import tempfile
from uuid import uuid4

from app_context import AppContext
from config_loader import CONFIG, BBOX_CONFIG

from ocr_engine import OCREngine
from text_parser import TextParser
from dataset_handler import DatasetHandler
from bbox_template_manager import BBoxTemplateManager
from concurrent.futures import ThreadPoolExecutor
from db_writer import save_parsing_result

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=1)

app = Flask(__name__)

OCR_SESSION_STORE = {}

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

def run_pipeline(file_path):
    ocr_engine = OCREngine(CONFIG)
    text_parser = TextParser(CONFIG)
    bbox_manager = BBoxTemplateManager(BBOX_CONFIG)
    return process_single_document(
        file_path=file_path,
        ocr_engine=ocr_engine,
        text_parser=text_parser,
        output_dir='output',
        save_annotated=True,
        use_bbox_template=False
    )

@app.route('/api/certificate-ocr/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    temp_dir = tempfile.mkdtemp()
    file_path = os.path.join(temp_dir, file.filename)
    file.save(file_path)

    try:
        future = executor.submit(run_pipeline, file_path)
        result = future.result()  # blocking but safer
        
        logger.info(f"OCR Result Status: {result.get('status')}")
        
        if result.get("status") == "success":
            logger.info("Attempting to save to database...")
            try:
                save_success = save_parsing_result(result)
                if save_success:
                    logger.info("✓ Data successfully saved to database")
                else:
                    logger.error("✗ Failed to save to database (returned False)")
            except Exception as db_error:
                logger.error(f"✗ Exception while saving to database: {db_error}", exc_info=True)
        else:
            logger.warning(f"Skipping database save - OCR status is not success: {result.get('status')}")
        
        session_id = str(uuid4())

        OCR_SESSION_STORE[session_id] = {
            "metadata": result.get("metadata"),
            "file": result.get("file")
        }

        result["session_id"] = session_id

        return jsonify(result)

    except Exception as e:
        logger.exception("Upload processing failed")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def setup_logging(config: dict):
    """
    Setup logging configuration
    
    Args:
        config: Configuration dictionary
    """
    log_config = config.get('logging', {})
    log_level = getattr(logging, log_config.get('level', 'INFO'))
    
    # Create formatters and handlers
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=[console_handler]
    )
    
    # File handler if enabled
    if log_config.get('save_logs', False):
        log_file = log_config.get('log_file', 'ocr_pipeline.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
    
    logger = logging.getLogger(__name__)
    logger.info("Logging configured successfully")


def load_config(config_path: str = 'config.yaml') -> dict:
    """
    Load configuration from YAML file
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def process_single_document(file_path: Union[str, Path],
                           ocr_engine: OCREngine,
                           text_parser: TextParser,
                           output_dir: Optional[Path] = None,
                           save_annotated: bool = True,
                           bbox_manager: Optional[BBoxTemplateManager] = None,
                           use_bbox_template: bool = False) -> dict:
    """
    Process a single document through the OCR pipeline

    Args:
        file_path: Path to document file
        ocr_engine: OCR engine instance
        text_parser: Text parser instance
        output_dir: Output directory for results
        save_annotated: Whether to save annotated image
        bbox_manager: BBox templates manager (optional)
        use_bbox_template: Whether to use bbox templates extraction

    Returns:
        Dictionary with processing results
    """
    logger = logging.getLogger(__name__)
    file_path = Path(file_path)
    
    logger.info(f"Processing: {file_path.name}")
    
    try:
        # Step 1: OCR - Extract text
        logger.info("Step 1: Running OCR...")
        ocr_result = ocr_engine.process_document(file_path)
        logger.info(f"Extracted {len(ocr_result.get('words', []))} words")
        
        # Step 2: Parse - Extract metadata
        logger.info("Step 2: Parsing metadata...")

        # Use bbox templates if enabled
        bbox_metadata = None
        if use_bbox_template and bbox_manager:
            logger.info("Using BBox templates extraction...")
            bbox_metadata = bbox_manager.extract_auto(ocr_result)
            logger.info(f"BBox templates used: {bbox_metadata.get('template_name', 'N/A')}")

        # Standard parsing
        metadata = text_parser.parse(ocr_result)

        # Check if multiple certificates
        # Step 3: Validate
        if metadata.get('multiple_certificates', False):
            all_valid = True
            all_errors = []

            for i, cert in enumerate(metadata['certificates']):
                is_valid, errors = text_parser.validate_extraction(cert)

                cert['is_valid'] = is_valid
                cert['validation_errors'] = errors

                if not is_valid:
                    all_valid = False
                    all_errors.extend([f"Cert {i + 1}: {e}" for e in errors])

            is_valid = all_valid
            errors = all_errors

        # Merge bbox results if available
        if bbox_metadata and 'extracted_fields' in bbox_metadata:
            if metadata.get('multiple_certificates', False):
                # Add bbox to first certificate for now
                metadata['certificates'][0]['bbox_extraction'] = bbox_metadata
            else:
                metadata['bbox_extraction'] = bbox_metadata
            logger.info("BBox extraction results merged")

        # Step 3: Validate
        if metadata.get('multiple_certificates', False):
            all_valid = True
            all_errors = []

            for i, cert in enumerate(metadata['certificates']):
                is_valid, errors = text_parser.validate_extraction(cert)

                # attach validation result to each certificate
                cert['is_valid'] = is_valid
                cert['validation_errors'] = errors

                if not is_valid:
                    all_valid = False
                    all_errors.extend([f"Cert {i + 1}: {e}" for e in errors])

            is_valid = all_valid
            errors = all_errors

        else:
            is_valid, errors = text_parser.validate_extraction(metadata)

            metadata['is_valid'] = is_valid
            metadata['validation_errors'] = errors

        if not is_valid:
            logger.warning(f"Validation errors: {errors}")

        # Step 4: Save results
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save JSON results
            base_name = file_path.stem
            
            # Save OCR result
            ocr_file = output_dir / f'{base_name}_ocr.json'
            with open(ocr_file, 'w', encoding='utf-8') as f:
                json.dump(ocr_result, f, indent=2, ensure_ascii=False)
            
            # Save metadata
            metadata_file = output_dir / f'{base_name}_metadata.json'
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            # Save extracted text
            text_file = output_dir / f'{base_name}_text.txt'
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(ocr_result.get('full_text', ''))
            
            # Save formatted metadata
            formatted_file = output_dir / f'{base_name}_formatted.txt'
            with open(formatted_file, 'w', encoding='utf-8') as f:
                if metadata.get('multiple_certificates', False):
                    # Format multiple certificates
                    output_lines = []
                    output_lines.append(f"Found {metadata['count']} certificates\n")
                    output_lines.append("="*50 + "\n")
                    for i, cert in enumerate(metadata['certificates']):
                        output_lines.append(f"\nCERTIFICATE {i+1}/{metadata['count']}: {cert.get('template_used', 'unknown').upper()}\n")
                        output_lines.append("="*50 + "\n")
                        output_lines.append(text_parser.format_output(cert, format_type='text'))
                        output_lines.append("\n")
                    f.write(''.join(output_lines))
                else:
                    f.write(text_parser.format_output(metadata, format_type='text'))
            
            logger.info(f"Results saved to: {output_dir}")
            
            # Save annotated image if it's an image file
            if save_annotated and file_path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
                annotated_file = output_dir / f'{base_name}_annotated{file_path.suffix}'
                ocr_engine.save_annotated_image(file_path, ocr_result, annotated_file)
        
        return {
            'status': 'success',
            'file': str(file_path),
            'metadata': metadata,
            'validation': {'is_valid': is_valid, 'errors': errors}
        }
        
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'file': str(file_path),
            'error': str(e)
        }


def process_batch(input_path: Union[str, Path],
                 config: dict,
                 output_dir: Optional[Path] = None,
                 use_bbox_template: bool = False) -> list:
    """
    Process multiple documents in batch

    Args:
        input_path: Path to directory containing documents
        config: Configuration dictionary
        output_dir: Output directory for results
        use_bbox_template: Whether to use bbox templates extraction

    Returns:
        List of processing results
    """
    logger = logging.getLogger(__name__)

    # Initialize components
    logger.info("Initializing OCR engine...")
    ocr_engine = OCREngine(config)

    logger.info("Initializing text parser...")
    text_parser = TextParser(config)

    # Initialize bbox templates manager if enabled
    bbox_manager = None
    if use_bbox_template:
        logger.info("Initializing BBox templates manager...")
        try:
            bbox_manager = BBoxTemplateManager()
            logger.info(f"Available bbox templates: {bbox_manager.get_available_templates()}")
        except Exception as e:
            logger.warning(f"Could not initialize bbox templates manager: {e}")
            use_bbox_template = False

    # Get all documents
    input_path = Path(input_path)
    if input_path.is_file():
        documents = [input_path]
    else:
        dataset_handler = DatasetHandler(input_path)
        documents = dataset_handler.get_all_documents()

    if not documents:
        logger.warning(f"No documents found in: {input_path}")
        return []

    logger.info(f"Found {len(documents)} documents to process")

    # Process each document
    results = []
    for doc_path in tqdm(documents, desc="Processing documents"):
        result = process_single_document(
            doc_path,
            ocr_engine,
            text_parser,
            output_dir,
            save_annotated=config.get('output', {}).get('save_annotated_image', True),
            bbox_manager=bbox_manager,
            use_bbox_template=use_bbox_template
        )
        results.append(result)

    # Summary
    successful = sum(1 for r in results if r['status'] == 'success')
    failed = len(results) - successful

    logger.info(f"\n{'='*50}")
    logger.info(f"BATCH PROCESSING COMPLETE")
    logger.info(f"{'='*50}")
    logger.info(f"Total documents: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")

    if successful > 0:
        # Calculate average quality (handle both single and multiple certificates)
        total_quality = 0
        for r in results:
            if r['status'] == 'success':
                metadata = r['metadata']
                if metadata.get('multiple_certificates', False):
                    # Average quality across all certificates in this document
                    cert_quality = sum(cert.get('overall_quality', 0) for cert in metadata['certificates'])
                    total_quality += cert_quality / metadata['count'] if metadata['count'] > 0 else 0
                else:
                    total_quality += metadata.get('overall_quality', 0)

        avg_quality = total_quality / successful
        logger.info(f"Average extraction quality: {avg_quality:.2%}")

    return results


def main():
    """
    Main entry point for the OCR pipeline
    """
    parser = argparse.ArgumentParser(
        description='OCR Pipeline - Extract text and metadata from images and PDFs'
    )

    parser.add_argument(
        'input',
        type=str,
        help='Path to input file or directory containing documents'
    )

    parser.add_argument(
        '-o', '--output',
        type=str,
        default='output',
        help='Output directory for results (default: output)'
    )

    parser.add_argument(
        '-c', '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    parser.add_argument(
        '--no-annotate',
        action='store_true',
        help='Do not save annotated images'
    )

    parser.add_argument(
        '--show-results',
        action='store_true',
        help='Print extracted metadata to console'
    )

    parser.add_argument(
        '--use-bbox',
        action='store_true',
        help='Use bounding box templates extraction (template1/template2)'
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override config with command line arguments
    if args.no_annotate:
        config.setdefault('output', {})['save_annotated_image'] = False

    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)

    logger.info("="*50)
    logger.info("OCR PIPELINE STARTED")
    logger.info("="*50)

    # Process documents
    results = process_batch(
        args.input,
        config,
        Path(args.output),
        use_bbox_template=args.use_bbox
    )

    # Show results if requested
    if args.show_results:
        text_parser = TextParser(config)
        for result in results:
            if result['status'] == 'success':
                metadata = result['metadata']

                # Check if multiple certificates
                if metadata.get('multiple_certificates', False):
                    print("\n" + "="*50)
                    print(f"File: {result['file']}")
                    print(f"Found {metadata['count']} certificates")
                    print("="*50)

                    for i, cert in enumerate(metadata['certificates']):
                        print(f"\n{'='*50}")
                        print(f"CERTIFICATE {i+1}/{metadata['count']}: {cert.get('template_used', 'unknown').upper()}")
                        print("="*50)
                        print(text_parser.format_output(cert, format_type='text'))
                else:
                    print("\n" + "="*50)
                    print(f"File: {result['file']}")
                    print(text_parser.format_output(metadata, format_type='text'))

    logger.info("="*50)
    logger.info("OCR PIPELINE FINISHED")
    logger.info("="*50)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main()        # CLI mode
    else:
        app.run(debug=True, host='0.0.0.0', port=5000)
"""
Dataset Handler Module
Manages dataset of images and PDFs for processing
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Union
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class DatasetHandler:
    """
    Handler for managing datasets of documents (images and PDFs)
    """
    
    def __init__(self, dataset_path: Union[str, Path]):
        """
        Initialize dataset handler
        
        Args:
            dataset_path: Path to dataset directory
        """
        self.dataset_path = Path(dataset_path)
        self.supported_image_formats = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
        self.supported_pdf_format = ['.pdf']
        self.supported_formats = self.supported_image_formats + self.supported_pdf_format
        
        logger.info(f"Dataset handler initialized for: {self.dataset_path}")
    
    def create_dataset_structure(self):
        """
        Create organized dataset directory structure
        """
        directories = [
            self.dataset_path / 'raw',           # Original documents
            self.dataset_path / 'processed',     # Processed results
            self.dataset_path / 'annotations',   # Manual annotations (ground truth)
            self.dataset_path / 'output',        # OCR output
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory: {directory}")
    
    def get_all_documents(self, subdirectory: str = 'raw') -> List[Path]:
        """
        Get all supported documents from dataset
        
        Args:
            subdirectory: Subdirectory to search in (default: 'raw')
            
        Returns:
            List of document file paths
        """
        search_path = self.dataset_path / subdirectory
        
        if not search_path.exists():
            logger.warning(f"Directory does not exist: {search_path}")
            return []
        
        documents = []
        for ext in self.supported_formats:
            documents.extend(search_path.glob(f'*{ext}'))
            documents.extend(search_path.glob(f'*{ext.upper()}'))
        
        documents = sorted(documents)
        logger.info(f"Found {len(documents)} documents in {search_path}")
        
        return documents
    
    def get_images(self, subdirectory: str = 'raw') -> List[Path]:
        """
        Get all image files from dataset
        
        Args:
            subdirectory: Subdirectory to search in
            
        Returns:
            List of image file paths
        """
        search_path = self.dataset_path / subdirectory
        
        if not search_path.exists():
            return []
        
        images = []
        for ext in self.supported_image_formats:
            images.extend(search_path.glob(f'*{ext}'))
            images.extend(search_path.glob(f'*{ext.upper()}'))
        
        return sorted(images)
    
    def get_pdfs(self, subdirectory: str = 'raw') -> List[Path]:
        """
        Get all PDF files from dataset
        
        Args:
            subdirectory: Subdirectory to search in
            
        Returns:
            List of PDF file paths
        """
        search_path = self.dataset_path / subdirectory
        
        if not search_path.exists():
            return []
        
        pdfs = list(search_path.glob('*.pdf'))
        pdfs.extend(search_path.glob('*.PDF'))
        
        return sorted(pdfs)
    
    def save_results(self, filename: str, ocr_result: Dict, 
                    metadata: Dict, output_dir: Optional[Path] = None):
        """
        Save OCR and parsing results
        
        Args:
            filename: Original filename
            ocr_result: OCR result dictionary
            metadata: Parsed metadata dictionary
            output_dir: Output directory (default: dataset/output)
        """
        if output_dir is None:
            output_dir = self.dataset_path / 'output'
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename without extension
        base_name = Path(filename).stem
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save raw OCR result
        ocr_file = output_dir / f'{base_name}_ocr_{timestamp}.json'
        with open(ocr_file, 'w', encoding='utf-8') as f:
            json.dump(ocr_result, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved OCR result to: {ocr_file}")
        
        # Save parsed metadata
        metadata_file = output_dir / f'{base_name}_metadata_{timestamp}.json'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved metadata to: {metadata_file}")
        
        # Save extracted text
        text_file = output_dir / f'{base_name}_text_{timestamp}.txt'
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(ocr_result.get('full_text', ''))
        logger.info(f"Saved text to: {text_file}")
        
        return {
            'ocr_file': str(ocr_file),
            'metadata_file': str(metadata_file),
            'text_file': str(text_file)
        }
    
    def load_annotation(self, filename: str) -> Optional[Dict]:
        """
        Load manual annotation (ground truth) if available
        
        Args:
            filename: Original filename
            
        Returns:
            Annotation dictionary or None
        """
        base_name = Path(filename).stem
        annotation_file = self.dataset_path / 'annotations' / f'{base_name}.json'
        
        if annotation_file.exists():
            with open(annotation_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def get_statistics(self) -> Dict:
        """
        Get dataset statistics
        
        Returns:
            Dictionary with dataset statistics
        """
        stats = {
            'total_documents': len(self.get_all_documents()),
            'total_images': len(self.get_images()),
            'total_pdfs': len(self.get_pdfs()),
            'processed_count': len(list((self.dataset_path / 'output').glob('*_metadata_*.json'))) if (self.dataset_path / 'output').exists() else 0
        }
        
        return stats

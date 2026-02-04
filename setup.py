"""
Setup Script for OCR Pipeline
Automates initial setup and verification
"""

import os
import sys
from pathlib import Path


def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)


def check_python_version():
    """Check if Python version is compatible"""
    print_header("Checking Python Version")
    
    version = sys.version_info
    print(f"Python version: {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ required!")
        return False
    
    print("✅ Python version OK")
    return True


def create_directories():
    """Create necessary directories"""
    print_header("Creating Directory Structure")
    
    directories = [
        'dataset/raw',
        'dataset/annotations',
        'dataset/output',
        'output',
        'logs'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created: {directory}/")
    
    return True


def check_dependencies():
    """Check if required packages are installed"""
    print_header("Checking Dependencies")
    
    required_packages = [
        ('doctr', 'python-doctr'),
        ('cv2', 'opencv-python'),
        ('PIL', 'Pillow'),
        ('yaml', 'pyyaml'),
        ('torch', 'torch'),
        ('rapidfuzz', 'rapidfuzz'),
        ('tqdm', 'tqdm'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas')
    ]
    
    missing = []
    
    for package, pip_name in required_packages:
        try:
            __import__(package)
            print(f"✅ {pip_name}")
        except ImportError:
            print(f"❌ {pip_name} - NOT INSTALLED")
            missing.append(pip_name)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"\nInstall with: pip install {' '.join(missing)}")
        return False
    
    print("\n✅ All dependencies installed")
    return True


def check_gpu():
    """Check GPU availability"""
    print_header("Checking GPU Availability")
    
    try:
        import torch
        
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            print(f"✅ GPU Available: {gpu_name}")
            print(f"   CUDA Version: {torch.version.cuda}")
            return True
        else:
            print("⚠️  No GPU detected - will use CPU")
            print("   (Processing will be slower)")
            return True
    except Exception as e:
        print(f"⚠️  Could not check GPU: {e}")
        return True


def verify_config():
    """Verify config file exists"""
    print_header("Verifying Configuration")
    
    if Path('config.yaml').exists():
        print("✅ config.yaml found")
        return True
    else:
        print("❌ config.yaml not found!")
        return False


def create_sample_dataset_info():
    """Create info file for dataset"""
    print_header("Creating Dataset Info")
    
    info_content = """# Dataset Information

## How to Use

1. Place your images/PDFs in `dataset/raw/`
2. Run: `python main.py dataset/raw -o dataset/output`
3. Check results in `dataset/output/`

## Supported Formats

- Images: .jpg, .jpeg, .png, .bmp, .tiff, .tif
- Documents: .pdf

## Folder Structure

- `raw/` - Original documents (input)
- `annotations/` - Ground truth annotations (optional)
- `output/` - Processing results (output)

## Example

```bash
# Process all documents
python main.py dataset/raw -o dataset/output --show-results
```
"""
    
    info_file = Path('dataset/README.txt')
    with open(info_file, 'w', encoding='utf-8') as f:
        f.write(info_content)
    
    print(f"✅ Created: {info_file}")
    return True


def run_quick_test():
    """Run a quick test to verify installation"""
    print_header("Running Quick Test")
    
    try:
        from doctr.models import ocr_predictor
        print("✅ Importing docTR...")
        
        # Try to create a model (this will download pretrained weights)
        print("✅ Loading OCR model (this may take a moment)...")
        model = ocr_predictor(pretrained=True)
        print("✅ Model loaded successfully!")
        
        return True
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def main():
    """Main setup function"""
    print("\n" + "="*60)
    print("  OCR PIPELINE - SETUP WIZARD")
    print("="*60)
    
    steps = [
        ("Python Version", check_python_version),
        ("Directory Structure", create_directories),
        ("Dependencies", check_dependencies),
        ("GPU Check", check_gpu),
        ("Configuration", verify_config),
        ("Dataset Info", create_sample_dataset_info),
        ("Quick Test", run_quick_test)
    ]
    
    results = []
    
    for step_name, step_func in steps:
        try:
            result = step_func()
            results.append((step_name, result))
        except Exception as e:
            print(f"❌ Error in {step_name}: {e}")
            results.append((step_name, False))
    
    # Summary
    print_header("Setup Summary")
    
    for step_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {step_name}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n" + "="*60)
        print("  ✅ SETUP COMPLETE!")
        print("="*60)
        print("\nNext steps:")
        print("1. Place your documents in dataset/raw/")
        print("2. Customize config.yaml if needed")
        print("3. Run: python main.py dataset/raw -o output")
        print("\nFor more info, see README.md or QUICKSTART.md")
    else:
        print("\n" + "="*60)
        print("  ⚠️  SETUP INCOMPLETE")
        print("="*60)
        print("\nPlease fix the issues above and run setup again.")
        print("For help, check README.md")
    
    return all_passed


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)


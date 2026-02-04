"""
Installation Test Script
Quick verification that all components are working
"""

import sys
from config_loader import CONFIG

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)


def test_python_version():
    """Test Python version"""
    print_header("Testing Python Version")
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major >= 3 and version.minor >= 8:
        print("✅ Python version OK")
        return True
    else:
        print("❌ Python 3.8+ required")
        return False


def test_imports():
    """Test all required imports"""
    print_header("Testing Package Imports")
    
    packages = [
        ('doctr', 'python-doctr'),
        ('torch', 'torch'),
        ('cv2', 'opencv-python'),
        ('PIL', 'Pillow'),
        ('yaml', 'pyyaml'),
        ('rapidfuzz', 'rapidfuzz'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('tqdm', 'tqdm')
    ]
    
    all_ok = True
    for module, name in packages:
        try:
            __import__(module)
            print(f"✅ {name}")
        except ImportError as e:
            print(f"❌ {name} - {e}")
            all_ok = False
    
    return all_ok


def test_gpu():
    """Test GPU availability"""
    print_header("Testing GPU")
    
    try:
        import torch
        
        if torch.cuda.is_available():
            print(f"✅ GPU Available")
            print(f"   Device: {torch.cuda.get_device_name(0)}")
            print(f"   CUDA Version: {torch.version.cuda}")
            return True
        else:
            print("⚠️  No GPU detected (will use CPU)")
            return True
    except Exception as e:
        print(f"❌ Error checking GPU: {e}")
        return False


def test_doctr_model():
    """Test docTR model loading"""
    print_header("Testing docTR Model")
    
    try:
        from doctr.models import ocr_predictor
        
        print("Loading OCR model (this may take a moment)...")
        model = ocr_predictor(pretrained=True)
        print("✅ docTR model loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return False

def test_project_files():
    """Test project files exist"""
    print_header("Testing Project Files")

    from pathlib import Path
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    required_files = [
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "ocr_service" / "app" / "ocr_engine.py",
        PROJECT_ROOT / "ocr_service" / "app" / "text_parser.py",
        PROJECT_ROOT / "ocr_service" / "app" / "dataset_handler.py",
        PROJECT_ROOT / "ocr_service" / "core" / "config.py"
    ]

    all_ok = True
    for file in required_files:
        if file.exists():
            print(f"✅ {file.relative_to(PROJECT_ROOT)}")
        else:
            print(f"❌ {file.relative_to(PROJECT_ROOT)} - NOT FOUND")
            all_ok = False

    return all_ok

def test_directories():
    """Test required directories exist"""
    print_header("Testing Directories")
    
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    required_dirs = [
        PROJECT_ROOT / "ocr_service" / 'dataset/raw',
        PROJECT_ROOT / "ocr_service" / 'dataset/output',
        PROJECT_ROOT / "ocr_service" / 'dataset/annotations',
        PROJECT_ROOT / "ocr_service" / 'output',
        PROJECT_ROOT / "ocr_service" / 'logs'
    ]
    
    all_ok = True
    for directory in required_dirs:
        path = Path(directory)
        if path.exists():
            print(f"✅ {directory}/")
        else:
            print(f"⚠️  {directory}/ - Creating...")
            path.mkdir(parents=True, exist_ok=True)
    
    return all_ok


def test_config():
    """Test config file can be loaded"""
    print_header("Testing Configuration")
    
    try:
        
        print("✅ configuration loaded from core.config")
        print(f"   OCR Model: {CONFIG['ocr']['detection_model']}")
        print(f"   Recognition: {CONFIG['ocr']['recognition_model']}")
        print(f"   Fields configured: {len(CONFIG['parsing']['fields'])}")
        return True
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return False

def test_modules():
    print_header("Testing Project Modules")

    modules = [
        'ocr_service.app.ocr_engine',
        'ocr_service.app.text_parser',
        'ocr_service.app.dataset_handler',
        'ocr_service.core.config'
    ]

    all_ok = True
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except Exception as e:
            print(f"❌ {module} - {e}")
            all_ok = False

    return all_ok

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("  OCR PIPELINE - INSTALLATION TEST")
    print("="*60)
    
    tests = [
        ("Python Version", test_python_version),
        ("Package Imports", test_imports),
        ("GPU Check", test_gpu),
        ("Project Files", test_project_files),
        ("Directories", test_directories),
        ("Configuration", test_config),
        ("Project Modules", test_modules),
        ("docTR Model", test_doctr_model)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Unexpected error in {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    print_header("Test Summary")
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        if result:
            print(f"✅ {test_name}")
            passed += 1
        else:
            print(f"❌ {test_name}")
            failed += 1
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n" + "="*60)
        print("  ✅ ALL TESTS PASSED!")
        print("="*60)
        print("\n🎉 Installation successful!")
        print("\nNext steps:")
        print("1. Read QUICKSTART.md")
        print("2. Place documents in dataset/raw/")
        print("3. Run: python main.py dataset/raw -o output")
        return True
    else:
        print("\n" + "="*60)
        print("  ⚠️  SOME TESTS FAILED")
        print("="*60)
        print("\nPlease fix the issues above.")
        print("See INSTALLATION.md for help.")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)


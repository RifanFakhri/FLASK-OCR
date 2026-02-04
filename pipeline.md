### Langkah 1: Install Dependencies

```bash
# Install semua yang dibutuhkan
pip install -r requirements.txt
```

### Langkah 2: Setup Project

```bash
# Jalankan setup wizard
python setup.py
```

### Langkah 3: Test Installation

```bash
# Verify semua OK
python test_installation.py
```

### Option A: Run Flask 

```bash
python main.py

### Option B: Quick Test 

```bash
# 1. Letakkan sample image/PDF  di folder dataset/raw/
#    Contoh: dataset/raw/adindawindukarsa.pdf

# 2. Process dokumen
python main.py dataset/raw/adindawindukarsa.pdf -o output --show-results

# 3. Lihat hasil di folder output/
#    - invoice_metadata.json    (metadata yang diekstrak)
#    - invoice_annotated.jpg    (image dengan bounding boxes)
#    - invoice_text.txt         (plain text)
```

### Option C: Batch Processing

```bash
# Process semua dokumen di folder
python main.py dataset/raw -o dataset/output
```

## ⚙️ Customize untuk Dokumen

Edit file `config.yaml` bagian `parsing.fields`:

```yaml
parsing:
  fields:
    # Contoh: Ekstrak nomor invoice
    invoice_number:
      labels: ['Invoice No', 'No. Invoice', 'INV']  # Label di dokumen
      pattern: 'INV-?\d{4,}'                         # Pattern regex
      required: true                                 # Wajib ada?
    
    # Tambahkan field lain sesuai kebutuhan...
```

**Tips**: Lihat [QUICKSTART.md](QUICKSTART.md) untuk contoh konfigurasi berbagai jenis dokumen!

## 📚 Dokumentasi Lengkap

Pilih sesuai kebutuhan Anda:

| Dokumen | Untuk Apa | Waktu Baca |
|---------|-----------|------------|
| **[INDEX.md](INDEX.md)** | 📑 Navigasi semua dokumentasi | 2 min |
| **[INSTALLATION.md](INSTALLATION.md)** | 🔧 Panduan install detail | 10 min |
| **[QUICKSTART.md](QUICKSTART.md)** | ⚡ Mulai cepat dalam 5 menit | 5 min |
| **[README.md](README.md)** | 📖 Dokumentasi lengkap | 20 min |
| **[USAGE_GUIDE.md](USAGE_GUIDE.md)** | 💻 Panduan advanced | 30 min |
| **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** | 📊 Overview project | 10 min |

## 🎯 Workflow Rekomendasi

```
1. Baca START_HERE.md (ini!) ✅
   ↓
2. Install: pip install -r requirements.txt
   ↓
3. Setup: python setup.py
   ↓
4. Test: python test_installation.py
   ↓
5. Baca QUICKSTART.md
   ↓
6. Edit config.yaml (sesuaikan field)
   ↓
7. Letakkan dokumen di dataset/raw/
   ↓
8. Process: python main.py dataset/raw -o output
   ↓
9. Check hasil di folder output/
   ↓
10. Iterate & improve! 🚀
```


## ✨ Quick Commands

```bash
# Setup
python setup.py

# Test
python test_installation.py

# To Open UI
python main.py

# Process single file
python main.py document.jpg -o output

# Process batch
python main.py dataset/raw -o output

# Show results in console
python main.py document.jpg --show-results

# Run examples
python example_usage.py
```


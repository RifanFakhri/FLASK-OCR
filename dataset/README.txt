# Dataset Information

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

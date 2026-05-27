# Auto PDF Bookmarker

A robust Python tool to automatically generate and inject Table of Contents (bookmarks) into PDF textbooks using advanced font-size analysis.

## Features

- **Font-Size Detection**: Instead of relying on fragile Regular Expressions, this tool physically measures the font size of text blocks to reliably identify Chapters, Sections, and Sub-sections. This avoids false positives from citations or paragraph text.
- **Smart Merging**: Automatically combines split multi-line headers on the same page (e.g., seamlessly merging "Chapter 13" and "Linear Algebra" into a single "Chapter 13: Linear Algebra" bookmark).
- **Duplicate Prevention**: Filters out identically repeating strings to prevent generating false bookmarks from running headers or footers.
- **Hierarchical Structure**: Correctly nests Level 1, Level 2, and Level 3 headings for a clean, navigable bookmark tree.

## Installation

The script requires `PyMuPDF` (imported as `fitz`) for extremely fast and accurate PDF parsing and modification.

```bash
pip install PyMuPDF
```

## Usage

1. Place the PDF you want to process in the same directory as the script.
2. Open `add_bookmarks.py` and modify the `input_file` and `output_file` variables at the very bottom of the script to match your PDF's name:

```python
if __name__ == "__main__":
    input_file = "Your_Textbook.pdf"
    output_file = "Your_Textbook_bookmarked.pdf"
    
    add_bookmarks(input_file, output_file)
```

3. Run the script from your terminal:
```bash
python add_bookmarks.py
```

## Customization

The script relies on the physical font size of the text to determine the bookmark level. By default, it is configured for a standard textbook layout:

- **Level 1** (Chapters/Parts): Font Size > `24.0`
- **Level 2** (Sections): Font Size between `17.0` and `18.0`
- **Level 3** (Sub-sections): Font Size between `14.0` and `15.0`

If your specific PDF uses different font sizes for its headings, you can use the included `inspect_fonts.py` script to print out the exact font sizes used on specific pages of your book. Once you know the sizes, simply update the `max_size` `if/elif` thresholds inside `add_bookmarks.py` to match your document's layout.

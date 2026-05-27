import fitz

doc = fitz.open('Deep+Learning+Ian+Goodfellow.pdf')
# Let's inspect pages where we know chapters start, and some random pages with running headers
pages_to_inspect = [28, 47, 48, 70, 97] 

for p in pages_to_inspect:
    print(f"\n--- Page {p} ---")
    page = doc[p]
    blocks = page.get_text('dict')['blocks']
    for b in blocks:
        if 'lines' in b:
            for l in b['lines']:
                for s in l['spans']:
                    text = s['text'].strip()
                    if text:
                        # try to avoid unicode errors in powershell
                        safe_text = text.encode('ascii', 'ignore').decode('ascii')
                        print(f"Text: '{safe_text[:30]}', Size: {s['size']:.2f}, Font: {s['font']}")

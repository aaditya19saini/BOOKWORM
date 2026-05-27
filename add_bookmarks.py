import fitz
import os

def add_bookmarks(input_pdf, output_pdf):
    if not os.path.exists(input_pdf):
        print(f"Error: Could not find '{input_pdf}'")
        return

    print(f"Processing '{input_pdf}'...")
    doc = fitz.open(input_pdf)
    toc = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        # We will collect headers block by block to handle multiline headers
        for block in blocks:
            if "lines" not in block:
                continue
            
            block_text = ""
            block_level = None
            
            for line in block["lines"]:
                if not line["spans"]:
                    continue
                
                # Determine size of the largest text in this line
                max_size = max(span["size"] for span in line["spans"])
                
                if max_size > 24.0:
                    level = 1
                elif max_size > 17.0 and max_size < 18.0:
                    level = 2
                elif max_size > 14.0 and max_size < 15.0:
                    level = 3
                else:
                    level = None
                
                if level:
                    # Concatenate spans in the line
                    line_text = "".join(span["text"] for span in line["spans"]).strip()
                    if line_text:
                        if block_level is None:
                            block_level = level
                        # Append with space if it's continuing a multiline header
                        block_text += (" " if block_text else "") + line_text

            if block_text and block_level:
                # Clean up heading text
                heading = block_text.replace("  ", " ").strip()
                
                if len(heading) < 150:
                    # Avoid duplicates of exact same text on the same page
                    if not any(item[1] == heading and item[2] == page_num + 1 for item in toc):
                        # Combine Level 1 headers on the same page
                        if block_level == 1 and len(toc) > 0 and toc[-1][0] == 1 and toc[-1][2] == page_num + 1:
                            # Use a colon or dash for separation
                            separator = ": " if "Chapter" in toc[-1][1] or "Part" in toc[-1][1] else " "
                            toc[-1][1] += separator + heading
                            safe_heading = toc[-1][1].encode('ascii', 'replace').decode('ascii')
                            print(f"  -> Merged (Level 1): '{safe_heading}' on Page {page_num + 1}")
                        else:
                            toc.append([block_level, heading, page_num + 1])
                            safe_heading = heading.encode('ascii', 'replace').decode('ascii')
                            print(f"  -> Found (Level {block_level}): '{safe_heading}' on Page {page_num + 1}")
                    
    if toc:
        # PyMuPDF requires the first TOC item to be level 1, and no level jumps > 1
        toc[0][0] = 1
        for i in range(1, len(toc)):
            prev_level = toc[i-1][0]
            if toc[i][0] > prev_level + 1:
                toc[i][0] = prev_level + 1
        
        doc.set_toc(toc)
        doc.save(output_pdf)
        print(f"\n Success! Saved '{output_pdf}' with {len(toc)} bookmarks.")
    else:
        print("\n No headings found matching your patterns. The PDF was not modified.")
        
    doc.close()

if __name__ == "__main__":
    input_file = "Deep+Learning+Ian+Goodfellow.pdf"
    output_file = "Deep+Learning+Ian+Goodfellow_bookmarked.pdf"
    
    add_bookmarks(input_file, output_file)

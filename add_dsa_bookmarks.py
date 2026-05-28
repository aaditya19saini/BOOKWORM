import fitz
import os
import re
import sys

def generate_dsa_bookmarks(input_pdf, output_pdf):
    if not os.path.exists(input_pdf):
        print(f"Error: Could not find '{input_pdf}'")
        return

    print(f"Opening '{input_pdf}'...")
    doc = fitz.open(input_pdf)
    
    # -------------------------------------------------------------
    # PHASE 1: Parse Table of Contents from Pages 1 to 20
    # -------------------------------------------------------------
    print("\nPhase 1: Parsing Table of Contents pages...")
    
    special_bookmarks = []  # e.g., Acknowledgements, Preface, References
    chapters = []           # list of dicts: {"num": int, "title": str}
    sections = {}           # dict mapping chapter_num -> list of {"num_str": "X.Y", "title": str}
    
    # Track which page special headings are on
    preface_page = None
    acknowledgements_page = None
    
    # First, let's do a quick scan of pages 1 to 20 to find special bookmarks
    for page_num in range(20):
        if page_num >= len(doc):
            break
        text = doc[page_num].get_text()
        for line in text.split('\n'):
            line_clean = line.strip()
            # Handle unicode/control characters
            line_clean = re.sub(r'\s+', ' ', line_clean)
            
            if re.match(r'^Acknowledgements$', line_clean, re.IGNORECASE) and not acknowledgements_page:
                acknowledgements_page = page_num + 1
                special_bookmarks.append([1, "Acknowledgements", acknowledgements_page])
                print(f"  -> Found 'Acknowledgements' on Page {acknowledgements_page}")
            elif re.match(r'^Preface$', line_clean, re.IGNORECASE) and not preface_page:
                preface_page = page_num + 1
                special_bookmarks.append([1, "Preface", preface_page])
                print(f"  -> Found 'Preface' on Page {preface_page}")

    # Now let's extract chapters and sections from the Table of Contents (Pages 7 to 14, i.e. indices 6 to 13)
    # We will search indices 6 to 13 explicitly for TOC lines
    for page_num in range(6, 14):
        if page_num >= len(doc):
            break
        text = doc[page_num].get_text()
        for line in text.split('\n'):
            line_clean = line.strip()
            # Replace multiple spaces/tabs with single space
            line_clean = re.sub(r'\s+', ' ', line_clean)
            
            # Match Chapter: e.g. "1. Introduction" or "2. Recursion and Backtracking"
            chapter_match = re.match(r'^(\d+)\.\s+(.+)$', line_clean)
            if chapter_match:
                ch_num = int(chapter_match.group(1))
                ch_title = chapter_match.group(2).strip()
                # Skip if it is a section like 1.10 that somehow got matched (shouldn't, because of dot pattern)
                chapters.append({"num": ch_num, "title": ch_title})
                sections[ch_num] = []
                print(f"  -> TOC Chapter {ch_num}: '{ch_title}'")
                continue
                
            # Match Section: e.g. "1.1 Variables" or "2.12 Backtracking: Problems & Solutions"
            section_match = re.match(r'^(\d+)\.(\d+)\s+(.+)$', line_clean)
            if section_match:
                ch_num = int(section_match.group(1))
                sec_sub = int(section_match.group(2))
                sec_title = section_match.group(3).strip()
                
                if ch_num in sections:
                    sections[ch_num].append({
                        "num_str": f"{ch_num}.{sec_sub}",
                        "title": sec_title
                    })
                continue

    # -------------------------------------------------------------
    # PHASE 2: Map Heading Sections to Physical Content Pages
    # -------------------------------------------------------------
    print("\nPhase 2: Mapping Chapters and Sections to physical content pages...")
    
    # We will store the final resolved pages here:
    # section_pages["X.Y"] = page_number
    # chapter_pages[X] = page_number
    section_pages = {}
    chapter_pages = {}
    references_page = None
    
    current_search_page = 14  # Start searching content page from page 15 (index 14)
    
    # To make matching extremely robust, we search sequentially:
    # For Chapter 1: find 1.1, then 1.2, ..., then 1.28
    # Then Chapter 2: find 2.1, then 2.2, ..., and so on.
    for ch in chapters:
        ch_num = ch["num"]
        ch_title = ch["title"]
        ch_sections = sections.get(ch_num, [])
        
        print(f"Scanning pages for Chapter {ch_num}: '{ch_title}'...")
        
        for sec in ch_sections:
            sec_num_str = sec["num_str"]
            sec_title = sec["title"]
            
            # Let's search sequentially starting from current_search_page
            found = False
            for page_idx in range(current_search_page, len(doc)):
                page = doc[page_idx]
                blocks = page.get_text("dict")["blocks"]
                
                # Scan through all text blocks
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        for s in l["spans"]:
                            font_size = s["size"]
                            font_name = s["font"]
                            span_text = s["text"].strip()
                            span_text_clean = re.sub(r'\s+', ' ', span_text)
                            
                            # precise section filter:
                            # 1. Starts with "X.Y"
                            # 2. Font size around 9.81 pt (9.5 to 10.5)
                            # 3. Font contains "Bold"
                            if (span_text_clean.startswith(sec_num_str) and 
                                9.5 <= font_size <= 10.5 and 
                                "bold" in font_name.lower()):
                                
                                page_num = page_idx + 1
                                section_pages[sec_num_str] = page_num
                                current_search_page = page_idx  # Update search cursor sequentially
                                found = True
                                
                                # If this is the very first section of the chapter (X.1), 
                                # then Chapter X starts on this page!
                                if sec_num_str.endswith(".1"):
                                    chapter_pages[ch_num] = page_num
                                    print(f"  -> Chapter {ch_num} starts on Page {page_num}")
                                    
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            
            if not found:
                # Fallback: if not found, use current_search_page + 1
                page_num = current_search_page + 1
                section_pages[sec_num_str] = page_num
                print(f"  [Warning] Section {sec_num_str} not found! Defaulting to Page {page_num}")

    # Find References page at the end of the book
    # Scan last 20 pages for bold "References" text
    last_pages_start = max(14, len(doc) - 20)
    for page_idx in range(last_pages_start, len(doc)):
        page = doc[page_idx]
        blocks = page.get_text("dict")["blocks"]
        found = False
        for b in blocks:
            if "lines" not in b:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    font_size = s["size"]
                    font_name = s["font"]
                    span_text = s["text"].strip()
                    if (re.match(r'^References$', span_text, re.IGNORECASE) and 
                        "bold" in font_name.lower()):
                        references_page = page_idx + 1
                        print(f"  -> Found 'References' on Page {references_page}")
                        found = True
                        break
                if found:
                    break
            if found:
                break
        if found:
            break
            
    if not references_page:
        # Fallback to the very last page
        references_page = len(doc)
        print(f"  [Warning] 'References' not found! Defaulting to Page {references_page}")

    # -------------------------------------------------------------
    # PHASE 3: Construct Bookmark Array & Inject into PDF
    # -------------------------------------------------------------
    print("\nPhase 3: Assembling bookmarks and injecting...")
    
    toc = []
    
    # 1. Add Acknowledgements and Preface if found
    for sb in special_bookmarks:
        toc.append(sb)
        
    # 2. Add Chapters and their Sections
    for ch in chapters:
        ch_num = ch["num"]
        ch_title = ch["title"]
        ch_page = chapter_pages.get(ch_num)
        
        if ch_page:
            toc.append([1, f"Chapter {ch_num}: {ch_title}", ch_page])
            
            # Add all sections of this chapter
            ch_sections = sections.get(ch_num, [])
            for sec in ch_sections:
                sec_num_str = sec["num_str"]
                sec_title = sec["title"]
                sec_page = section_pages.get(sec_num_str)
                
                if sec_page:
                    toc.append([2, f"{sec_num_str} {sec_title}", sec_page])
                    
    # 3. Add References
    toc.append([1, "References", references_page])
    
    print(f"\nFinal TOC has {len(toc)} bookmarks assembled.")
    
    # Inject Table of Contents
    doc.set_toc(toc)
    doc.save(output_pdf)
    doc.close()
    
    print(f"\nSuccess! Saved bookmarked PDF to '{output_pdf}' with {len(toc)} bookmarks.")

if __name__ == "__main__":
    input_file = "4f91b8db-dae0-4737-8194-94ad5a70b1f8.pdf"
    output_file = "DSA.pdf"
    
    generate_dsa_bookmarks(input_file, output_file)

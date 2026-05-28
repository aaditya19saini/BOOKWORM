import fitz
import os
import re
import sys
from collections import Counter

# Set stdout to UTF-8 to prevent UnicodeEncodeError in PowerShell
sys.stdout.reconfigure(encoding='utf-8')

def preprocess_toc_lines(text):
    """
    Cleans and joins TOC lines that were split across line breaks in the PDF text flow.
    E.g. joins:
      Line 1: "1.1"
      Line 2: "Who Should Read This Book?"
    Into:
      "1.1 Who Should Read This Book?"
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    cleaned_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Replace multiple whitespace/tabs with single space
        line = re.sub(r'\s+', ' ', line)
        
        # Check if line is just a chapter/section/subsection number, e.g. "1", "1.1", "1.1.1"
        is_num = re.match(r'^\d+(\.\d+){0,2}$', line) or re.match(r'^(?:Chapter|Part)\s+\d+$', line, re.IGNORECASE)
        
        if is_num and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # If the next line is a page number (just digits) or a section number, don't merge!
            is_next_num = re.match(r'^\d+(\.\d+){0,2}$', next_line) or re.match(r'^(?:Chapter|Part)\s+\d+$', next_line, re.IGNORECASE)
            
            if not is_next_num:
                # Merge them!
                merged_line = f"{line} {next_line}"
                cleaned_lines.append(merged_line)
                i += 2
                continue
                
        cleaned_lines.append(line)
        i += 1
        
    return cleaned_lines

def clean_heading_title(title):
    """
    Removes dot leaders and trailing page numbers from TOC entry titles.
    E.g. cleans "Who Should Read This Book? . . . . . 8" into "Who Should Read This Book?"
    """
    # Remove dot leaders followed by page numbers
    title = re.sub(r'[\.\s_·•-]{3,}\d+\s*$', '', title)
    title = re.sub(r'\s*\.\s*\.\s*\.\s*.*$', '', title)
    title = re.sub(r'\s*\.\s+\.\s+.*$', '', title)
    # Remove trailing page numbers if separated by whitespace
    title = re.sub(r'\s+\d+\s*$', '', title)
    return title.strip()

def find_toc_range(doc):
    toc_indicators = ["table of contents", "contents", "table of content", "index of contents"]
    toc_start = None
    
    # 1. Discover where the TOC starts
    for page_idx in range(min(30, len(doc))):
        page = doc[page_idx]
        text = page.get_text().lower()
        
        # Check if the page contains a TOC indicator
        if any(ind in text for ind in toc_indicators):
            toc_start = page_idx
            print(f"  -> Detected TOC starting on Page {page_idx + 1}")
            break
            
    if toc_start is None:
        # Fallback to standard range
        toc_start = 6
        toc_end = 13
        print(f"  -> TOC indicator not found. Defaulting to index [{toc_start}:{toc_end}] (Page 7-14)")
        return toc_start, toc_end
        
    # 2. Discover where the TOC ends by scanning consecutive pages
    toc_end = toc_start
    for page_idx in range(toc_start, min(toc_start + 15, len(doc))):
        page = doc[page_idx]
        text = page.get_text()
        
        cleaned_lines = preprocess_toc_lines(text)
        
        # Count lines matching chapter/section patterns
        match_count = 0
        for line_clean in cleaned_lines:
            if (re.match(r'^(\d+)\.\s+(.+)$', line_clean) or 
                re.match(r'^(\d+)\.(\d+)\s+(.+)$', line_clean) or
                re.match(r'^(\d+)\.(\d+)\.(\d+)\s+(.+)$', line_clean) or
                re.match(r'^(?:Chapter|Part)\s+(\d+)\b', line_clean, re.IGNORECASE)):
                match_count += 1
                
        # If the page contains a healthy density of TOC entries (at least 3), it is a TOC page
        if page_idx == toc_start or match_count >= 3:
            toc_end = page_idx
        else:
            # Reached normal content or end of TOC
            break
            
    print(f"  -> Detected TOC ending on Page {toc_end + 1}")
    return toc_start, toc_end

def parse_toc_entries(doc, start_idx, end_idx):
    toc_items = []
    
    special_patterns = ["preface", "acknowledgements", "acknowledgments", "notation", "references", "bibliography", "index", "website"]
    
    for page_idx in range(start_idx, end_idx + 1):
        page = doc[page_idx]
        text = page.get_text()
        
        cleaned_lines = preprocess_toc_lines(text)
        
        for line_clean in cleaned_lines:
            # Check for special pages
            matched_special = False
            for spec in special_patterns:
                if re.match(rf'^{spec}$', line_clean, re.IGNORECASE):
                    toc_items.append({
                        "level": 1,
                        "type": "special",
                        "title": line_clean,
                        "key": line_clean.lower()
                    })
                    matched_special = True
                    break
            if matched_special:
                continue
                
            # Match Level 3 section (X.Y.Z) e.g., "1.2.1 The Many Names"
            subsec_match = re.match(r'^(\d+)\.(\d+)\.(\d+)\s+(.+)$', line_clean)
            if subsec_match:
                num_str = f"{subsec_match.group(1)}.{subsec_match.group(2)}.{subsec_match.group(3)}"
                title = clean_heading_title(subsec_match.group(4))
                toc_items.append({
                    "level": 3,
                    "type": "subsection",
                    "num_str": num_str,
                    "title": title,
                    "ch_num": int(subsec_match.group(1))
                })
                continue
                
            # Match Level 2 section (X.Y) e.g., "1.1 Variables"
            sec_match = re.match(r'^(\d+)\.(\d+)\s+(.+)$', line_clean)
            if sec_match:
                num_str = f"{sec_match.group(1)}.{sec_match.group(2)}"
                title = clean_heading_title(sec_match.group(3))
                toc_items.append({
                    "level": 2,
                    "type": "section",
                    "num_str": num_str,
                    "title": title,
                    "ch_num": int(sec_match.group(1))
                })
                continue
                
            # Match Level 1 (Numbered Chapters): e.g. "1. Introduction" or "12. Searching"
            chapter_num_match = re.match(r'^(\d+)\.\s+(.+)$', line_clean)
            if chapter_num_match:
                ch_num = int(chapter_num_match.group(1))
                title = clean_heading_title(chapter_num_match.group(2))
                toc_items.append({
                    "level": 1,
                    "type": "chapter",
                    "num_str": str(ch_num),
                    "title": title,
                    "ch_num": ch_num
                })
                continue
                
            # Match Level 1 (Word-based Chapters): e.g. "Chapter 1 Introduction" or "Chapter 1: Linear Algebra"
            chapter_word_match = re.match(r'^(?:Chapter|Part)\s+(\d+)\b[:\s.-]*(.+)$', line_clean, re.IGNORECASE)
            if chapter_word_match:
                ch_num = int(chapter_word_match.group(1))
                title = clean_heading_title(chapter_word_match.group(2))
                toc_items.append({
                    "level": 1,
                    "type": "chapter",
                    "num_str": str(ch_num),
                    "title": title,
                    "ch_num": ch_num
                })
                continue

    return toc_items

def find_body_text_size(doc, start_page):
    sizes = []
    # Scan 5 pages from the middle of the book
    mid_page = (start_page + len(doc)) // 2
    for p_idx in range(mid_page, min(mid_page + 5, len(doc))):
        page = doc[p_idx]
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if "lines" in b:
                for l in b["lines"]:
                    for s in l["spans"]:
                        if s["text"].strip():
                            sizes.append(round(s["size"], 2))
    if not sizes:
        return 10.0 # Default fallback
    mode_size = Counter(sizes).most_common(1)[0][0]
    print(f"  -> Identified body text size: {mode_size} pt")
    return mode_size

def probe_heading_signatures(doc, toc_items, start_search_page, body_text_size):
    signatures = {1: None, 2: None, 3: None}
    
    candidates_2 = [item for item in toc_items if item["level"] == 2][:5]
    candidates_3 = [item for item in toc_items if item["level"] == 3][:5]
    candidates_1 = [item for item in toc_items if item["level"] == 1][:5]
    
    # 1. Probe Level 2 Signature
    if candidates_2:
        print("Probing styling signature for Level 2 sections...")
        for cand in candidates_2:
            num_str = cand["num_str"]
            found = False
            for p_idx in range(start_search_page, len(doc)):
                page = doc[p_idx]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        for s in l["spans"]:
                            text = s["text"].strip()
                            text_clean = re.sub(r'\s+', ' ', text)
                            
                            # Match starts with section number, size > body_text_size + 0.5, and font is bold
                            if (text_clean.startswith(num_str) and 
                                s["size"] > body_text_size + 0.5 and
                                ("bold" in s["font"].lower() or s["size"] > body_text_size + 1.0)):
                                signatures[2] = {
                                    "size": round(s["size"], 2),
                                    "font": s["font"]
                                }
                                print(f"  -> Found Level 2 style signature: {signatures[2]}")
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break
                
    # 2. Probe Level 3 Signature
    if candidates_3:
        print("Probing styling signature for Level 3 subsections...")
        for cand in candidates_3:
            num_str = cand["num_str"]
            found = False
            for p_idx in range(start_search_page, len(doc)):
                page = doc[p_idx]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        for s in l["spans"]:
                            text = s["text"].strip()
                            text_clean = re.sub(r'\s+', ' ', text)
                            if (text_clean.startswith(num_str) and 
                                s["size"] > body_text_size + 0.2 and
                                ("bold" in s["font"].lower() or s["size"] > body_text_size + 0.5)):
                                signatures[3] = {
                                    "size": round(s["size"], 2),
                                    "font": s["font"]
                                }
                                print(f"  -> Found Level 3 style signature: {signatures[3]}")
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break

    # 3. Probe Level 1 (Chapters) Signature
    if candidates_1:
        print("Probing styling signature for Level 1 chapters...")
        for cand in candidates_1:
            title = cand["title"]
            found = False
            for p_idx in range(start_search_page, len(doc)):
                page = doc[p_idx]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        for s in l["spans"]:
                            text = s["text"].strip()
                            if (title.lower() in text.lower() and 
                                s["size"] > body_text_size + 3.0):
                                signatures[1] = {
                                    "size": round(s["size"], 2),
                                    "font": s["font"]
                                }
                                print(f"  -> Found Level 1 chapter style signature: {signatures[1]}")
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if found:
                break

    return signatures

def map_headings_to_pages(doc, toc_items, start_search_page, signatures, body_text_size):
    resolved_toc = []
    current_search_page = start_search_page
    resolved_pages = {}
    
    print("\nMapping parsed TOC headings to content pages...")
    for item in toc_items:
        level = item["level"]
        title = item["title"]
        item_type = item["type"]
        
        if item_type == "special":
            key = item["key"]
            found_page = None
            for p_idx in range(start_search_page + 2):
                if p_idx >= len(doc):
                    break
                page = doc[p_idx]
                text = page.get_text().lower()
                if key in text:
                    found_page = p_idx + 1
                    break
            if found_page:
                resolved_toc.append([level, title, found_page])
                print(f"  -> Special '{title}' mapped to Page {found_page}")
            continue
            
        if item_type == "chapter":
            ch_num = item["ch_num"]
            found = False
            sig = signatures[1]
            if sig:
                for p_idx in range(current_search_page, len(doc)):
                    page = doc[p_idx]
                    blocks = page.get_text("dict")["blocks"]
                    for b in blocks:
                        if "lines" not in b:
                            continue
                        for l in b["lines"]:
                            for s in l["spans"]:
                                text = s["text"].strip()
                                if (title.lower() in text.lower() and 
                                    abs(s["size"] - sig["size"]) < 1.0 and 
                                    s["font"] == sig["font"]):
                                    
                                    found_page = p_idx + 1
                                    resolved_pages[f"ch_{ch_num}"] = found_page
                                    current_search_page = p_idx
                                    resolved_toc.append([level, f"Chapter {ch_num}: {title}", found_page])
                                    print(f"  -> Chapter {ch_num}: '{title}' mapped to Page {found_page}")
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break
                    if found:
                        break
            
            if not found:
                resolved_toc.append({
                    "pending": True,
                    "level": level,
                    "type": "chapter",
                    "ch_num": ch_num,
                    "title": f"Chapter {ch_num}: {title}"
                })
            continue

        num_str = item["num_str"]
        ch_num = item["ch_num"]
        sig = signatures[level]
        
        found = False
        if sig:
            for p_idx in range(current_search_page, len(doc)):
                page = doc[p_idx]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if "lines" not in b:
                        continue
                    for l in b["lines"]:
                        for s in l["spans"]:
                            text = s["text"].strip()
                            text_clean = re.sub(r'\s+', ' ', text)
                            if (text_clean.startswith(num_str) and 
                                abs(s["size"] - sig["size"]) < 0.5 and 
                                ("bold" in s["font"].lower() or "bold" in sig["font"].lower() or s["font"] == sig["font"])):
                                
                                found_page = p_idx + 1
                                resolved_pages[num_str] = found_page
                                current_search_page = p_idx
                                resolved_toc.append([level, f"{num_str} {title}", found_page])
                                print(f"  -> Section {num_str}: '{title}' mapped to Page {found_page}")
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
                    
        if not found:
            for p_idx in range(current_search_page, len(doc)):
                page = doc[p_idx]
                text = page.get_text()
                if re.search(rf'\b{re.escape(num_str)}\b', text):
                    found_page = p_idx + 1
                    resolved_pages[num_str] = found_page
                    current_search_page = p_idx
                    resolved_toc.append([level, f"{num_str} {title}", found_page])
                    print(f"  -> Section {num_str} (fallback text search): '{title}' mapped to Page {found_page}")
                    found = True
                    break
                    
        if not found:
            found_page = current_search_page + 1
            resolved_pages[num_str] = found_page
            resolved_toc.append([level, f"{num_str} {title}", found_page])
            print(f"  [Warning] Section {num_str} not found! Defaulting to Page {found_page}")

    final_toc = []
    for item in resolved_toc:
        if isinstance(item, dict) and item.get("pending"):
            ch_num = item["ch_num"]
            title = item["title"]
            first_sec_page = resolved_pages.get(f"{ch_num}.1")
            if first_sec_page:
                final_toc.append([item["level"], title, first_sec_page])
                print(f"  -> Pending Chapter {ch_num} resolved to Page {first_sec_page} (from Section {ch_num}.1)")
            else:
                # If X.1 is not found, let's search if X.2 exists
                sec_keys = [k for k in resolved_pages.keys() if k.startswith(f"{ch_num}.")]
                if sec_keys:
                    min_sec_page = min(resolved_pages[k] for k in sec_keys)
                    final_toc.append([item["level"], title, min_sec_page])
                    print(f"  -> Pending Chapter {ch_num} resolved to Page {min_sec_page} (from first available Section)")
                else:
                    fallback_page = start_search_page + 1
                    final_toc.append([item["level"], title, fallback_page])
                    print(f"  [Warning] Chapter {ch_num} first section not found! Defaulting to Page {fallback_page}")
        else:
            final_toc.append(item)
            
    return final_toc

def run_universal_bookmarker(input_pdf, output_pdf):
    print(f"\n=======================================================")
    print(f"Universal Plug-and-Play Bookmarker: '{input_pdf}'")
    print(f"=======================================================")
    
    if not os.path.exists(input_pdf):
        print(f"Error: File '{input_pdf}' not found.")
        return
        
    doc = fitz.open(input_pdf)
    
    # 1. Discover TOC Range
    toc_start_page, toc_end_page = find_toc_range(doc)
    
    # 2. Parse TOC entries
    toc_items = parse_toc_entries(doc, toc_start_page, toc_end_page)
    print(f"  -> Parsed {len(toc_items)} outline items from Table of Contents.")
    
    # 3. Dynamic Font Style Signature Autoprobe
    body_text_size = find_body_text_size(doc, toc_end_page)
    signatures = probe_heading_signatures(doc, toc_items, toc_end_page, body_text_size)
    
    # 4. Map Headings sequentially
    final_toc = map_headings_to_pages(doc, toc_items, toc_end_page, signatures, body_text_size)
    
    # Inject bookmarks
    doc.set_toc(final_toc)
    doc.save(output_pdf)
    doc.close()
    
    print(f"\nSuccess! Successfully bookmarked '{output_pdf}' with {len(final_toc)} items.")

if __name__ == "__main__":
    # Test case 1: DSA book
    if os.path.exists("4f91b8db-dae0-4737-8194-94ad5a70b1f8.pdf"):
        run_universal_bookmarker("4f91b8db-dae0-4737-8194-94ad5a70b1f8.pdf", "DSA_universal.pdf")
        
    # Test case 2: Deep Learning book
    if os.path.exists("Deep+Learning+Ian+Goodfellow.pdf"):
        run_universal_bookmarker("Deep+Learning+Ian+Goodfellow.pdf", "Deep_Learning_universal.pdf")

import re
import base64
import io
import logging
import shutil
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OCR support for scanned/image-based PDFs
# ---------------------------------------------------------------------------
_ocr_cache = {}   # pg_idx -> {'text': str, 'blocks': list}
_is_scanned = False


def _init_ocr():
    """Reset OCR state at the start of each parse call."""
    global _ocr_cache, _is_scanned
    _ocr_cache = {}
    _is_scanned = False


def _detect_scanned_pdf(doc):
    """Check if the PDF is image-based (no extractable text)."""
    global _is_scanned
    for i in range(min(5, len(doc))):
        if doc[i].get_text().strip():
            _is_scanned = False
            return
    _is_scanned = True
    logger.info("[OCR] Detected scanned/image-based PDF — will use OCR")


def _ocr_page(page):
    """OCR a single page and cache both plain text and block structure."""
    pg_idx = page.number
    if pg_idx in _ocr_cache:
        return

    try:
        from PIL import Image
        import pytesseract
    except ImportError:
        logger.warning("[OCR] pytesseract or Pillow not installed — cannot OCR scanned PDF")
        _ocr_cache[pg_idx] = {'text': '', 'col_text': '', 'blocks': []}
        return

    tesseract_cmd = shutil.which('tesseract')
    if not tesseract_cmd:
        import os
        for p in [r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                  r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe']:
            if os.path.isfile(p):
                tesseract_cmd = p
                break
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    dpi = 300
    pix = page.get_pixmap(dpi=dpi)
    img = Image.open(io.BytesIO(pix.tobytes('png')))
    pw = page.rect.width
    scale = float(dpi) / 72.0  # pixel-to-PDF-point conversion
    col_mid_px = int(pw * 0.5 * scale)

    # Full-page OCR for plain text (needed for section detection, answer key, etc.)
    text = pytesseract.image_to_string(img)

    # Column-aware OCR: OCR left and right halves separately to avoid
    # column interleaving that breaks question detection
    w, h = img.size
    left_img = img.crop((0, 0, col_mid_px + 30, h))
    right_img = img.crop((col_mid_px - 30, 0, w, h))

    left_text = pytesseract.image_to_string(left_img, config='--psm 4')
    right_text = pytesseract.image_to_string(right_img, config='--psm 4')
    col_text = left_text + "\n\n" + right_text

    # Build block structure from column-specific word data
    result_blocks = []
    for col_label, col_img, x_offset in [('L', left_img, 0), ('R', right_img, col_mid_px - 30)]:
        data = pytesseract.image_to_data(col_img, output_type=pytesseract.Output.DICT, config='--psm 4')
        blocks_by_num = {}
        for i in range(len(data['text'])):
            word = data['text'][i]
            if not word.strip():
                continue
            block_num = data['block_num'][i]
            line_num = data['line_num'][i]

            x0 = (data['left'][i] + x_offset) / scale
            y0 = data['top'][i] / scale
            x1 = (data['left'][i] + data['width'][i] + x_offset) / scale
            y1 = (data['top'][i] + data['height'][i]) / scale

            if block_num not in blocks_by_num:
                blocks_by_num[block_num] = {'lines': {}, 'bbox': [9999, 9999, 0, 0]}
            blk = blocks_by_num[block_num]
            blk['bbox'] = [
                min(blk['bbox'][0], x0), min(blk['bbox'][1], y0),
                max(blk['bbox'][2], x1), max(blk['bbox'][3], y1),
            ]

            if line_num not in blk['lines']:
                blk['lines'][line_num] = {'spans': [], 'bbox': [9999, 9999, 0, 0]}
            ln = blk['lines'][line_num]
            ln['bbox'] = [
                min(ln['bbox'][0], x0), min(ln['bbox'][1], y0),
                max(ln['bbox'][2], x1), max(ln['bbox'][3], y1),
            ]
            ln['spans'].append({
                'text': word + ' ',
                'bbox': (x0, y0, x1, y1),
                'size': y1 - y0,
                'flags': 0,
                'font': 'OCR',
            })

        for bnum in sorted(blocks_by_num):
            blk = blocks_by_num[bnum]
            lines_list = []
            for lnum in sorted(blk['lines']):
                ln = blk['lines'][lnum]
                lines_list.append({
                    'spans': ln['spans'],
                    'bbox': tuple(ln['bbox']),
                    'wmode': 0,
                    'dir': (1.0, 0.0),
                })
            result_blocks.append({
                'type': 0,
                'bbox': tuple(blk['bbox']),
                'lines': lines_list,
            })

    _ocr_cache[pg_idx] = {'text': text, 'col_text': col_text, 'blocks': result_blocks}


def _get_page_text(page):
    """Get page text with OCR fallback for scanned PDFs."""
    if not _is_scanned:
        return page.get_text()
    _ocr_page(page)
    return _ocr_cache.get(page.number, {}).get('text', '')


def _get_page_col_text(page):
    """Get column-aware OCR text (left col + right col, no interleaving).
    Falls back to regular page text for non-scanned PDFs."""
    if not _is_scanned:
        return page.get_text()
    _ocr_page(page)
    return _ocr_cache.get(page.number, {}).get('col_text', '')


def _get_page_blocks(page):
    """Get page text blocks with OCR fallback for scanned PDFs."""
    if not _is_scanned:
        return page.get_text("dict")["blocks"]
    _ocr_page(page)
    return _ocr_cache.get(page.number, {}).get('blocks', [])


# ACT section headers as they appear in PDFs
SECTION_PATTERNS = [
    (r'ENGLISH\s+TEST', 'English'),
    (r'MATHEMATICS\s+TEST', 'Math'),
    (r'READING\s+TEST', 'Reading'),
    (r'SCIENCE\s+TEST', 'Science'),
]

SECTION_TIME_LIMITS = {
    'English': 45,
    'Math': 60,
    'Reading': 35,
    'Science': 35,
}

# Passage marker pattern
PASSAGE_MARKER = re.compile(r'^(?:PASSAGE|Passage)\s+([IVX]+)', re.MULTILINE)


def _render_region_to_base64(page, rect, scale=2.0):
    """Render a rectangular region of a PDF page to a base64-encoded PNG."""
    clip = fitz.Rect(rect)
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    img_bytes = pix.tobytes("png")
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _has_drawings_in_rect(page, rect):
    """Check if there are vector drawings within a given rect on the page."""
    r = fitz.Rect(rect)
    for d in page.get_drawings():
        for item in d.get("items", []):
            # Each item is a tuple like ("l", Point, Point) for line, etc.
            # Check if any point is inside our rect
            for pt in item[1:]:
                if hasattr(pt, 'x') and hasattr(pt, 'y'):
                    if r.contains(fitz.Point(pt.x, pt.y)):
                        return True
    return False


def _find_figure_regions(page, question_positions, page_text_dict):
    """
    Find regions on a page that contain figures/diagrams/graphs.
    Uses heuristics: areas between questions that have vector drawings
    and no/little text, or areas referenced by "Figure" / "graph" keywords.
    """
    pw = page.rect.width
    ph = page.rect.height
    drawings = page.get_drawings()
    if not drawings:
        return {}

    # Collect all drawing points to find bounding boxes of drawn content
    drawing_clusters = []
    all_points = []
    for d in drawings:
        pts = []
        for item in d.get("items", []):
            for pt in item[1:]:
                if hasattr(pt, 'x') and hasattr(pt, 'y'):
                    pts.append((pt.x, pt.y))
                    all_points.append((pt.x, pt.y))
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            drawing_clusters.append({
                "x0": min(xs), "y0": min(ys),
                "x1": max(xs), "y1": max(ys),
            })

    if not all_points:
        return {}

    # Merge nearby drawing clusters into figure regions
    figure_regions = _merge_drawing_clusters(drawing_clusters, margin=10)

    # Filter out tiny regions (decorative lines, page borders) and header bars
    figure_regions = [
        r for r in figure_regions
        if (r["x1"] - r["x0"]) > 40 and (r["y1"] - r["y0"]) > 40
        and r["y0"] > 50  # skip header decorations
    ]

    return figure_regions


def _merge_drawing_clusters(clusters, margin=15):
    """Merge overlapping or nearby drawing bounding boxes."""
    if not clusters:
        return []

    merged = [dict(clusters[0])]
    for c in clusters[1:]:
        found_merge = False
        for m in merged:
            # Check if clusters overlap or are close
            if (c["x0"] <= m["x1"] + margin and c["x1"] >= m["x0"] - margin and
                c["y0"] <= m["y1"] + margin and c["y1"] >= m["y0"] - margin):
                m["x0"] = min(m["x0"], c["x0"])
                m["y0"] = min(m["y0"], c["y0"])
                m["x1"] = max(m["x1"], c["x1"])
                m["y1"] = max(m["y1"], c["y1"])
                found_merge = True
                break
        if not found_merge:
            merged.append(dict(c))

    # Repeat merging until stable
    prev_len = -1
    while len(merged) != prev_len:
        prev_len = len(merged)
        merged = _merge_drawing_clusters_once(merged, margin)

    return merged


def _merge_drawing_clusters_once(clusters, margin):
    if not clusters:
        return []
    merged = [dict(clusters[0])]
    for c in clusters[1:]:
        found = False
        for m in merged:
            if (c["x0"] <= m["x1"] + margin and c["x1"] >= m["x0"] - margin and
                c["y0"] <= m["y1"] + margin and c["y1"] >= m["y0"] - margin):
                m["x0"] = min(m["x0"], c["x0"])
                m["y0"] = min(m["y0"], c["y0"])
                m["x1"] = max(m["x1"], c["x1"])
                m["y1"] = max(m["y1"], c["y1"])
                found = True
                break
        if not found:
            merged.append(dict(c))
    return merged


def _extract_page_questions(page, page_num):
    """
    Extract question positions and text from a single page using text blocks.
    Returns list of question dicts with their y-position on the page.
    """
    blocks = _get_page_blocks(page)
    text = _get_page_text(page)
    questions = []

    # Find question number positions using text search
    # ACT questions: "1." or "10." at start, with bold numbering
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\.\s+')
    for match in q_pattern.finditer(text):
        q_num = int(match.group(1))
        if q_num < 1 or q_num > 75:
            continue
        # Find the position of this question number on the page
        q_text_start = match.group(0).strip()
        rects = page.search_for(q_text_start)
        if rects:
            questions.append({
                "question_number": q_num,
                "y_pos": rects[0].y0,
                "x_pos": rects[0].x0,
                "page_num": page_num,
            })

    return questions


def parse_act_pdf(pdf_bytes: bytes) -> dict:
    """
    Main entry point: parse an ACT PDF into sections with questions and diagram images.
    Renders diagrams/figures as PNG screenshots from the PDF pages.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # Detect scanned/image-based PDF and set up OCR if needed
    _init_ocr()
    _detect_scanned_pdf(doc)

    # Step 1: Detect section boundaries
    sections_raw = []
    for pg_idx in range(total_pages):
        page = doc[pg_idx]
        text = _get_page_text(page)
        for pattern, section_name in SECTION_PATTERNS:
            if re.search(pattern, text):
                # Check for duplicates
                if not sections_raw or sections_raw[-1]["name"] != section_name:
                    sections_raw.append({
                        "name": section_name,
                        "start_page": pg_idx,
                    })
                break

    # Determine end pages
    for i, sec in enumerate(sections_raw):
        if i + 1 < len(sections_raw):
            sec["end_page"] = sections_raw[i + 1]["start_page"] - 1
        else:
            # Find "END OF TEST" to determine last page
            end_page = total_pages - 1
            for pg_idx in range(sec["start_page"], total_pages):
                text = _get_page_text(doc[pg_idx])
                if re.search(r'END\s+OF\s+TEST\s+\d', text) or re.search(r'STOP!\s+DO\s+NOT', text):
                    end_page = pg_idx
                    break
            sec["end_page"] = end_page

    if not sections_raw:
        text_preview = _get_page_text(doc[0])[:2000] if total_pages > 0 else ""
        doc.close()
        return {
            "sections": [],
            "total_pages": total_pages,
            "total_questions": 0,
            "text_preview": text_preview,
        }

    # Step 2: For each section, parse questions, extract figures and passages
    sections_out = []
    total_questions = 0

    for sec in sections_raw:
        section_questions = []

        # Extract passages for this section
        passages = _extract_passages(doc, sec["start_page"], sec["end_page"], sec["name"])

        for pg_idx in range(sec["start_page"], sec["end_page"] + 1):
            page = doc[pg_idx]
            page_text = _get_page_text(page)
            pw = page.rect.width
            ph = page.rect.height

            # Find figure regions on this page (vector drawings)
            figure_regions = _find_figure_regions(page, [], None)

            # Render significant figures as images
            page_figures = []
            for fig in figure_regions:
                fig_w = fig["x1"] - fig["x0"]
                fig_h = fig["y1"] - fig["y0"]
                # Only capture meaningful figures (not header decorations)
                if fig_w > 60 and fig_h > 60:
                    # Add padding
                    pad = 8
                    rect = (
                        max(0, fig["x0"] - pad),
                        max(0, fig["y0"] - pad),
                        min(pw, fig["x1"] + pad),
                        min(ph, fig["y1"] + pad),
                    )
                    img_b64 = _render_region_to_base64(page, rect, scale=2.0)
                    page_figures.append({
                        "data_uri": img_b64,
                        "y0": fig["y0"],
                        "y1": fig["y1"],
                        "x0": fig["x0"],
                        "x1": fig["x1"],
                    })

            # Parse questions from this page (use column-aware text for better detection)
            q_parse_text = _get_page_col_text(page) if _is_scanned else page_text
            page_questions = _parse_page_questions(page, q_parse_text, pg_idx + 1, section_name=sec["name"])

            # Associate figures with questions
            for q in page_questions:
                # Find figures that are vertically close to this question
                q_y = q.get("y_pos", 0)
                best_fig = None
                best_dist = float("inf")

                for fig in page_figures:
                    # Figure should be near the question (within ~200 points)
                    dist = min(abs(fig["y0"] - q_y), abs(fig["y1"] - q_y))
                    # Also check if figure is between this question and next
                    if dist < best_dist and dist < 250:
                        best_dist = dist
                        best_fig = fig

                if best_fig:
                    q["question_image"] = best_fig["data_uri"]
                    # Remove from pool so it doesn't get assigned to another question
                    page_figures = [f for f in page_figures if f is not best_fig]

                section_questions.append(q)

            # Any remaining unassigned figures - store as section-level images
            # (for passages with figures that apply to multiple questions)
            if page_figures:
                for fig in page_figures:
                    # Try to assign to the nearest question that doesn't have one
                    for q in reversed(section_questions):
                        if q.get("page_num") == pg_idx + 1 and not q.get("question_image"):
                            q["question_image"] = fig["data_uri"]
                            break

        # Sort questions by number
        section_questions.sort(key=lambda q: q["question_number"])

        # Deduplicate questions across pages (e.g. Science procedure steps 1-5
        # can be parsed as questions on passage pages, duplicating real Q1-Q5).
        # Prefer questions with real options over "(see image)" stubs.
        seen_q = {}
        for q in section_questions:
            qn = q["question_number"]
            if qn not in seen_q:
                seen_q[qn] = q
            else:
                existing = seen_q[qn]
                existing_is_stub = existing.get("option_a") == "(see image)"
                new_is_stub = q.get("option_a") == "(see image)"
                # Prefer real options over stubs
                if existing_is_stub and not new_is_stub:
                    seen_q[qn] = q
                # If both are real, prefer the one with more option content
                elif not existing_is_stub and not new_is_stub:
                    existing_len = len(existing.get("option_a", "") or "")
                    new_len = len(q.get("option_a", "") or "")
                    if new_len > existing_len:
                        seen_q[qn] = q
        section_questions = sorted(seen_q.values(), key=lambda q: q["question_number"])

        # Associate questions with passages based on page ranges
        if passages:
            for q in section_questions:
                q_page = q.get("page_num", 0) - 1  # convert to 0-indexed
                q_y = q.get("y_pos", 0)
                best_passage = None
                for p in passages:
                    if p["start_page"] <= q_page <= p["end_page"]:
                        # On shared pages, use y-position to disambiguate
                        # If question is on this passage's end_page and there's a y_max boundary,
                        # only match if the question is above that boundary
                        if (q_page == p["end_page"] and p.get("end_page_y_max") is not None
                                and q_y > p["end_page_y_max"]):
                            continue
                        # If question is on this passage's start_page and there's a marker_y,
                        # only match if the question is at or below the marker
                        if (q_page == p["start_page"] and p.get("marker_y") is not None
                                and q_y < p["marker_y"]):
                            continue
                        best_passage = p
                        break
                if best_passage:
                    p = best_passage
                    passage_label = f"PASSAGE {p['number']}"
                    if p["title"]:
                        passage_label += f"\n{p['title']}"
                    passage_label += f"\n\n{p['text']}"
                    q["passage_text"] = passage_label.strip()
                    if p.get("image"):
                        q["passage_image"] = p["image"]

        # Render question images for Math section (preserves notation)
        if sec["name"] == "Math":
            _extract_math_shared_info(doc, section_questions, sec["start_page"], sec["end_page"])
            _render_question_images(doc, section_questions, sec["start_page"], sec["end_page"])

        # Detect and render embedded tables/figures in Science and Reading questions
        if sec["name"] in ("Science", "Reading"):
            _render_embedded_content(doc, section_questions, sec["start_page"], sec["end_page"], sec["name"])
            # Render question images for graphical-option questions (e.g. graph choices).
            # Pass all questions for position boundaries, but only render stubs.
            graph_q_nums = {q["question_number"] for q in section_questions if q.get("option_a") == "(see image)"}
            if graph_q_nums:
                _render_question_images(doc, section_questions, sec["start_page"], sec["end_page"],
                                        only_q_nums=graph_q_nums)

        # Remove position metadata from output
        for q in section_questions:
            q.pop("y_pos", None)
            q.pop("x_pos", None)
            q.pop("page_num", None)

        sections_out.append({
            "name": sec["name"],
            "start_page": sec["start_page"] + 1,
            "end_page": sec["end_page"] + 1,
            "time_limit_minutes": SECTION_TIME_LIMITS.get(sec["name"], 35),
            "questions": section_questions,
            "images_count": sum(1 for q in section_questions if q.get("question_image")),
        })
        total_questions += len(section_questions)

    # Step 3: Extract answer key from end of PDF and apply to questions
    answer_key = _extract_answer_key(doc)
    answers_applied = 0
    if answer_key:
        for section in sections_out:
            sec_name = section["name"]
            sec_answers = answer_key.get(sec_name, {})
            if sec_answers:
                for q in section["questions"]:
                    q_num = q.get("question_number")
                    if q_num and q_num in sec_answers:
                        q["correct_answer"] = sec_answers[q_num]
                        answers_applied += 1

    # Capture answer key page text for debugging
    answer_key_text = ""
    for pg_idx in range(max(0, total_pages - 10), total_pages):
        page = doc[pg_idx]
        text = _get_page_text(page)
        if re.search(r'(?:Correct\s*Answer|Answer\s*Key|ANSWER\s*KEY)', text, re.IGNORECASE):
            answer_key_text += f"\n=== PAGE {pg_idx + 1} ===\n{text}"

    # Text preview from first few pages
    preview_text = ""
    for i in range(min(3, total_pages)):
        preview_text += _get_page_text(doc[i]) + "\n"

    doc.close()

    return {
        "sections": sections_out,
        "total_pages": total_pages,
        "total_questions": total_questions,
        "answers_extracted": answers_applied,
        "answer_key_by_subject": {k: len(v) for k, v in answer_key.items()} if answer_key else {},
        "answer_key_debug": answer_key_text[:5000] if answer_key_text else "No answer key pages detected",
        "text_preview": preview_text[:3000],
    }


def _render_passage_image(doc, pages_info, section_name, scale=2.0):
    """
    Render passage region from PDF pages as a single stitched PNG image.
    For English: renders the left column of each page.
    For Reading/Science: renders the passage area above questions.
    Returns a base64 data URI string.
    """
    from PIL import Image

    page_images = []
    for pg_idx, clip_rect in pages_info:
        page = doc[pg_idx]
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip_rect)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        page_images.append(img)

    if not page_images:
        return None

    # Stitch images vertically with a small gap
    gap = int(4 * scale)
    total_width = max(img.width for img in page_images)
    total_height = sum(img.height for img in page_images) + gap * (len(page_images) - 1)
    stitched = Image.new("RGB", (total_width, total_height), (255, 255, 255))
    y_offset = 0
    for img in page_images:
        stitched.paste(img, (0, y_offset))
        y_offset += img.height + gap

    buf = io.BytesIO()
    stitched.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _find_passage_clip_rect(page, section_name, is_first_page, y_clip_min=None, y_clip_max=None):
    """
    Determine the clip rectangle(s) for the passage region on a page.
    English: left column (x < ~48% of page width), below header bar.
    Reading/Science: passage area, potentially split into left+right columns
    when the passage spans both columns with questions below in the right column.
    Returns a single fitz.Rect or a list of fitz.Rect for multi-column passages.
    """
    pw = page.rect.width
    ph = page.rect.height

    if section_name == "English":
        # Left column: from left edge to about 48% of page width
        # Skip header bar (top ~90 pts) and footer (bottom ~35 pts)
        # Find actual content bounds
        blocks = _get_page_blocks(page)
        col_boundary = pw * 0.48
        min_y = ph
        max_y = 0
        for b in blocks:
            if b["type"] != 0:
                continue
            bx0, by0, bx1, by1 = b["bbox"]
            if bx0 > col_boundary:
                continue
            # Skip the big "1" header and footer
            block_text = ""
            for line in b["lines"]:
                for span in line["spans"]:
                    block_text += span["text"]
            block_text = block_text.strip()
            if not block_text:
                continue
            if re.match(r'^(GO ON|ACT-|ENGLISH TEST)', block_text):
                continue
            if 'GO ON TO THE NEXT PAGE' in block_text or 'ACT-' in block_text:
                continue
            if 'STOP!' in block_text or 'DO NOT TURN' in block_text or 'END OF TEST' in block_text:
                continue
            if re.match(r'^[1-5]\s*$', block_text):
                continue
            # Skip the large section number headers (e.g. big "1" "2")
            is_large_header = False
            for line in b["lines"]:
                for span in line["spans"]:
                    if span["size"] >= 30:
                        is_large_header = True
                        break
            if is_large_header:
                continue
            # Skip directions on first page
            if is_first_page and ('DIRECTIONS' in block_text or 'underlined and numbered' in block_text
                                  or 'choose the best answer' in block_text or 'identified by a number' in block_text):
                continue
            if by0 > ph - 55:  # footer area (page numbers, "GO ON", "ACT-J08")
                continue
            # Respect y clipping boundaries (for shared pages between passages)
            if y_clip_min is not None and by1 < y_clip_min:
                continue
            if y_clip_max is not None and by0 >= y_clip_max:
                continue
            min_y = min(min_y, by0)
            max_y = max(max_y, by1)

        if max_y <= min_y:
            return None
        # Apply y clipping boundaries
        if y_clip_min is not None:
            min_y = max(min_y, y_clip_min)
        if y_clip_max is not None:
            max_y = min(max_y, y_clip_max)
        # Add padding
        return fitz.Rect(36, min_y - 4, col_boundary + 10, min(ph - 55, max_y + 10))
    else:
        # Reading/Science: full width passage area above questions
        # Some passages span two columns: passage text in left AND right columns,
        # with questions only in the right column below the passage continuation.
        blocks = _get_page_blocks(page)
        first_question_y = ph
        passage_start_y = None
        max_passage_bottom_y = 0
        has_passage_marker = False
        col_mid = pw * 0.5

        for b in blocks:
            if b["type"] != 0:
                continue
            block_text = ""
            for line in b["lines"]:
                for span in line["spans"]:
                    block_text += span["text"]
            block_text = block_text.strip()
            if not block_text:
                continue
            # Skip noise
            if re.match(r'^(GO ON|ACT-|READING TEST|SCIENCE TEST|DIRECTIONS:)', block_text):
                continue
            if 'GO ON TO THE NEXT PAGE' in block_text or 'DO NOT TURN' in block_text or 'DO NOT RETURN' in block_text:
                continue
            if re.match(r'^(END OF TEST|STOP!)', block_text):
                continue
            if re.match(r'^[1-5]\s*$', block_text):
                continue
            # Skip standalone line numbers (e.g. 5, 10, 15, ...)
            if re.match(r'^\d{1,2}$', block_text):
                continue
            # Skip footer-area blocks (page numbers + boilerplate)
            if b["bbox"][1] > ph - 60:
                continue
            # Skip large section number headers
            is_large_header = False
            for line in b["lines"]:
                for span in line["spans"]:
                    if span["size"] >= 30:
                        is_large_header = True
                        break
            if is_large_header:
                continue
            # Detect passage marker or title
            if re.match(r'^(?:PASSAGE|Passage)\s+[IVX]+', block_text):
                passage_start_y = b["bbox"][1]
                has_passage_marker = True
                continue
            # Detect questions
            q_match = re.match(r'^(\d{1,2})\.\s', block_text)
            if q_match:
                # For Science: on pages with a passage marker, numbered items are
                # often experimental procedure steps, not real questions.
                # - Left column numbered items are always procedure steps
                # - Right column items with low numbers (1-10) are also procedure steps
                #   (real questions continue from previous passage: 7+, 13+, 19+, etc.)
                if section_name == "Science" and has_passage_marker:
                    q_num = int(q_match.group(1))
                    is_left = b["bbox"][0] < col_mid
                    if is_left or q_num <= 10:
                        pass  # treat as passage content, fall through
                    else:
                        first_question_y = min(first_question_y, b["bbox"][1])
                        continue
                else:
                    first_question_y = min(first_question_y, b["bbox"][1])
                    continue
            # On continuation pages (no passage marker), the passage starts
            # at the first content block (skip headers/footers)
            if not has_passage_marker and passage_start_y is None:
                by0 = b["bbox"][1]
                # Skip header area (top ~60 pts) and footer
                if by0 > 55 and by0 < ph - 40:
                    passage_start_y = by0
            # Track the bottom of passage content blocks
            by1 = b["bbox"][3]
            if by1 < ph - 35:  # skip footer area
                max_passage_bottom_y = max(max_passage_bottom_y, by1)

        if passage_start_y is None:
            return None

        # Check if this is a two-column passage layout:
        # Left column has passage text that extends BELOW where right-column questions start.
        # In that case, a single full-width clip rect would include question blocks.
        # Detect by checking if any passage content block in the left column
        # extends below the first question's y position.
        left_passage_bottom = 0
        right_passage_bottom = 0
        for b in blocks:
            if b["type"] != 0:
                continue
            btext = ""
            for line in b["lines"]:
                for span in line["spans"]:
                    btext += span["text"]
            btext = btext.strip()
            if not btext:
                continue
            q_m = re.match(r'^(\d{1,2})\.\s', btext)
            if q_m:
                # For Science: on passage pages, low-numbered items are procedure steps
                if section_name == "Science" and has_passage_marker:
                    q_n = int(q_m.group(1))
                    if b["bbox"][0] < col_mid or q_n <= 10:
                        pass  # procedure step, treat as passage content
                    else:
                        continue  # real question, skip from passage content
                else:
                    continue
            if re.match(r'^(GO ON|ACT-|READING TEST|SCIENCE TEST|DIRECTIONS:|END OF TEST|STOP!)', btext):
                continue
            if 'GO ON TO THE NEXT PAGE' in btext or 'DO NOT TURN' in btext or 'DO NOT RETURN' in btext:
                continue
            if re.match(r'^[1-5]\s*$', btext) or re.match(r'^\d{1,2}$', btext):
                continue
            if b["bbox"][1] > ph - 60:
                continue
            is_large = any(span["size"] >= 30 for line in b["lines"] for span in line["spans"])
            if is_large:
                continue
            if re.match(r'^(?:PASSAGE|Passage)\s+[IVX]+', btext):
                continue
            bx0 = b["bbox"][0]
            by1 = b["bbox"][3]
            if bx0 < col_mid:
                left_passage_bottom = max(left_passage_bottom, by1)
            else:
                right_passage_bottom = max(right_passage_bottom, by1)

        # If passage starts at or after questions, there's no passage content
        if passage_start_y >= first_question_y:
            return None

        # Two-column passage: left column text goes below where right column questions start
        if (left_passage_bottom > first_question_y and
                right_passage_bottom > 0 and first_question_y < ph):
            # Check if there's meaningful space above the first question for a full-width rect
            if first_question_y - passage_start_y > 20:
                rects = []
                # Find the split point: bottom of the last left-column block that
                # ends BEFORE first_question_y, so we don't cut a block in half.
                split_y = first_question_y - 10
                for b in blocks:
                    if b["type"] != 0:
                        continue
                    bx0, by0, _, by1 = b["bbox"]
                    # Left-column block that straddles the question boundary
                    if bx0 < col_mid and by0 < first_question_y and by1 > first_question_y - 10:
                        # This block extends below the split — move split above it
                        split_y = min(split_y, by0 - 4)
                # Full-width rect above the split (captures both columns cleanly)
                full_width_rect = fitz.Rect(36, passage_start_y - 4, pw - 36, split_y)
                rects.append(full_width_rect)
                # Left-column-only rect for content at and below the split
                if left_passage_bottom > split_y:
                    left_only_rect = fitz.Rect(36, split_y, col_mid + 10,
                                               min(ph - 55, left_passage_bottom + 5))
                    rects.append(left_only_rect)
                return rects
            else:
                # Passage and questions start at same y (side-by-side layout)
                # Return just the left column
                return fitz.Rect(36, passage_start_y - 4, col_mid + 10,
                                 min(ph - 35, left_passage_bottom + 5))

        # Normal single-region passage
        # If passage and questions start at nearly the same y (side-by-side layout),
        # return just the left column instead of a negative/tiny full-width rect
        if first_question_y - passage_start_y < 20 and left_passage_bottom > 0:
            return fitz.Rect(36, passage_start_y - 4, col_mid + 10,
                             min(ph - 35, left_passage_bottom + 5))
        return fitz.Rect(36, passage_start_y - 4, pw - 36, first_question_y - 10)


def _extract_passages(doc, start_page, end_page, section_name):
    """
    Extract passage content from a range of pages.
    Returns a list of dicts with both rendered image and extracted text.

    For English passages: renders the left column as an image (preserves
    underlines, reference numbers, boxed paragraph markers exactly).
    For Reading/Science: renders the passage area above questions.
    Also extracts text as fallback/searchable content.
    """
    passages = []

    # First, find all passage markers and their page locations + y positions
    passage_locs = []
    for pg_idx in range(start_page, end_page + 1):
        page = doc[pg_idx]
        text = _get_page_text(page)
        for m in PASSAGE_MARKER.finditer(text):
            # Find the y-position of this passage marker on the page
            marker_y = None
            blocks = _get_page_blocks(page)
            for b in blocks:
                if b["type"] != 0:
                    continue
                btext = ""
                for line in b["lines"]:
                    for span in line["spans"]:
                        btext += span["text"]
                btext = btext.strip()
                if re.match(r'^(?:PASSAGE|Passage)\s+' + re.escape(m.group(1)) + r'\b', btext):
                    marker_y = b["bbox"][1]
                    break
            passage_locs.append({
                "number": m.group(1),
                "page": pg_idx,
                "marker_y": marker_y,
            })

    if not passage_locs:
        return []

    # Determine page ranges for each passage
    # For English, a passage's content may extend onto the page where the next
    # passage marker appears (above that marker). Include that shared page.
    for i, ploc in enumerate(passage_locs):
        if i + 1 < len(passage_locs):
            next_ploc = passage_locs[i + 1]
            if section_name == "English" and next_ploc["page"] > ploc["page"]:
                # Include the next passage's start page in this passage's range
                # (content above the next marker belongs to this passage)
                ploc["end_page"] = next_ploc["page"]
                ploc["end_page_y_max"] = next_ploc["marker_y"]
            else:
                ploc["end_page"] = next_ploc["page"] - 1
                ploc["end_page_y_max"] = None
        else:
            ploc["end_page"] = end_page
            ploc["end_page_y_max"] = None

    # Extract text and render images for each passage
    for ploc in passage_locs:
        passage_text_parts = []
        title = ""
        render_pages = []  # (pg_idx, clip_rect) pairs for image rendering

        for pg_idx in range(ploc["page"], ploc["end_page"] + 1):
            page = doc[pg_idx]
            is_first = (pg_idx == ploc["page"])

            # Determine y clipping for shared pages
            y_clip_min = None
            y_clip_max = None
            if is_first and ploc.get("marker_y") is not None:
                # On first page, start from the passage marker
                y_clip_min = ploc["marker_y"]
            if pg_idx == ploc["end_page"] and ploc.get("end_page_y_max") is not None:
                # On last page shared with next passage, stop at next marker
                y_clip_max = ploc["end_page_y_max"]

            # Get clip rect(s) for rendering
            clip = _find_passage_clip_rect(page, section_name, is_first,
                                           y_clip_min=y_clip_min, y_clip_max=y_clip_max)
            if clip:
                if isinstance(clip, list):
                    for c in clip:
                        render_pages.append((pg_idx, c))
                else:
                    render_pages.append((pg_idx, clip))

            # Also extract text as fallback
            if section_name == "English":
                ptext, ptitle = _extract_left_column_text(page, is_first)
            else:
                ptext, ptitle = _extract_passage_text_before_questions(page, is_first)
            if ptitle and not title:
                title = ptitle
            if ptext:
                passage_text_parts.append(ptext)

        # Render passage as image
        passage_image = None
        if render_pages:
            try:
                img_scale = 5.0 if section_name == "English" else 2.5
                passage_image = _render_passage_image(doc, render_pages, section_name, scale=img_scale)
            except Exception as e:
                print(f"Warning: failed to render passage image: {e}")

        # Clean up extracted text
        full_text = "\n\n".join(passage_text_parts).strip()
        cleaned_lines = []
        for line in full_text.split("\n"):
            s = line.strip()
            if not s:
                cleaned_lines.append("")
                continue
            if re.match(r'^(GO ON TO THE NEXT PAGE|ACT-|DO YOUR FIGURING|END OF TEST|STOP!)', s):
                continue
            if re.match(r'^\d{1,3}$', s):
                continue
            if re.match(r'^[1-5]\s*$', s):
                continue
            if s in ('DIRECTIONS:', 'READING TEST', 'SCIENCE TEST', 'ENGLISH TEST'):
                continue
            if 'You are not permitted to use a calculator' in s:
                continue
            cleaned_lines.append(line)
        full_text = "\n".join(cleaned_lines).strip()
        full_text = re.sub(r'\n{3,}', '\n\n', full_text)

        passages.append({
            "number": ploc["number"],
            "title": title,
            "text": full_text,
            "image": passage_image,
            "start_page": ploc["page"],
            "end_page": ploc["end_page"],
            "marker_y": ploc.get("marker_y"),
            "end_page_y_max": ploc.get("end_page_y_max"),
        })

    return passages


def _extract_left_column_text(page, is_first_page):
    """
    Extract text from the left column of an English section page.
    The passage text is on the left (x < ~300), questions on the right.
    """
    blocks = _get_page_blocks(page)
    pw = page.rect.width
    mid_x = pw * 0.52  # Approximate column boundary

    passage_lines = []
    title = ""
    found_passage_marker = False

    for b in blocks:
        if b["type"] != 0:  # skip image blocks
            continue
        x0 = b["bbox"][0]
        x1 = b["bbox"][2]

        # Only left column blocks
        if x0 > mid_x:
            continue

        # Get block text
        block_text = ""
        for line in b["lines"]:
            line_text = ""
            for span in line["spans"]:
                line_text += span["text"]
            block_text += line_text.strip() + "\n"
        block_text = block_text.strip()

        if not block_text:
            continue

        # Skip noise
        if re.match(r'^(DIRECTIONS|ENGLISH TEST|GO ON|ACT-|\d+$)', block_text):
            continue
        if re.match(r'^[1-5]\s*$', block_text):
            continue
        # Skip directions text blocks
        if 'underlined and numbered' in block_text or \
           'choose the best answer' in block_text or \
           'fill in the corresponding oval' in block_text or \
           'Read each passage through once' in block_text or \
           'identified by a number' in block_text:
            continue

        # Detect passage marker
        if re.match(r'^PASSAGE\s+[IVX]+$', block_text):
            found_passage_marker = True
            continue

        # Title is usually the line right after PASSAGE marker (bold/italic)
        if found_passage_marker and not title:
            title = block_text.split("\n")[0].strip()
            found_passage_marker = False
            # Don't add title to passage text, store separately
            continue

        # Skip question-like blocks (start with number followed by period)
        if re.match(r'^\d{1,2}\.\s', block_text):
            continue

        # Skip standalone numbers (question references in boxes)
        if re.match(r'^[\d\s]+$', block_text):
            continue

        passage_lines.append(block_text)

    return "\n".join(passage_lines), title


def _extract_passage_text_before_questions(page, is_first_page):
    """
    Extract passage/experiment text from Reading/Science pages.
    These have passage text in the upper portion and questions below.
    """
    blocks = _get_page_blocks(page)
    passage_parts = []
    title = ""
    found_passage_marker = False
    # On continuation pages, passage text continues from previous page.
    # On the first page, we wait for the PASSAGE marker before collecting.
    in_passage = not is_first_page

    for b in blocks:
        if b["type"] != 0:
            continue

        block_text = ""
        for line in b["lines"]:
            line_text = ""
            for span in line["spans"]:
                line_text += span["text"]
            block_text += line_text.strip() + "\n"
        block_text = block_text.strip()

        if not block_text:
            continue

        # Skip noise
        if re.match(r'^(DIRECTIONS:|READING TEST|SCIENCE TEST|GO ON|ACT-|\d+$)', block_text):
            continue
        if re.match(r'^[1-5]\s*$', block_text):
            continue

        # Detect passage marker
        if re.match(r'^(?:PASSAGE|Passage)\s+[IVX]+', block_text):
            found_passage_marker = True
            in_passage = True
            continue

        # Title after passage marker
        if found_passage_marker and not title:
            # Title line(s)
            first_line = block_text.split("\n")[0].strip()
            if not re.match(r'^\d{1,2}\.\s', first_line):
                title = first_line
                found_passage_marker = False
                # Include remaining text as passage
                remaining = "\n".join(block_text.split("\n")[1:]).strip()
                if remaining:
                    passage_parts.append(remaining)
                continue

        # Once we hit a question number, stop collecting passage text
        if re.match(r'^\d{1,2}\.\s', block_text):
            in_passage = False
            continue

        if in_passage:
            passage_parts.append(block_text)

    return "\n".join(passage_parts), title


def _is_noise_line(line):
    """Check if a line is boilerplate noise from ACT PDFs."""
    s = line.strip()
    if not s:
        return True
    # Page numbers, headers, footers, section markers
    if re.match(r'^(GO ON TO THE NEXT PAGE|ACT-|DO YOUR FIGURING HERE|END OF TEST|STOP!|DO NOT)', s):
        return True
    if re.match(r'^\d{1,3}$', s):  # standalone page numbers
        return True
    # Section number markers like "2 " or "2" alone (ACT section indicators)
    if re.match(r'^[1-5]\s*$', s):
        return True
    return False


def _reassemble_fractions(text):
    """
    Reassemble fractions that PyMuPDF splits across multiple lines.
    Pattern: numerator line, '_' (fraction bar) line, denominator line
    becomes: numerator/denominator

    Examples:
        '1\\n_\\n4' → '1/4'
        '3\\n_\\n5' → '3/5'
        '( 1\\n_\\n64  )' → '(1/64)'
        '√\\n_\\nx' → '√(x)' (square root)
    """
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Check for fraction pattern: current line has a number/expr,
        # next line is '_', line after is denominator
        if (i + 2 < len(lines) and
                lines[i + 1].strip() == '_' and
                lines[i + 2].strip()):
            numerator = stripped
            denominator = lines[i + 2].strip()

            # Check if this is a sqrt symbol (√ over _ over variable)
            if numerator == '√' or numerator.endswith('√'):
                # Square root: √_x → √(x)
                prefix = numerator[:-1] if len(numerator) > 1 else ''
                result.append(prefix + '√(' + denominator + ')')
                i += 3
                continue

            # Regular fraction: num/denom
            # Check if previous line has a leading paren or coefficient
            if result and result[-1].strip().endswith('('):
                # Merge with previous paren: "( " + "1/64"
                prev = result.pop().rstrip()
                result.append(prev + numerator + '/' + denominator)
            else:
                result.append(numerator + '/' + denominator)
            i += 3
            continue

        result.append(lines[i])
        i += 1

    return '\n'.join(result)


def _parse_page_questions(page, page_text, page_num, section_name=None):
    """
    Parse individual questions from a page's text.
    Handles both A/B/C/D and F/G/H/J answer patterns.
    ACT PDFs fragment text heavily across lines - question numbers may appear
    on lines with no text, and options may have values on the next line.
    """
    questions = []
    # Reassemble fractions before parsing
    page_text = _reassemble_fractions(page_text)
    lines = page_text.split("\n")

    # Find question starts: lines beginning with "N." where N is 1-75
    # Allow the line to have no text after the number (e.g. " 2.  ")
    # But reject "N.D" where D is a digit (e.g. "2.5" is not question 2)
    q_starts = []
    for i, line in enumerate(lines):
        m = re.match(r'^\s*(\d{1,2})\.\s*(.*)', line)
        if m:
            num = int(m.group(1))
            rest = m.group(2).strip()
            if 1 <= num <= 75:
                # Reject if next char after "N." is a digit (e.g. "2.5", "1.5")
                if rest and rest[0].isdigit():
                    continue
                # Filter out false positives from "Notes" section instructions
                if rest.startswith('Illustrative figures') or \
                   rest.startswith('Geometric figures') or \
                   rest.startswith('The word'):
                    continue
                # Filter out experiment procedure steps (e.g. "1. A 200.0 mL volume")
                # These typically appear within a passage context, not as standalone questions
                # We'll handle this via dedup - procedure steps won't have A/B/C/D options
                q_starts.append((i, num, rest))

    # Deduplicate: if same question number appears twice, keep the one
    # that has answer options following it (the real question, not a note)
    if q_starts:
        seen = {}
        for list_idx, item in enumerate(q_starts):
            line_idx, num, rest = item
            if num not in seen:
                seen[num] = item
            else:
                # Check which block has option letters (A./B./F./G. etc.)
                next_line = q_starts[list_idx + 1][0] if list_idx + 1 < len(q_starts) else len(lines)
                curr_block = "\n".join(lines[line_idx:next_line])
                if re.search(r'^[A-KFGHJ]\.\s', curr_block, re.MULTILINE):
                    seen[num] = item
        q_starts = sorted(seen.values(), key=lambda x: x[0])

    for idx, (line_idx, q_num, first_line_rest) in enumerate(q_starts):
        # Collect all lines until next question
        end_idx = q_starts[idx + 1][0] if idx + 1 < len(q_starts) else len(lines)
        block_lines = lines[line_idx + 1:end_idx]
        # Prepend any text that was on the question number line
        if first_line_rest:
            block_lines = [first_line_rest] + block_lines
        block_text = "\n".join(block_lines)

        # Skip if too short after removing noise
        clean = "\n".join(l for l in block_lines if not _is_noise_line(l))
        if len(clean.strip()) < 5:
            continue

        # Try to parse options
        q = _parse_question_block(q_num, block_text, page_num)

        # For Math questions with graphical answer options (e.g. graphs for
        # each choice), text option parsing fails.  Create a stub question
        # so the image renderer can still capture the visual options.
        if q is None and section_name in ("Mathematics", "Science") and len(clean.strip()) > 20:
            uses_fghj = q_num % 2 == 0
            q = {
                "question_number": q_num,
                "question_text": " ".join(clean.split()),
                "correct_answer": None,
                "option_labels": "FGHJK" if uses_fghj else "ABCDE",
                "option_a": "(see image)",
                "option_b": "(see image)",
                "option_c": "(see image)",
                "option_d": "(see image)",
                "option_e": None,
                "passage_text": None,
                "question_image": None,
                "difficulty": 3,
            }
            logger.info(f"[GraphQ] Q{q_num} ({section_name}) has graphical options — created stub question")

        if q:
            # Find y position by scanning text blocks for lines starting with "N."
            # This is more reliable than page.search_for which can match
            # question numbers embedded in option text (e.g. "289" matching "2.")
            left_half = page.rect.width * 0.5
            q_pattern = re.compile(rf'^\s*{q_num}\.\s')
            found_pos = False

            blocks = _get_page_blocks(page)
            # Two-pass: first with standard header threshold, then relaxed
            for header_threshold in [page.rect.height * 0.22, page.rect.height * 0.08]:
                if found_pos:
                    break
                for b in blocks:
                    if b["type"] != 0:
                        continue
                    bx0, by0 = b["bbox"][0], b["bbox"][1]
                    # Must be below header
                    if by0 < header_threshold:
                        continue
                    # English questions are in the right column; Math/Reading in the left
                    # Science questions can be in either column
                    if section_name == "English":
                        if bx0 < left_half:
                            continue
                    elif section_name == "Science":
                        pass  # accept blocks in either column
                    elif bx0 > left_half:
                        continue
                    # Check if block text starts with the question number
                    block_text = ""
                    for bline in b["lines"]:
                        for span in bline["spans"]:
                            block_text += span["text"]
                    block_text = block_text.strip()
                    if q_pattern.match(block_text):
                        q["y_pos"] = by0
                        q["x_pos"] = bx0
                        found_pos = True
                        break

            if not found_pos:
                # Fallback: use search_for with stricter filtering
                search_str = f" {q_num}." if q_num < 10 else f"{q_num}."
                rects = page.search_for(search_str)
                if section_name in ("English", "Science"):
                    valid_rects = [r for r in rects if r.y0 > header_threshold]
                else:
                    valid_rects = [r for r in rects if r.y0 > header_threshold and r.x0 < left_half]
                if valid_rects:
                    q["y_pos"] = valid_rects[0].y0
                    q["x_pos"] = valid_rects[0].x0
                else:
                    q["y_pos"] = line_idx * 12
                    q["x_pos"] = 0

            q["page_num"] = page_num
            questions.append(q)

    return questions


def _is_noise_line_question(line, inside_option=False):
    """
    Noise filter for question text lines only (not option values).
    Less aggressive than _is_noise_line — does NOT filter standalone numbers
    since those could be option values like "8" or "128".
    When inside_option=True, even less aggressive (keeps everything except
    boilerplate headers/footers).
    """
    s = line.strip()
    if not s:
        return True
    if re.match(r'^(GO ON TO THE NEXT PAGE|ACT-|DO YOUR FIGURING HERE|END OF TEST|STOP!|DO NOT)', s):
        return True
    # When collecting option values, don't filter any numbers
    if inside_option:
        return False
    # Only filter standalone numbers that look like section markers (1-5)
    if re.match(r'^[1-5]\s*$', s):
        return True
    return False


def _parse_question_block(q_num, text, page_num):
    """
    Parse a single question block into structured data.
    Handles ACT's fragmented text layout where option letters (A./F./etc.)
    may appear on their own line with the value on the next line.
    Preserves original F/G/H/J labels for even-numbered ACT questions.
    """
    opts = {}
    q_text_parts = []
    current_opt = None

    lines_iter = text.split("\n")
    i = 0
    while i < len(lines_iter):
        stripped = lines_iter[i].strip()
        i += 1

        if not stripped:
            continue

        # Skip noise (but use the less aggressive filter that keeps numbers)
        if _is_noise_line_question(stripped):
            continue

        # Check for option lines: "A. text", "F. text", or just "A." / "A.  "
        opt_match = re.match(r'^([A-KFGHJ])\.\s*(.*)', stripped)
        if opt_match:
            letter = opt_match.group(1).upper()
            opt_text = opt_match.group(2).strip()

            # If we already parsed this option letter, we've hit duplicate
            # labels from trailing content (e.g. graph axis labels from a
            # different question's images).  Stop parsing.
            if letter in opts:
                break

            # If we already have all 4 required options (A-D or F-J),
            # only accept option E/K; anything else is trailing noise.
            if len(opts) >= 4 and letter not in ('E', 'K'):
                break

            # If option text is empty or very short, grab next non-empty lines
            # ACT PDFs often put "A.  " then the value on the next line(s)
            if not opt_text:
                # Collect continuation lines until next option or question marker
                while i < len(lines_iter):
                    next_line = lines_iter[i].strip()
                    if not next_line:
                        i += 1
                        continue
                    # Stop if we hit another option letter or question number
                    if re.match(r'^[A-KFGHJ]\.\s*', next_line):
                        break
                    if re.match(r'^\d{1,2}\.\s', next_line):
                        break
                    # Inside options: only skip obvious boilerplate, keep numbers
                    if _is_noise_line_question(next_line, inside_option=True):
                        i += 1
                        continue
                    # Skip standalone numbers (passage refs) if we already have text
                    if opt_text and re.match(r'^\d{1,2}$', next_line) and 1 <= int(next_line) <= 75:
                        i += 1
                        continue
                    opt_text += (" " if opt_text else "") + next_line
                    i += 1
                    # For simple single-value options, one line is usually enough
                    # But allow multi-line for longer text options
                    if len(opt_text) > 3:
                        break

            current_opt = letter
            opts[letter] = opt_text
        elif current_opt and current_opt in opts:
            # Check if this looks like continuation of the current option
            # vs start of question text for next question
            if re.match(r'^\d{1,2}\.\s', stripped):
                break
            # Once we have all 4 required options, only allow continuation
            # if the current option text ends mid-sentence (e.g. "between 400 nm and").
            # Otherwise, remaining lines are likely noise (graph axis labels, etc.).
            if len(opts) >= 4:
                last_word = opts[current_opt].rstrip('.').rsplit(None, 1)[-1].lower() if opts[current_opt].strip() else ""
                mid_sentence = last_word in (
                    'and', 'or', 'the', 'a', 'an', 'of', 'in', 'to', 'from',
                    'for', 'by', 'is', 'was', 'be', 'that', 'than', 'with',
                    'into', 'between', 'not', 'would', 'prevented',
                )
                if not mid_sentence:
                    continue
            # Skip standalone numbers (1-75) — these are passage reference
            # numbers or question numbers leaking from the adjacent column
            if re.match(r'^\d{1,2}$', stripped) and 1 <= int(stripped) <= 75:
                continue
            opts[current_opt] += " " + stripped
        else:
            q_text_parts.append(stripped)

    # Need at least 3 options (some questions might have only A-D or F-J)
    if len(opts) < 3:
        return None

    q_text = " ".join(q_text_parts).strip()
    # Clean up question text
    q_text = re.sub(r'\s+', ' ', q_text).strip()

    # ACT uses alternating labels: odd questions = A/B/C/D/E, even = F/G/H/J/K.
    # Use question number parity as the authority for display labels.
    # Use the actually parsed letters for value extraction.
    expected_fghj = q_num % 2 == 0
    parsed_fghj = any(k in opts for k in 'FGHJK')

    # Labels for extracting values from opts dict
    if parsed_fghj:
        extract_labels = ['F', 'G', 'H', 'J', 'K']
    else:
        extract_labels = ['A', 'B', 'C', 'D', 'E']

    # Labels for display (based on question number, the authoritative source)
    if expected_fghj:
        labels = ['F', 'G', 'H', 'J', 'K']
    else:
        labels = ['A', 'B', 'C', 'D', 'E']

    # Clean up option text
    for k in opts:
        opts[k] = re.sub(r'\s+', ' ', opts[k]).strip()
        # Fix PDF artifact: invisible "0," prefix on numbers < 1,000
        # e.g. "0,200." → "200.", "0,300." → "300."
        opts[k] = re.sub(r'^0,(\d)', r'\1', opts[k])

    # Map positionally: option_a = first label's value, etc.
    # Use extract_labels for lookup (matches parsed PDF letters),
    # display labels (from question number parity) for option_labels.
    positional = ['option_a', 'option_b', 'option_c', 'option_d', 'option_e']
    result = {
        "question_number": q_num,
        "question_text": q_text,
        "correct_answer": None,
        "option_labels": "FGHJK" if expected_fghj else "ABCDE",
        "passage_text": None,
        "question_image": None,
        "difficulty": 3,
    }
    for i, ext_label in enumerate(extract_labels):
        field = positional[i]
        if i < 4:  # option_a through option_d are required
            result[field] = opts.get(ext_label, "")
        else:  # option_e is optional
            result[field] = opts.get(ext_label)

    return result


def _extract_math_shared_info(doc, questions, start_page, end_page):
    """
    Detect shared information blocks in Math sections.

    ACT Math sometimes has blocks like:
        "Use the following information to answer questions 17–19."
        [paragraph + table/figure]
    followed by questions 17, 18, 19.

    This function finds those blocks, renders them as images, and attaches
    them as passage_image to each of the referenced questions.
    """
    if not questions:
        return

    # Build a lookup: question_number -> question dict
    q_by_num = {q["question_number"]: q for q in questions if q.get("question_number")}

    # Pattern: "Use the following information to answer questions X–Y"
    # Various dash types: –, -, —, and "through"
    info_pat = re.compile(
        r'Use the following information to answer\s+questions?\s+(\d+)\s*[\u2013\u2014\-]+\s*(\d+)',
        re.IGNORECASE
    )

    for pg_idx in range(start_page, min(end_page + 1, len(doc))):
        page = doc[pg_idx]
        pw = page.rect.width
        ph = page.rect.height
        page_text = _get_page_text(page)

        for m in info_pat.finditer(page_text):
            q_start = int(m.group(1))
            q_end = int(m.group(2))

            # Find the y-position of the info block header on the page
            blocks = _get_page_blocks(page)
            info_y_start = None
            info_block_bottom = 0

            for b in blocks:
                if b["type"] != 0:
                    continue
                block_text = ""
                for bline in b["lines"]:
                    for span in bline["spans"]:
                        block_text += span["text"]
                block_text = block_text.strip()

                if "Use the following information" in block_text:
                    info_y_start = b["bbox"][1]

            if info_y_start is None:
                continue

            # Find the first referenced question's y_pos to determine where
            # the info block ends
            first_q = q_by_num.get(q_start)
            if not first_q or first_q.get("page_num") != pg_idx + 1:
                continue

            first_q_y = first_q.get("y_pos", 0)

            # The info block spans from info_y_start to just before first_q_y
            if first_q_y <= info_y_start:
                continue

            # Determine x boundaries (left column for math)
            has_figuring = "DO YOUR FIGURING" in page_text
            x_left = 36
            x_right = pw * 0.52 if has_figuring else pw - 36

            # Render the info block as an image
            clip = fitz.Rect(x_left, max(0, info_y_start - 4), x_right, first_q_y - 4)
            if clip.height < 20:
                continue

            try:
                info_image = _render_region_to_base64(page, clip, scale=5.0)
            except Exception as e:
                logger.warning(f"Failed to render shared info block for Q{q_start}-{q_end}: {e}")
                continue

            # Attach as passage_image to all referenced questions
            passage_text = f"Use the following information to answer questions {q_start}\u2013{q_end}."
            for qn in range(q_start, q_end + 1):
                q = q_by_num.get(qn)
                if q:
                    q["passage_image"] = info_image
                    q["passage_text"] = passage_text

            logger.info(f"[MathSharedInfo] Attached shared info block to Q{q_start}-{q_end} (page {pg_idx + 1})")


def _render_embedded_content(doc, questions, start_page, end_page, section_name="Science"):
    """
    Detect and render embedded content (tables, figures) within Science/Reading
    questions where such content sits between the question text and answer options.

    Text extraction captures the question text and options but loses table structure
    (gridlines, alignment). This function finds those regions and renders them as
    question_image so the frontend can display them inline.
    """
    if not questions:
        return

    # Group questions by page
    by_page = {}
    for q in questions:
        pg = q.get("page_num")
        if pg:
            by_page.setdefault(pg, []).append(q)

    for pg_num, page_questions in by_page.items():
        pg_idx = pg_num - 1
        if pg_idx < 0 or pg_idx >= len(doc):
            continue

        page = doc[pg_idx]
        pw = page.rect.width
        ph = page.rect.height
        col_mid = pw * 0.5
        blocks = _get_page_blocks(page)

        # Sort questions on this page by y position
        page_questions.sort(key=lambda q: q.get("y_pos", 0))

        for i, q in enumerate(page_questions):
            # Skip if already has a question_image
            if q.get("question_image"):
                continue

            q_num = q.get("question_number", 0)
            q_y = q.get("y_pos", 0)
            q_x = q.get("x_pos", 0)

            # Determine which column the question is in
            is_right_col = q_x >= col_mid

            # Find the y-extent of this question's region
            # Must find next question in the SAME column (left vs right)
            next_q_y = ph - 60  # default: stop before footer
            for j in range(i + 1, len(page_questions)):
                nq = page_questions[j]
                nq_x = nq.get("x_pos", 0)
                nq_in_right = nq_x >= col_mid
                if nq_in_right == is_right_col:
                    next_q_y = nq.get("y_pos", ph)
                    break

            # Two-pass approach: first find option blocks, then question text block
            # Option pattern: "A." or "F." (may or may not have space after period)
            opt_pattern = re.compile(r'^[A-KFGHJ]\.')
            q_num_pattern = re.compile(rf'^\s*{q_num}\.\s')

            q_text_bottom = q_y  # bottom of question text (just the Q number block)
            first_opt_y = next_q_y  # y of first option

            # Collect relevant blocks in this question's region and column
            q_blocks = []
            for b in blocks:
                if b["type"] != 0:
                    continue
                bx0, by0, bx1, by1 = b["bbox"]
                if by0 < q_y - 2 or by0 >= next_q_y:
                    continue
                if is_right_col and bx0 < col_mid:
                    continue
                if not is_right_col and bx0 >= col_mid:
                    continue
                block_text = ""
                for bline in b["lines"]:
                    for span in bline["spans"]:
                        block_text += span["text"]
                block_text = block_text.strip()
                if not block_text:
                    continue
                if any(noise in block_text for noise in ['GO ON TO THE NEXT PAGE', 'ACT-', 'STOP!', 'DO NOT TURN', 'END OF TEST']):
                    continue
                q_blocks.append((bx0, by0, bx1, by1, block_text))

            # Pass 1: find first option y
            for bx0, by0, bx1, by1, block_text in q_blocks:
                if opt_pattern.match(block_text):
                    first_opt_y = min(first_opt_y, by0)

            # Pass 2: find question number block bottom (the actual question text)
            for bx0, by0, bx1, by1, block_text in q_blocks:
                if q_num_pattern.match(block_text):
                    q_text_bottom = max(q_text_bottom, by1)

            # Now check if there's a gap between question text bottom and first option
            # that might contain a table or figure
            gap = first_opt_y - q_text_bottom
            if gap < 30:
                # No significant gap - no embedded content
                continue

            # Define the gap region
            if is_right_col:
                x_left = col_mid - 10
                x_right = pw - 36
            else:
                x_left = 36
                x_right = col_mid + 10

            gap_rect = fitz.Rect(x_left, q_text_bottom - 2, x_right, first_opt_y - 2)

            # Check if there are vector drawings (table gridlines) in this gap
            has_drawings = _has_drawings_in_rect(page, gap_rect)

            # Also check for table-like text content in the gap
            # (multiple short text blocks at similar y positions = table rows)
            gap_blocks = []
            for b in blocks:
                if b["type"] != 0:
                    continue
                bx0, by0, bx1, by1 = b["bbox"]
                if by0 >= q_text_bottom - 2 and by1 <= first_opt_y + 2:
                    if is_right_col and bx0 >= col_mid - 10:
                        gap_blocks.append(b)
                    elif not is_right_col and bx0 < col_mid + 10:
                        gap_blocks.append(b)

            # Heuristic: if there are drawings OR multiple text blocks in the gap,
            # it's likely a table or structured content
            has_table_content = has_drawings or len(gap_blocks) >= 2

            if not has_table_content:
                continue

            # Render the gap region (table/figure only) as question_image
            try:
                # Use higher scale for narrow columns
                clip_width = gap_rect.width
                scale = max(2.5, 1350 / clip_width) if clip_width > 0 else 5.0
                scale = min(scale, 5.0)

                img_b64 = _render_region_to_base64(page, gap_rect, scale=scale)
                q["question_image"] = img_b64
                logger.info(f"[EmbeddedContent] Rendered table/figure for Q{q_num} on page {pg_num} "
                           f"(gap={gap:.0f}px, drawings={has_drawings}, blocks={len(gap_blocks)})")
            except Exception as e:
                logger.warning(f"Failed to render embedded content for Q{q_num}: {e}")


def _render_question_images(doc, questions, start_page, end_page, only_q_nums=None):
    """
    Render each question (text + options) as an image from the PDF.
    This preserves mathematical notation, fractions, superscripts, etc.
    that text extraction cannot faithfully reproduce.

    For each question, we find its bounding region on the page
    (from question start to next question start) and render as PNG.

    If only_q_nums is set, only render questions with those numbers
    (other questions are still used for position boundaries).
    """
    if not questions:
        return

    # Group questions by page
    by_page = {}
    for q in questions:
        pg = q.get("page_num")
        if pg:
            by_page.setdefault(pg, []).append(q)

    for pg_num, page_questions in by_page.items():
        pg_idx = pg_num - 1  # 0-indexed
        if pg_idx < 0 or pg_idx >= len(doc):
            continue

        page = doc[pg_idx]
        pw = page.rect.width
        ph = page.rect.height

        # Sort questions on this page by y position
        page_questions.sort(key=lambda q: q.get("y_pos", 0))

        # Determine the content column for questions
        # Math section: questions may be on the left half of the page
        # (right half is "DO YOUR FIGURING HERE")
        # Detect by checking if "DO YOUR FIGURING" text exists
        page_text = _get_page_text(page)
        has_figuring_area = "DO YOUR FIGURING" in page_text

        # For math pages with figuring area, questions are in left ~52% of page
        # For other pages, use full width
        if has_figuring_area:
            x_right = pw * 0.52
        else:
            x_right = pw - 36

        x_left = 36  # standard left margin

        for i, q in enumerate(page_questions):
            # Skip if question already has a manually-assigned image (e.g. diagram)
            # We'll set question_image only if it doesn't have one
            q_y_start = q.get("y_pos", 0)

            # For two-column Science pages, limit clip to the question's column
            q_x_pos = q.get("x_pos", 0)
            col_mid = pw * 0.5
            if not has_figuring_area and q_x_pos < col_mid:
                # Question is in left column — don't capture right column content
                q_x_left = x_left
                q_x_right = col_mid + 10
            elif not has_figuring_area and q_x_pos >= col_mid:
                q_x_left = col_mid - 10
                q_x_right = pw - 36
            else:
                q_x_left = x_left
                q_x_right = x_right

            # End y: next question's y_pos IN THE SAME COLUMN, or content bottom.
            # On two-column Science pages, questions in opposite columns at the
            # same y should not limit each other's height.
            q_in_left = q_x_pos < col_mid
            next_same_col = None
            for j in range(i + 1, len(page_questions)):
                nq = page_questions[j]
                nq_in_left = nq.get("x_pos", 0) < col_mid
                if nq_in_left == q_in_left and nq.get("y_pos", 0) > q_y_start + 10:
                    next_same_col = nq
                    break
            if next_same_col:
                q_y_end = next_same_col.get("y_pos", ph) - 4
            else:
                # Last question on page: find actual content bottom instead of
                # extending to page bottom (which captures empty space)
                last_content_y = q_y_start + 50  # minimum
                blocks = _get_page_blocks(page)
                for b in blocks:
                    if b["type"] != 0:
                        continue
                    bx0, by0, bx1, by1 = b["bbox"]
                    # Only blocks in the question column and below this question
                    if bx0 > q_x_right or bx0 < q_x_left - 10 or by0 < q_y_start:
                        continue
                    # Skip footer/noise blocks
                    if by0 > ph - 60:
                        continue
                    block_text = ""
                    for bline in b["lines"]:
                        for span in bline["spans"]:
                            block_text += span["text"]
                    block_text = block_text.strip()
                    if not block_text:
                        continue
                    if re.match(r'^(GO ON|ACT-|STOP!|DO NOT|END OF)', block_text):
                        continue
                    # Skip large section headers
                    is_large = any(span["size"] >= 30 for bline in b["lines"] for span in bline["spans"])
                    if is_large:
                        continue
                    last_content_y = max(last_content_y, by1)
                q_y_end = last_content_y + 10

            # Add a small margin above the question number
            q_y_start = max(0, q_y_start - 6)

            # Minimum height check
            if q_y_end - q_y_start < 30:
                continue

            # Skip questions not in the render set (but keep them for boundaries)
            if only_q_nums and q.get("question_number") not in only_q_nums:
                continue

            # Render the question region
            rect = fitz.Rect(q_x_left, q_y_start, q_x_right, q_y_end)
            try:
                img_b64 = _render_region_to_base64(page, rect, scale=5.0)
                q["question_image"] = img_b64
            except Exception as e:
                print(f"Warning: failed to render Q{q.get('question_number')} image: {e}")


def _extract_answer_key(doc) -> dict[str, dict[int, str]]:
    """
    Extract the answer key from the end of an ACT PDF.

    ACT "My Answer Key" PDFs have separate pages per subject with tables:
      [Subject] Number | Correct Answer | Correct (Mark 1) | Reporting Categories
    Each row's data appears on separate lines in PyMuPDF text extraction:
      number (line), letter (line), reporting_category (line), repeating.

    Subject sections are identified by headers like:
      "English Test 1 Section", "Mathematics Test 2 Section", etc.

    Returns a dict keyed by subject name -> {question_number: correct_answer}.
    Answer letters are preserved as-is (F/G/H/J are NOT mapped to A/B/C/D).
    """
    total_pages = len(doc)

    answer_key = {}  # subject -> {q_num: answer}

    # Scan last ~15 pages for scoring key sections
    # Subject header patterns (match inline while scanning lines)
    # Formats: "English Test 1 Section", "Test 1: English—Scoring Key", "English Scoring Key"
    _subj_patterns = [
        (re.compile(r'English\s+Test\s+1\s+Section|English.{0,3}Scoring\s+Key|Test\s+1.{0,3}English', re.IGNORECASE), 'English'),
        (re.compile(r'Mathematics\s+Test\s+2\s+Section|Mathematics.{0,3}Scoring\s+Key|Test\s+2.{0,3}Mathematics', re.IGNORECASE), 'Math'),
        (re.compile(r'Reading\s+Test\s+3\s+Section|Reading.{0,3}Scoring\s+Key|Test\s+3.{0,3}Reading', re.IGNORECASE), 'Reading'),
        (re.compile(r'Science\s+Test\s+4\s+Section|Science.{0,3}Scoring\s+Key|Test\s+4.{0,3}Science', re.IGNORECASE), 'Science'),
    ]

    # Reporting category markers that identify which subject's answer block follows.
    # On shared pages, data may appear: Science Q1-40, then Reading Q1-40
    # with only the reporting category header row distinguishing them.
    _cat_markers = {
        'POW': 'English', 'KLA': 'English', 'CSE': 'English',
        'PHM': 'Math', 'IES': 'Math',
        'KID': 'Reading', 'IKI': 'Reading',
        'IOD': 'Science', 'SIN': 'Science', 'EMI': 'Science',
    }

    for pg_idx in range(max(0, total_pages - 15), total_pages):
        page = doc[pg_idx]
        text = _get_page_text(page)

        # Quick check: does this page have any scoring key content?
        if not re.search(r'Scoring\s+Key|Test\s+\d\s+Section', text, re.IGNORECASE):
            continue

        # Scan lines, switching current_subject when a header is encountered.
        # This handles pages with multiple subjects (e.g. Reading + Science).
        lines = text.split('\n')
        current_subject = None
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            # Check if this line is a subject header
            for pat, subj in _subj_patterns:
                if pat.search(line):
                    current_subject = subj
                    if current_subject not in answer_key:
                        answer_key[current_subject] = {}
                    break

            # Check for reporting category markers that switch the active subject.
            # e.g. a line "KID" followed by "CS" and "IKI" means Reading data follows.
            if line in _cat_markers:
                new_subj = _cat_markers[line]
                if new_subj != current_subject:
                    current_subject = new_subj
                    if current_subject not in answer_key:
                        answer_key[current_subject] = {}

            if not current_subject:
                continue

            # Look for a question number (1-75, with optional trailing period)
            num_match = re.match(r'^(\d{1,2})\.?$', line)
            if not num_match:
                continue

            q_num = int(num_match.group(1))
            if q_num < 1 or q_num > 75:
                continue

            # Next non-empty line should be the answer letter
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break

            answer_line = lines[i].strip()
            i += 1

            # Answer should be a single letter A-K or F/G/H/J
            answer_match = re.match(r'^([A-KFGHJ])$', answer_line, re.IGNORECASE)
            if not answer_match:
                continue

            answer = answer_match.group(1).upper()
            answer_key[current_subject][q_num] = answer

            # Skip the reporting category line(s) — we don't need them
            # but advance past them so the next number is found correctly
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines):
                cat_line = lines[i].strip()
                # If it's a reporting category (not a number), skip it
                if not re.match(r'^\d{1,2}\.?$', cat_line):
                    i += 1

    # If table-based parsing found nothing, try compact format:
    # "CORRECT ANSWER EHBFDKBGDJ CGCFCHEHAK ..." (all answers as one string)
    if not any(answer_key.get(s) for s in ['English', 'Math', 'Reading', 'Science']):
        _parse_compact_answer_key(doc, answer_key)

    return answer_key


def _parse_compact_answer_key(doc, answer_key):
    """
    Parse compact answer key format found in scanned ACT PDFs.
    Uses word-level bounding box data to separate multi-column layouts
    (Math/Reading/Science side by side on the same page).
    """
    total_pages = len(doc)
    subject_expected = {'Math': 60, 'Reading': 40, 'Science': 40, 'English': 75}

    for pg_idx in range(max(0, total_pages - 10), total_pages):
        page = doc[pg_idx]
        text = _get_page_text(page)
        if 'CORRECT' not in text.upper():
            continue

        # Use OCR word data with positions for column detection
        blocks = _get_page_blocks(page)
        if not blocks:
            continue

        # Collect all words with their positions
        words = []
        for b in blocks:
            if b.get('type', 0) != 0:
                continue
            for line in b.get('lines', []):
                for span in line.get('spans', []):
                    bbox = span.get('bbox', (0, 0, 0, 0))
                    words.append({
                        'text': span['text'].strip(),
                        'x': bbox[0], 'y': bbox[1],
                        'x1': bbox[2], 'y1': bbox[3],
                    })

        # Find subject headers and their "CORRECT ANSWER" y-positions
        subject_y = {}  # subject_name -> y of "CORRECT ANSWER"
        for w in words:
            t = w['text'].upper()
            if t == 'MATHEMATICS':
                subject_y['Math'] = None
            elif t == 'READING':
                subject_y['Reading'] = None
            elif t == 'SCIENCE':
                subject_y['Science'] = None

        # Find "CORRECT" words and match to nearest subject
        correct_positions = []
        for w in words:
            if w['text'].upper() == 'CORRECT':
                correct_positions.append(w['y'])

        # Sort subjects by their header y-position
        subject_headers = []
        for w in words:
            t = w['text'].upper()
            if t in ('MATHEMATICS', 'READING', 'SCIENCE'):
                name = {'MATHEMATICS': 'Math', 'READING': 'Reading', 'SCIENCE': 'Science'}[t]
                subject_headers.append((w['y'], name))
        subject_headers.sort()

        # Match each subject to the nearest "CORRECT" y-position
        for header_y, subj_name in subject_headers:
            best_y = None
            best_dist = float('inf')
            for cy in correct_positions:
                dist = cy - header_y  # CORRECT should be below header
                if 0 < dist < 30 and dist < best_dist:
                    best_dist = dist
                    best_y = cy
            if best_y is not None:
                subject_y[subj_name] = best_y

        # For each subject with a known CORRECT ANSWER y-position,
        # collect all letter groups at that y (within tolerance)
        for subj_name, correct_y in subject_y.items():
            if correct_y is None:
                continue
            expected = subject_expected.get(subj_name, 60)
            y_tolerance = 8

            # Find answer groups: words near correct_y that look like letter sequences
            answer_words = []
            for w in words:
                if abs(w['y'] - correct_y) > y_tolerance:
                    continue
                t = w['text'].upper()
                # Must be mostly A-K letters and at least 5 chars
                letter_count = sum(1 for c in t if c in 'ABCDEFGHJK')
                if letter_count >= 5 and letter_count / max(len(t), 1) > 0.7:
                    answer_words.append((w['x'], t))

            # Sort by x-position and concatenate
            answer_words.sort()
            letters = ''
            for _, word_text in answer_words:
                letters += re.sub(r'[^A-K]', '', word_text)

            if letters:
                _store_compact_answers(answer_key, subj_name, expected, letters)

    # Also try parsing sequential single-letter answers from scoring key pages
    _parse_sequential_answer_key(doc, answer_key)


def _store_compact_answers(answer_key, subject, expected_count, letters):
    """Store compact answer letters into the answer_key dict."""
    if len(letters) < expected_count * 0.8:
        return  # Not enough letters, probably misparse
    letters = letters[:expected_count]
    if subject not in answer_key:
        answer_key[subject] = {}
    for i, ch in enumerate(letters):
        if ch in 'ABCDEFGHJK':
            answer_key[subject][i + 1] = ch
    logger.info(f"[AnswerKey] Compact format: {subject} = {len(answer_key[subject])} answers from {len(letters)} letters")


def _parse_sequential_answer_key(doc, answer_key):
    """
    Parse scoring key pages where answers are listed as sequential single letters.
    E.g., page has "Scoring Key" header and then lists letters G, A, J, C, ...
    one per line, in question order.
    """
    total_pages = len(doc)
    subject_patterns = [
        (r'English.*Scoring\s+Key', 'English', 75),
        (r'Mathematics.*Scoring\s+Key', 'Math', 60),
        (r'Reading.*Scoring\s+Key', 'Reading', 40),
        (r'Science.*Scoring\s+Key', 'Science', 40),
    ]

    for pg_idx in range(max(0, total_pages - 15), total_pages):
        page = doc[pg_idx]
        text = _get_page_text(page)

        subject = None
        expected = 0
        for pat, subj, count in subject_patterns:
            if re.search(pat, text, re.IGNORECASE):
                subject = subj
                expected = count
                break

        if not subject or subject in answer_key and len(answer_key[subject]) >= expected * 0.8:
            continue

        # Collect all single-letter lines that are valid answer letters
        lines = text.split('\n')
        letters = []
        for line in lines:
            s = line.strip()
            if re.match(r'^[A-KFGHJ]$', s):
                letters.append(s)

        if len(letters) >= expected * 0.8:
            if subject not in answer_key:
                answer_key[subject] = {}
            for i, ch in enumerate(letters[:expected]):
                answer_key[subject][i + 1] = ch
            logger.info(f"[AnswerKey] Sequential format: {subject} = {len(answer_key[subject])} answers")


def parse_answer_key(text: str) -> dict[int, str]:
    """Parse answer key from text (legacy simple version)."""
    answers = {}
    pattern = re.compile(r'(\d+)[.)]\s*([A-Ka-kFGHJfghj])')
    fghj_map = {'F': 'A', 'G': 'B', 'H': 'C', 'J': 'D', 'K': 'E'}
    for match in pattern.finditer(text):
        q_num = int(match.group(1))
        answer = match.group(2).upper()
        answer = fghj_map.get(answer, answer)
        answers[q_num] = answer
    return answers

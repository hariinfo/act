import re
import base64
import io
import fitz  # PyMuPDF

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
    blocks = page.get_text("dict")["blocks"]
    text = page.get_text()
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

    # Step 1: Detect section boundaries
    sections_raw = []
    for pg_idx in range(total_pages):
        page = doc[pg_idx]
        text = page.get_text()
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
                text = doc[pg_idx].get_text()
                if re.search(r'END\s+OF\s+TEST\s+\d', text) or re.search(r'STOP!\s+DO\s+NOT', text):
                    end_page = pg_idx
                    break
            sec["end_page"] = end_page

    if not sections_raw:
        doc.close()
        return {
            "sections": [],
            "total_pages": total_pages,
            "total_questions": 0,
            "text_preview": doc[0].get_text()[:2000] if total_pages > 0 else "",
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
            page_text = page.get_text()
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

            # Parse questions from this page
            page_questions = _parse_page_questions(page, page_text, pg_idx + 1, section_name=sec["name"])

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
        # Also render for Science questions that have diagrams/figures nearby
        if sec["name"] == "Math":
            _render_question_images(doc, section_questions, sec["start_page"], sec["end_page"])

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
        text = page.get_text()
        if re.search(r'(?:Correct\s*Answer|Answer\s*Key|ANSWER\s*KEY)', text, re.IGNORECASE):
            answer_key_text += f"\n=== PAGE {pg_idx + 1} ===\n{text}"

    # Text preview from first few pages
    preview_text = ""
    for i in range(min(3, total_pages)):
        preview_text += doc[i].get_text() + "\n"

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
        blocks = page.get_text("dict")["blocks"]
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
        blocks = page.get_text("dict")["blocks"]
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
        text = page.get_text()
        for m in PASSAGE_MARKER.finditer(text):
            # Find the y-position of this passage marker on the page
            marker_y = None
            blocks = page.get_text("dict")["blocks"]
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
    blocks = page.get_text("dict")["blocks"]
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
    blocks = page.get_text("dict")["blocks"]
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
        if q:
            # Find y position by scanning text blocks for lines starting with "N."
            # This is more reliable than page.search_for which can match
            # question numbers embedded in option text (e.g. "289" matching "2.")
            header_threshold = page.rect.height * 0.22
            left_half = page.rect.width * 0.5
            q_pattern = re.compile(rf'^\s*{q_num}\.\s')
            found_pos = False

            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if b["type"] != 0:
                    continue
                bx0, by0 = b["bbox"][0], b["bbox"][1]
                # Must be below header
                if by0 < header_threshold:
                    continue
                # English questions are in the right column; others in the left
                if section_name != "English" and bx0 > left_half:
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
                if section_name == "English":
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

    # Determine if this question uses F/G/H/J/K labels (ACT even-numbered questions)
    uses_fghj = any(k in opts for k in 'FGHJK')

    # Store options positionally (option_a=first, option_b=second, etc.)
    # but preserve original labels for display
    if uses_fghj:
        labels = ['F', 'G', 'H', 'J', 'K']
    else:
        labels = ['A', 'B', 'C', 'D', 'E']

    # Clean up option text
    for k in opts:
        opts[k] = re.sub(r'\s+', ' ', opts[k]).strip()

    # Map positionally: option_a = first label's value, etc.
    positional = ['option_a', 'option_b', 'option_c', 'option_d', 'option_e']
    result = {
        "question_number": q_num,
        "question_text": q_text,
        "correct_answer": None,
        "option_labels": "FGHJK" if uses_fghj else "ABCDE",
        "passage_text": None,
        "question_image": None,
        "difficulty": 3,
    }
    for i, label in enumerate(labels):
        field = positional[i]
        if i < 4:  # option_a through option_d are required
            result[field] = opts.get(label, "")
        else:  # option_e is optional
            result[field] = opts.get(label)

    return result


def _render_question_images(doc, questions, start_page, end_page):
    """
    Render each question (text + options) as an image from the PDF.
    This preserves mathematical notation, fractions, superscripts, etc.
    that text extraction cannot faithfully reproduce.

    For each question, we find its bounding region on the page
    (from question start to next question start) and render as PNG.
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
        page_text = page.get_text()
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

            # End y: either next question's y_pos or bottom of question content
            if i + 1 < len(page_questions):
                q_y_end = page_questions[i + 1].get("y_pos", ph) - 4
            else:
                # Last question on page: find actual content bottom instead of
                # extending to page bottom (which captures empty space)
                last_content_y = q_y_start + 50  # minimum
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if b["type"] != 0:
                        continue
                    bx0, by0, bx1, by1 = b["bbox"]
                    # Only blocks in the question column and below this question
                    if bx0 > x_right or by0 < q_y_start:
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

            # Render the question region
            rect = fitz.Rect(x_left, q_y_start, x_right, q_y_end)
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
    for pg_idx in range(max(0, total_pages - 15), total_pages):
        page = doc[pg_idx]
        text = page.get_text()

        # Detect subject from section headers
        current_subject = None
        if re.search(r'English\s+Test\s+1\s+Section|English\s+Scoring\s+Key', text, re.IGNORECASE):
            current_subject = 'English'
        elif re.search(r'Mathematics\s+Test\s+2\s+Section|Mathematics\s+Scoring\s+Key', text, re.IGNORECASE):
            current_subject = 'Math'
        elif re.search(r'Reading\s+Test\s+3\s+Section|Reading\s+Scoring\s+Key', text, re.IGNORECASE):
            current_subject = 'Reading'
        elif re.search(r'Science\s+Test\s+4\s+Section|Science\s+Scoring\s+Key', text, re.IGNORECASE):
            current_subject = 'Science'

        if not current_subject:
            continue

        if current_subject not in answer_key:
            answer_key[current_subject] = {}

        # Parse the table data from the extracted text.
        # PyMuPDF extracts each table cell on its own line, so the pattern is:
        #   number_line, answer_letter_line, reporting_category_line (repeating)
        # We scan lines looking for: a number (1-75), followed by a single letter line.
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1

            # Look for a question number (1-75 as standalone number)
            num_match = re.match(r'^(\d{1,2})$', line)
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
                if not re.match(r'^\d{1,2}$', cat_line):
                    i += 1

    return answer_key


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

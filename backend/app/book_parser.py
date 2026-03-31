"""
Parser for ACT prep books (e.g., "Ultimate Guide to the Math ACT").

These books have a different structure from official ACT practice tests:
- Organized by topic sections (e.g., "2.1 Problems on integers, primes and digits")
- Each section has numbered questions with A-E options
- Solutions sections follow with answers like "1. (D) explanation..."
- Math notation doesn't extract cleanly as text, so questions are rendered as images
"""

import re
import base64
import io
import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def parse_act_book_pdf(pdf_bytes: bytes) -> dict:
    """Parse an ACT prep book PDF into sections with questions and images."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    # Step 1: Find all problem sections and solution sections
    problem_sections = []  # [{section_id, title, topic, start_page, start_y}, ...]
    solution_sections = []  # [{section_id, title, start_page}, ...]

    prob_pat = re.compile(r'(\d+\.\d+)\s+((?:Problems|Practice problems|practice problems)\s+(?:on|for)\s+.+)', re.IGNORECASE)
    sol_pat = re.compile(r'(\d+\.\d+)\s+(Solutions\s+to\s+.+)', re.IGNORECASE)

    for pg_idx in range(total_pages):
        page = doc[pg_idx]
        text = page.get_text()

        for m in prob_pat.finditer(text):
            section_id = m.group(1)
            title = m.group(2).strip()
            # Extract topic from title: "Problems on X" -> "X", "Practice problems for X" -> "X"
            topic = re.sub(r'^(?:Practice\s+)?[Pp]roblems\s+(?:on|for)\s+', '', title).strip()
            # Capitalize first letter
            if topic:
                topic = topic[0].upper() + topic[1:]

            # Find y-position of this header on the page
            blocks = page.get_text("dict")["blocks"]
            header_y = 0
            for b in blocks:
                if b.get("type") != 0:
                    continue
                block_text = ""
                for line in b["lines"]:
                    for span in line["spans"]:
                        block_text += span["text"]
                if section_id in block_text and ("Problems" in block_text or "problems" in block_text):
                    header_y = b["bbox"][1]
                    break

            problem_sections.append({
                "section_id": section_id,
                "title": title,
                "topic": topic,
                "start_page": pg_idx,
                "start_y": header_y,
            })

        for m in sol_pat.finditer(text):
            section_id = m.group(1)
            solution_sections.append({
                "section_id": section_id,
                "start_page": pg_idx,
            })

    if not problem_sections:
        text_preview = doc[0].get_text()[:2000] if total_pages > 0 else ""
        doc.close()
        return {
            "sections": [],
            "total_pages": total_pages,
            "total_questions": 0,
            "text_preview": text_preview,
        }

    logger.info(f"[BookParser] Found {len(problem_sections)} problem sections, {len(solution_sections)} solution sections")

    # Step 2: Determine page ranges for each problem section
    for i, ps in enumerate(problem_sections):
        # Start with either the next problem section or end of doc as upper bound
        if i + 1 < len(problem_sections):
            next_ps = problem_sections[i + 1]
            if next_ps["start_page"] == ps["start_page"]:
                ps["end_page"] = ps["start_page"]
            else:
                ps["end_page"] = next_ps["start_page"] - 1
        else:
            ps["end_page"] = min(ps["start_page"] + 10, total_pages - 1)

        # Cap at the matching solution section so we don't extract solutions as questions
        sol = _find_solution_section(ps["section_id"], solution_sections)
        if sol and sol["start_page"] > ps["start_page"]:
            ps["end_page"] = min(ps["end_page"], sol["start_page"] - 1)

    # Step 3: Extract answers from solution sections
    answer_keys = {}  # section_id -> {q_num: answer_letter}
    sol_map = {s["section_id"]: s for s in solution_sections}

    for sol in solution_sections:
        sid = sol["section_id"]
        # Determine end page for this solution section
        sol_end = total_pages - 1
        # Find next section (problem or solution) after this one
        all_markers = [(ps["start_page"], ps["section_id"]) for ps in problem_sections]
        all_markers += [(s["start_page"], s["section_id"]) for s in solution_sections]
        all_markers.sort(key=lambda x: x[0])

        found_current = False
        for pg, marker_id in all_markers:
            if marker_id == sid and pg == sol["start_page"]:
                found_current = True
                continue
            if found_current and pg > sol["start_page"]:
                sol_end = pg - 1
                break

        answers = {}
        ans_pat = re.compile(r'(\d{1,2})\.\s+\(([A-E])\)')
        for pg_idx in range(sol["start_page"], min(sol_end + 1, total_pages)):
            text = doc[pg_idx].get_text()
            for m in ans_pat.finditer(text):
                q_num = int(m.group(1))
                answers[q_num] = m.group(2)

        answer_keys[sid] = answers
        logger.info(f"[BookParser] Section {sid}: extracted {len(answers)} answers")

    # Step 4: Extract questions from each problem section
    all_questions = []
    global_q_num = 0

    for ps in problem_sections:
        section_answers = answer_keys.get(ps["section_id"], {})
        section_questions = _extract_section_questions(
            doc, ps, section_answers
        )
        all_questions.extend(section_questions)
        global_q_num += len(section_questions)
        logger.info(f"[BookParser] Section {ps['section_id']} '{ps['topic']}': {len(section_questions)} questions")

    # Assign global sequential question numbers
    for i, q in enumerate(all_questions, 1):
        q["question_number"] = i

    answers_total = sum(1 for q in all_questions if q.get("correct_answer"))

    doc.close()

    return {
        "sections": [{
            "name": "Math",
            "start_page": 1,
            "end_page": total_pages,
            "time_limit_minutes": 60,
            "questions": all_questions,
            "images_count": sum(1 for q in all_questions if q.get("question_image")),
        }],
        "total_pages": total_pages,
        "total_questions": len(all_questions),
        "answers_extracted": answers_total,
        "answer_key_by_subject": {"Math": answers_total},
        "text_preview": "",
    }


def _find_solution_section(section_id, solution_sections):
    """Find the matching solution section for a problem section."""
    for sol in solution_sections:
        if sol["section_id"] == section_id:
            return sol
    return None


def _extract_section_questions(doc, ps, answers):
    """Extract questions from a single problem section's page range.

    The book uses a two-column layout: questions flow down the left column
    first (x < ~306), then down the right column (x >= ~306). Each question
    must be clipped to its own column to avoid capturing content from the
    adjacent column.
    """
    questions = []

    start_page = ps["start_page"]
    end_page = ps["end_page"]
    col_mid = 306  # approximate column midpoint for 612pt-wide pages

    # Collect all question start positions across all pages, with column info
    # (page_idx, col, y_pos, x_pos, q_num)
    #   col: 'L' for left column, 'R' for right column
    q_positions = []

    for pg_idx in range(start_page, end_page + 1):
        page = doc[pg_idx]
        blocks = page.get_text("dict")["blocks"]

        for b in blocks:
            if b.get("type") != 0:
                continue
            block_text = ""
            for line in b["lines"]:
                for span in line["spans"]:
                    block_text += span["text"]
            block_text = block_text.strip()

            if not block_text:
                continue

            m = re.match(r'^(\d{1,2})\.\s', block_text)
            if not m:
                continue

            q_num = int(m.group(1))
            bx0 = b["bbox"][0]
            by0 = b["bbox"][1]

            # Skip section headers
            if ps["section_id"] in block_text and ("Problems" in block_text or "problems" in block_text):
                continue
            # Skip "Solutions to" headers
            if "Solutions" in block_text or "solutions" in block_text:
                continue

            # Skip solution-style entries like "1. (D)" or "1.  (D)\nExplanation..."
            if re.match(r'^(\d{1,2})\.\s+\([A-E]\)', block_text):
                continue

            # Skip page numbers (standalone small numbers near top/bottom)
            if len(block_text) <= 4 and (by0 < 50 or by0 > 750):
                continue

            col = "L" if bx0 < col_mid else "R"
            q_positions.append((pg_idx, col, by0, bx0, q_num))

    # Sort: by page, then left column first, then by y within each column
    q_positions.sort(key=lambda x: (x[0], 0 if x[1] == "L" else 1, x[2]))

    # For each question, find the content bottom by scanning all blocks in
    # its column between this question's y and the next question's y (or
    # the bottom of the page/column).
    for i, (pg_idx, col, y_start, x_start, q_num) in enumerate(q_positions):
        page = doc[pg_idx]
        pw = page.rect.width
        ph = page.rect.height

        # Column x-boundaries
        if col == "L":
            x_left = 30
            x_right = col_mid - 5
        else:
            x_left = col_mid - 5
            x_right = pw - 30

        # Determine y_end: next question in same page+column, or page bottom
        y_end = ph - 30
        for j in range(i + 1, len(q_positions)):
            nxt_pg, nxt_col, nxt_y, _, _ = q_positions[j]
            if nxt_pg == pg_idx and nxt_col == col:
                y_end = nxt_y - 4
                break
            if nxt_pg > pg_idx:
                break

        # Find the actual content bottom within this region by scanning blocks
        content_bottom = y_start + 20  # minimum
        blocks = page.get_text("dict")["blocks"]
        for b in blocks:
            if b.get("type") != 0:
                continue
            bbx0 = b["bbox"][0]
            bby0 = b["bbox"][1]
            bby1 = b["bbox"][3]

            # Block must be in the same column
            if col == "L" and bbx0 >= col_mid:
                continue
            if col == "R" and bbx0 < col_mid - 20:
                continue

            # Block must be in the y range of this question
            if bby0 >= y_start - 2 and bby1 <= y_end + 10:
                content_bottom = max(content_bottom, bby1)

        y_end_clip = min(content_bottom + 5, ph)
        y_start_clip = max(0, y_start - 4)

        if y_end_clip - y_start_clip < 20:
            continue

        # Render question region as image (column-constrained)
        clip = fitz.Rect(x_left, y_start_clip, x_right, y_end_clip)
        question_image = _render_region(page, clip, scale=4.0)

        q = {
            "question_number": q_num,  # will be overwritten with global number
            "question_text": "",  # math notation doesn't extract well as text
            "question_image": question_image,
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "option_e": "E",
            "option_labels": "ABCDE",
            "correct_answer": answers.get(q_num),
            "topic": ps["topic"],
            "difficulty": 3,
        }
        questions.append(q)

    return questions



def _render_region(page, clip, scale=3.0):
    """Render a page region as a base64 PNG data URI."""
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    img_bytes = pix.tobytes("png")
    b64 = base64.b64encode(img_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"

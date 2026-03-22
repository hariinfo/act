# PDF Passage Image Extraction - Lessons Learned

## ACT PDF Layout Overview
- Pages are ~612x792 pts. Column midpoint at pw * 0.5 (~306).
- Left column: x < 306. Right column: x >= 306.
- Header area: y < ~80. Footer area: y > ph - 60.
- Noise blocks: "GO ON TO THE NEXT PAGE", "ACT-...", "DO NOT TURN", "END OF TEST", "STOP!", large section number headers (font size >= 30), standalone page numbers.

## Science Passage Extraction

### Problem 1: Numbered Procedure Steps Misdetected as Questions
Science passages often contain numbered experimental steps (e.g., "1. A 200.0 mL volume was placed...") that match the question regex `^\d{1,2}\.\s`. This caused the clip rect to stop at the first step, truncating the passage.

**Fix**: On Science pages WITH a passage marker, treat numbered items as procedure steps (not questions) if:
- They are in the LEFT column, OR
- They have a low number (1-10) even in the right column

Real Science questions have higher numbers (13+, 19+, 25+, etc.) since each passage has ~6 questions numbered sequentially across the entire test. Procedure steps restart at 1 within each passage.

```python
if section_name == "Science" and has_passage_marker:
    q_num = int(q_match.group(1))
    is_left = b["bbox"][0] < col_mid
    if is_left or q_num <= 10:
        pass  # procedure step, treat as passage content
```

### Problem 1b: Side-by-Side Passage and Questions (Same Starting Y)
Some Science passages have passage content in the left column and questions in the right column, both starting at the same y-position (~y=80). This produces negative-height clip rects when calculating `passage_start_y - first_question_y`.

**Fix**: When `first_question_y - passage_start_y < 20`, the layout is side-by-side. Return just the left column as the clip rect instead of a full-width rect.
```python
if first_question_y - passage_start_y < 20 and left_passage_bottom > 0:
    return fitz.Rect(36, passage_start_y - 4, col_mid + 10, left_passage_bottom + 5)
```

### Problem 2: Two-Column Rendering Produced Narrow Images
When passage content spans both columns (left has text extending below where right-column questions start), the old approach rendered two narrow column strips (~280px wide) and stitched them vertically. This looked inconsistent with full-width single-rect passages.

**Fix**: Use a full-width rect above the first question line (captures both columns), then a left-column-only rect for remaining content below the question line.
```python
# Full-width rect above questions (both columns)
full_width_rect = fitz.Rect(36, passage_start_y - 4, pw - 36, first_question_y - 10)
# Left-column-only rect for content below question line
left_only_rect = fitz.Rect(36, first_question_y - 10, col_mid + 10, left_passage_bottom + 5)
```

### Problem 3: Questions-Only Pages Returning Broken Clip Rects
Continuation pages with only questions (no passage content) had answer option text (e.g., "F. 1/6") treated as passage content, producing broken two-column rects where y_end < y_start.

**Fix**: Add early check `passage_start_y >= first_question_y` BEFORE the two-column detection. If "passage" starts at or after the first question, there's no real passage content.

## English Passage Extraction

### Problem 1: Shared Pages Between Passages
English passages can share a page - e.g., Passage IV's tail content appears above the "PASSAGE V" marker on the same page. The old code set `end_page = next_passage_page - 1`, skipping the tail content entirely.

**Fix**:
1. Detect the y-position of each passage marker on its page.
2. Extend current passage's `end_page` to include the shared page, with `y_clip_max` set to the next passage's marker y-position.
3. Next passage uses `y_clip_min` from its own marker position.
4. `_find_passage_clip_rect` accepts `y_clip_min`/`y_clip_max` to constrain the clip region.
5. Question-to-passage assignment uses the same y-boundaries to correctly assign questions on shared pages.

### Problem 2: Footer Noise in Rendered Images
Footer blocks like "2GO ON TO THE NEXT PAGE.ACT-J08" and "11ACT-J08" were appearing in passage images. The original regex `^(GO ON|ACT-...)` didn't match because the page number is prepended (e.g., "2GO ON..." or "11ACT-J08").

**Fix**:
- Use `in` checks instead of `^` anchored regex: `'GO ON TO THE NEXT PAGE' in block_text` and `'ACT-' in block_text`
- Also filter `'STOP!'`, `'DO NOT TURN'`, `'END OF TEST'` using `in` checks
- Lower footer y-threshold from `ph - 40` to `ph - 55` (footers start at y=738, ph=792)
- Lower max_y padding from `ph - 35` to `ph - 55`

### Problem 3: Passage Marker from Next Passage Leaking into Current Passage Image
When using `y_clip_max` to limit a passage on a shared page, the boundary comparison `by0 > y_clip_max` used strict greater-than. Since the next passage marker's y-position IS the `y_clip_max` value, the marker block (with `by0 == y_clip_max`) was not filtered out.

**Fix**: Use `by0 >= y_clip_max` (greater-than-or-equal) to exclude the marker block itself.

### English Left Column Specifics
- English passage content is in the left column (x < pw * 0.48 ≈ 294).
- The clip rect width is `col_boundary + 10` to capture the full left column.
- Standalone numbers in the left column (e.g., "1", "19") are underlined question reference markers in the passage text — they are essential passage content and should NOT be filtered.
- "STOP! DO NOT TURN THE PAGE..." text can start at x=242 which is within the left column boundary — must be explicitly filtered.

## Reading Passage Extraction

### Problem: Two-Column Passages Truncated
Reading Passage III had a two-column layout where left column text extended below where right column questions started. A single full-width clip rect stopped at the first question, cutting off left-column content.

**Fix**: Same two-column detection as Science - full-width rect above questions, left-column-only rect below. This applies to both Science and Reading.

## General Principles

1. **Question detection via text blocks, not `page.search_for()`**: `search_for(" 2.")` matches inside words like "289". Instead, scan text blocks for lines matching `^\s*N\.\s` pattern.

2. **Last question boundary**: Don't extend to page footer. Find actual content bottom by scanning blocks, skipping noise. Avoids capturing whitespace.

3. **Ghost server processes**: Always check `netstat -ano | grep ":8000"` and kill ALL old processes before restarting. Old servers on 127.0.0.1 shadow new servers on 0.0.0.0.

4. **Render scale and display sizing**: The render scale must account for the clip rect width to produce crisp images. Narrow columns need higher scale to match the pixel density of wider clips.
   - **English passages** (left column only, ~268pts wide): scale=5.0 → ~1340px wide. Display at 75% of pane width (centered) to avoid oversized text.
   - **Math questions** (left column only, ~282pts wide): scale=5.0 → ~1410px wide. Display at 75% of pane width (centered).
   - **Science/Reading passages** (full width, ~540pts wide): scale=2.5 → ~1350px wide. Display at 100% of pane width.
   - **Rule of thumb**: target ~1350px rendered width for consistent crispness. Calculate scale as `1350 / clip_width_pts`.

5. **Image stitching**: When multiple clip rects are used, they're rendered separately and stitched vertically with a small gap. Ensure rect widths are consistent for clean stitching.

6. **English questions are in the RIGHT column**: Unlike Math/Science/Reading where questions are in the left column, English questions appear in the right column (x > pw*0.5). The y_pos detection in `_parse_page_questions` must NOT filter by `bx0 < left_half` for English. Pass `section_name` to the function and skip the left-half constraint when `section_name == "English"`.

7. **English "NO CHANGE" questions have no question text**: Many English questions (grammar/usage) have empty `question_text` — the question refers to an underlined portion in the passage. The format is `1. A.\nNO CHANGE\nB.\noption text...`. This parses correctly; `question_text=""` is expected and normal. Do NOT substitute placeholder text like "(no text extracted)".

8. **Two-column split must not cut through text blocks**: When splitting a passage into full-width rect (above questions) + left-column-only rect (below), the split boundary (`first_question_y - 10`) can bisect a left-column text block, splitting words like "them-" / "selves" across two differently-sized image strips. **Fix**: Before setting the split point, scan left-column blocks to find any that straddle the boundary. If a block's y0 < split and y1 > split, move the split point above that block (`by0 - 4`) so the entire block goes into the left-column-only rect.

9. **Re-importing a PDF doesn't auto-update the database**: After fixing extraction code, the database still holds stale data from the previous import. Either re-upload the PDF or directly update affected question rows in the database.

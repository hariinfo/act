"""
Generate step-by-step explanations for ACT questions using a local Ollama LLM.
Generates one explanation at a time for reliability.
"""
import logging
import re
import time
import requests

logger = logging.getLogger("uvicorn.error")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1:8b"


def generate_explanations(section_name: str, questions: list[dict], on_progress=None) -> list[str]:
    """
    Generate explanations for questions using local Ollama, one at a time.
    Returns a list of explanation strings, one per question (same order).
    on_progress(i, total, q_num, status, elapsed) is called after each question.
    """
    if not questions:
        return []

    logger.info(f"[Explanation] Starting explanation generation for {len(questions)} {section_name} questions")
    logger.info(f"[Explanation] Using model: {OLLAMA_MODEL} at {OLLAMA_URL}")

    # Check Ollama connectivity
    try:
        health = requests.get("http://localhost:11434/api/tags", timeout=10)
        models = [m["name"] for m in health.json().get("models", [])]
        logger.info(f"[Explanation] Ollama is running. Available models: {models}")
        if not any(OLLAMA_MODEL in m for m in models):
            logger.info(f"[Explanation] WARNING: Model '{OLLAMA_MODEL}' not found in available models!")
    except Exception as e:
        logger.info(f"[Explanation] WARNING: Cannot reach Ollama: {e}")

    explanations = []
    success_count = 0
    fail_count = 0
    total_start = time.time()

    for i, q in enumerate(questions):
        q_num = q.get("question_number", i + 1)
        q_text_preview = q.get("question_text", "")[:80].replace("\n", " ")
        logger.info(f"[Explanation] [{i+1}/{len(questions)}] Q{q_num}: {q_text_preview}...")

        start = time.time()
        exp = _explain_single(section_name, q)
        elapsed = time.time() - start

        if exp:
            success_count += 1
            logger.info(f"[Explanation] [{i+1}/{len(questions)}] OK ({elapsed:.1f}s, {len(exp)} chars): {exp[:100]}...")
            if on_progress:
                on_progress(i, len(questions), q_num, "ok", elapsed)
        else:
            fail_count += 1
            logger.info(f"[Explanation] [{i+1}/{len(questions)}] FAILED ({elapsed:.1f}s)")
            if on_progress:
                on_progress(i, len(questions), q_num, "failed", elapsed)

        explanations.append(exp)

    total_elapsed = time.time() - total_start
    logger.info(f"[Explanation] Done. {success_count} succeeded, {fail_count} failed, total time: {total_elapsed:.1f}s")
    return explanations


def _explain_single(section_name: str, q: dict) -> str:
    """Generate explanation for a single question via Ollama."""
    LABEL_MAP_ABCDE = ['A', 'B', 'C', 'D', 'E']
    LABEL_MAP_FGHJK = ['F', 'G', 'H', 'J', 'K']

    text = q.get("question_text", "")[:400]
    labels = LABEL_MAP_FGHJK if q.get("option_labels") == "FGHJK" else LABEL_MAP_ABCDE
    opts = []
    for j, key in enumerate(["option_a", "option_b", "option_c", "option_d", "option_e"]):
        val = q.get(key)
        if val:
            opts.append(f"{labels[j]}. {val[:100]}")
    opts_str = "\n".join(opts)
    correct = q.get("correct_answer", "?")
    passage_hint = ""
    if q.get("passage_text"):
        passage_hint = f"\nPassage context: {q['passage_text'][:300]}..."

    prompt = f"""You are an ACT test prep tutor. Explain this ACT {section_name} question.

Question: {text}
{opts_str}
Correct answer: {correct}{passage_hint}

In 2-4 sentences explain:
1. Why {correct} is correct
2. How to arrive at the answer
3. Why other options are wrong (briefly)

Write ONLY the explanation text, no JSON, no markdown, no extra formatting."""

    try:
        logger.info(f"[Explanation]   Sending request to Ollama ({OLLAMA_MODEL})...")
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            },
        }, timeout=300)

        logger.info(f"[Explanation]   Response status: {resp.status_code}")
        resp.raise_for_status()

        resp_json = resp.json()
        result_text = resp_json.get("response", "").strip()
        raw_len = len(result_text)
        eval_duration = resp_json.get("eval_duration", 0) / 1e9  # nanoseconds to seconds
        tokens = resp_json.get("eval_count", 0)

        logger.info(f"[Explanation]   Raw response: {raw_len} chars, {tokens} tokens, {eval_duration:.1f}s eval time")

        if raw_len > 0:
            logger.info(f"[Explanation]   Raw preview: {result_text[:150]}...")

        # DeepSeek-R1 outputs <think>...</think> blocks — strip them
        has_think = "<think>" in result_text
        if has_think:
            think_match = re.search(r'<think>(.*?)</think>', result_text, flags=re.DOTALL)
            think_len = len(think_match.group(1)) if think_match else 0
            logger.info(f"[Explanation]   Stripping <think> block ({think_len} chars)")
        result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()

        # Also strip any unclosed <think> block (model ran out of tokens mid-think)
        if '<think>' in result_text:
            logger.info(f"[Explanation]   Stripping unclosed <think> block")
            result_text = re.sub(r'<think>.*', '', result_text, flags=re.DOTALL).strip()

        logger.info(f"[Explanation]   Final cleaned: {len(result_text)} chars")

        if result_text and len(result_text) > 10:
            return result_text

        logger.info(f"[Explanation]   SKIP: explanation too short or empty after cleaning")
        return None

    except requests.exceptions.Timeout:
        logger.info(f"[Explanation]   ERROR: Request timed out after 300s")
        return None
    except requests.exceptions.ConnectionError as e:
        logger.info(f"[Explanation]   ERROR: Cannot connect to Ollama: {e}")
        return None
    except Exception as e:
        logger.info(f"[Explanation]   ERROR: {type(e).__name__}: {e}")
        return None

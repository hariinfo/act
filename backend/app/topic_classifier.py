"""
Auto-classify ACT questions into topics using a local Ollama LLM.
Sends batches of questions per section to minimize calls.
"""
import json
import logging
import re
import time
import requests
from .config import settings

logger = logging.getLogger("uvicorn.error")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "deepseek-r1:8b"

# Predefined topic lists per ACT section
SECTION_TOPICS = {
    "English": [
        "Grammar & Usage",
        "Punctuation",
        "Sentence Structure",
        "Rhetorical Strategy",
        "Organization",
        "Style & Tone",
        "Word Choice",
    ],
    "Math": [
        "Pre-Algebra",
        "Elementary Algebra",
        "Intermediate Algebra",
        "Coordinate Geometry",
        "Plane Geometry",
        "Trigonometry",
        "Statistics & Probability",
        "Functions",
        "Numbers & Operations",
    ],
    "Reading": [
        "Prose Fiction",
        "Social Science",
        "Humanities",
        "Natural Science",
        "Main Idea & Purpose",
        "Detail & Evidence",
        "Inference",
        "Vocabulary in Context",
        "Comparative Reading",
    ],
    "Science": [
        "Data Representation",
        "Research Summaries",
        "Conflicting Viewpoints",
        "Biology",
        "Chemistry",
        "Physics",
        "Earth Science",
    ],
}


def classify_questions(section_name: str, questions: list[dict], on_progress=None) -> list[str]:
    """
    Classify a batch of questions into topics using local Ollama.
    Returns a list of topic strings, one per question (same order).
    Batches in groups of 10 to stay within context limits.
    on_progress(batch_num, total_batches, batch_size, elapsed) is called after each batch.
    """
    if not questions:
        return []

    logger.info(f"[Topics] Starting topic classification for {len(questions)} {section_name} questions")
    logger.info(f"[Topics] Using model: {OLLAMA_MODEL} at {OLLAMA_URL}")

    BATCH_SIZE = 10
    all_topics = []
    total_start = time.time()
    total_batches = (len(questions) + BATCH_SIZE - 1) // BATCH_SIZE
    for start in range(0, len(questions), BATCH_SIZE):
        batch = questions[start:start + BATCH_SIZE]
        batch_num = start // BATCH_SIZE + 1
        logger.info(f"[Topics] Batch {batch_num}/{total_batches} ({len(batch)} questions)...")

        t0 = time.time()
        batch_topics = _classify_batch(section_name, batch)
        elapsed = time.time() - t0
        logger.info(f"[Topics] Batch {batch_num} done in {elapsed:.1f}s: {batch_topics}")
        all_topics.extend(batch_topics)

        if on_progress:
            on_progress(batch_num, total_batches, len(batch), elapsed)

    total_elapsed = time.time() - total_start
    assigned = sum(1 for t in all_topics if t)
    logger.info(f"[Topics] Done. {assigned}/{len(all_topics)} topics assigned, total time: {total_elapsed:.1f}s")
    return all_topics


def _classify_batch(section_name: str, questions: list[dict]) -> list[str]:
    """Classify a single batch of questions via Ollama."""
    topics_list = SECTION_TOPICS.get(section_name, ["General"])

    # Build compact question summaries
    q_summaries = []
    for i, q in enumerate(questions):
        text = q.get("question_text", "")[:150]
        opts = []
        for key in ["option_a", "option_b", "option_c", "option_d"]:
            val = q.get(key, "")
            if val:
                opts.append(val[:40])
        opts_str = " | ".join(opts)
        q_summaries.append(f"{i+1}. {text}\n   Opts: {opts_str}")

    questions_text = "\n".join(q_summaries)
    n = len(questions)

    prompt = f"""Classify these {n} ACT {section_name} questions into topics.

Topics: {json.dumps(topics_list)}

Questions:
{questions_text}

Return ONLY a JSON array of {n} strings, one topic per question. No explanation needed, just the JSON array.
Example: {json.dumps(topics_list[:min(3, n)])}
JSON array:"""

    try:
        logger.info(f"[Topics]   Sending request to Ollama ({OLLAMA_MODEL})...")
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 8192,
            },
        }, timeout=300)

        logger.info(f"[Topics]   Response status: {resp.status_code}")
        resp.raise_for_status()

        resp_json = resp.json()
        result_text = resp_json.get("response", "").strip()
        raw_len = len(result_text)
        tokens = resp_json.get("eval_count", 0)
        eval_time = resp_json.get("eval_duration", 0) / 1e9

        logger.info(f"[Topics]   Raw response: {raw_len} chars, {tokens} tokens, {eval_time:.1f}s eval")
        logger.info(f"[Topics]   Raw preview: {result_text[:200]}...")

        # DeepSeek-R1 outputs <think>...</think> blocks — strip them
        if '<think>' in result_text:
            think_match = re.search(r'<think>(.*?)</think>', result_text, flags=re.DOTALL)
            think_len = len(think_match.group(1)) if think_match else 0
            logger.info(f"[Topics]   Stripping <think> block ({think_len} chars)")
        result_text = re.sub(r'<think>.*?</think>', '', result_text, flags=re.DOTALL).strip()
        # Strip unclosed think block
        if '<think>' in result_text:
            logger.info(f"[Topics]   Stripping unclosed <think> block")
            result_text = re.sub(r'<think>.*', '', result_text, flags=re.DOTALL).strip()

        logger.info(f"[Topics]   After cleaning: {len(result_text)} chars: {result_text[:200]}")

        # Extract JSON array from response
        start_idx = result_text.find("[")
        end_idx = result_text.rfind("]")
        if start_idx != -1 and end_idx != -1:
            json_str = result_text[start_idx:end_idx + 1]
            logger.info(f"[Topics]   Found JSON array: {json_str[:200]}")
            topics = json.loads(json_str)

            if isinstance(topics, list) and len(topics) == n:
                valid = set(topics_list)
                return [t if t in valid else _best_match(t, topics_list) for t in topics]
            elif isinstance(topics, list) and len(topics) > 0:
                logger.info(f"[Topics]   WARNING: Got {len(topics)} topics, expected {n}. Padding/trimming.")
                topics = topics[:n]
                while len(topics) < n:
                    topics.append(topics_list[0])
                valid = set(topics_list)
                return [t if t in valid else _best_match(t, topics_list) for t in topics]
            else:
                logger.info(f"[Topics]   ERROR: Parsed result is not a list or is empty")
        else:
            logger.info(f"[Topics]   ERROR: No JSON array found in response")

        logger.info(f"[Topics]   FAILED to parse. Full cleaned response: {result_text[:500]}")
        return [None] * n

    except requests.exceptions.Timeout:
        logger.info(f"[Topics]   ERROR: Request timed out after 300s")
        return [None] * n
    except requests.exceptions.ConnectionError as e:
        logger.info(f"[Topics]   ERROR: Cannot connect to Ollama: {e}")
        return [None] * n
    except json.JSONDecodeError as e:
        logger.info(f"[Topics]   ERROR: JSON parse failed: {e}")
        logger.info(f"[Topics]   JSON string was: {json_str[:300]}")
        return [None] * n
    except Exception as e:
        logger.info(f"[Topics]   ERROR: {type(e).__name__}: {e}")
        return [None] * n


def _best_match(text: str, options: list[str]) -> str:
    """Find the closest matching topic from the options list."""
    if not text:
        return options[0]
    text_lower = text.lower()
    for opt in options:
        if opt.lower() in text_lower or text_lower in opt.lower():
            return opt
    # Keyword matching fallback
    for opt in options:
        words = opt.lower().split()
        if any(w in text_lower for w in words if len(w) > 3):
            return opt
    return options[0]

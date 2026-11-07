"""Evaluation metrics (owner: Student A, task A12). Pure functions, unit-tested.

Search (one question, a ranked list of frames, the set of right frames):
- Recall@k: 1 if a right frame is among the first k results, else 0 (averaged).
- Reciprocal rank: 1 / position of the first right frame (1, 0.5, 0.33...), 0 if
  none; its average is the MRR (mean reciprocal rank).
OCR (true text vs read text):
- Word recall: share of the true words that were read.
- CER (character error rate): edit distance / length of the true text; 0 = perfect.
"""

import re
import statistics
import unicodedata


def rank_of_first_relevant(ranked: list[str], relevant: set[str] | frozenset[str]) -> int | None:
    """1-based position of the first right answer, None if absent."""
    for position, item in enumerate(ranked, start=1):
        if item in relevant:
            return position
    return None


def recall_at(rank: int | None, k: int) -> float:
    return 1.0 if rank is not None and rank <= k else 0.0


def reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


def normalize(text: str) -> str:
    """Case, accents and punctuation removed; one space between words."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text))


def word_recall(truth: str, read: str) -> float:
    words = normalize(truth).split()
    if not words:
        return 1.0
    found = set(normalize(read).split())
    return sum(word in found for word in words) / len(words)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance: insertions + deletions + substitutions."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(truth: str, read: str) -> float:
    truth, read = normalize(truth), normalize(read)
    return edit_distance(truth, read) / max(1, len(truth))


def summary(values: list[float]) -> dict[str, float]:
    """mean, median and 95th percentile (rounded), for timings."""
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"mean": round(statistics.fmean(values), 1),
            "median": round(statistics.median(values), 1), "p95": round(p95, 1)}

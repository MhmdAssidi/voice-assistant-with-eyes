"""Student A evaluation (task A12): search quality, OCR, warnings and speed.

Every frame goes through the REAL pipeline (enhance, face blur, OCR, YOLO, CLIP,
warnings) into a throw-away database `va_eval`, then the questions are searched with
the real ranking. Your own `va` database and data/frames are never touched.

Run from backend/ (Docker must be running; first run downloads ~20 photos):
    python ../eval/run_eval.py                      # the built-in set (eval/evalset.py)
    python ../eval/run_eval.py --video ../eval/samples/walk.mp4 \
                               --queries ../eval/samples/walk_queries.csv
Writes eval/results/results.json and eval/results/RESULTS.md (or --out DIR).
"""

import argparse
import csv
import json
import os
import platform
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path[:0] = [str(EVAL_DIR.parent / "backend"), str(EVAL_DIR)]

import cv2  # noqa: E402
import metrics  # noqa: E402
import psycopg  # noqa: E402
from evalset import ITEMS, QUERIES, Query  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

from app import db  # noqa: E402
from app.config import BACKEND_DIR, settings  # noqa: E402
from app.ingest.grabber import GrabbedFrame  # noqa: E402
from app.memory import repository as repo  # noqa: E402
from app.memory import search  # noqa: E402
from app.vision.quality import Decision, FrameSelector  # noqa: E402

EVAL_DB = "va_eval"
RESULTS_DIR = EVAL_DIR / "results"
THRESHOLD = settings.confidence_threshold  # Student B: below this, "I'm not sure"
STAGES = ["quality", "enhance", "faces", "warnings", "ocr", "objects", "embed", "store"]

# Ablation: which signals matter? (image, caption text, OCR words) weights in the score
VARIANTS = {
    "full (0.5 image + 0.3 text + 0.2 OCR)": (0.5, 0.3, 0.2),
    "picture only (CLIP image)": (1.0, 0.0, 0.0),
    "caption only (CLIP text)": (0.0, 1.0, 0.0),
    "OCR words only": (0.0, 0.0, 1.0),
    "no OCR (0.6 image + 0.4 text)": (0.6, 0.4, 0.0),
}


class KeepAll:
    """For the photo set every frame must be stored (each one is a different scene)."""

    def decide(self, quality, captured_at) -> Decision:
        return Decision(True, "eval")


# ---------- setup ----------

def open_eval_database() -> None:
    with psycopg.connect(settings.database_url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {EVAL_DB} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {EVAL_DB}")
    url = make_conninfo(settings.database_url, dbname=EVAL_DB)
    schema = (BACKEND_DIR / "db" / "init" / "001_frames.sql").read_text(encoding="utf-8")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(schema)
    db.open_pool(url)


def load_pipeline(selector):
    from app.ingest.pipeline import Pipeline
    from app.memory.embeddings import Embedder
    from app.vision.hazards import HazardDetector

    started = time.perf_counter()
    embedder = Embedder()
    pipeline = Pipeline(selector=selector, embedder=embedder,
                        hazards=HazardDetector(embedder, cooldown_s=0))
    search._embedder = embedder  # search reuses the same CLIP text model
    return pipeline, round(time.perf_counter() - started, 1)


# ---------- the built-in set ----------

def ingest_items(pipeline) -> tuple[dict[str, int], list[dict]]:
    """Store every item; return item id -> frame id, and per-frame timings."""
    start = datetime.now(UTC) - timedelta(minutes=2)  # "seen a moment ago"
    frame_of, timings = {}, []
    for seq, item in enumerate(ITEMS, start=1):
        image = item.load()
        if image.shape[1] != 640:  # the phone streams 640 px wide
            image = cv2.resize(image, (640, round(image.shape[0] * 640 / image.shape[1])))
        pipeline.process(GrabbedFrame(seq, start + timedelta(seconds=seq), image))
        frame_of[item.id] = pipeline.last_frame_id
        timings.append(pipeline.last_timings)
        print(f"  stored {item.id:14s} -> frame {pipeline.last_frame_id}  "
              f"{sum(pipeline.last_timings.values())} ms", flush=True)
    return frame_of, timings


def evaluate_ocr(frame_of: dict[str, int]) -> dict:
    rows = []
    for item in ITEMS:
        if not item.text:
            continue
        read = repo.get_frame(frame_of[item.id]).ocr_text
        rows.append({"item": item.id, "truth": item.text, "read": " ".join(read.split()),
                     "word_recall": round(metrics.word_recall(item.text, read), 3),
                     "cer": round(metrics.cer(item.text, read), 3)})
    return {
        "signs": rows,
        "mean_word_recall": round(sum(r["word_recall"] for r in rows) / len(rows), 3),
        "mean_cer": round(sum(r["cer"] for r in rows) / len(rows), 3),
    }


def evaluate_warnings(pipeline, frame_of: dict[str, int]) -> dict:
    detector = pipeline.hazards
    per_item, counts = [], {k: defaultdict(int) for k in ("stairs", "closed_door")}
    for item in ITEMS:
        image_emb = repo.get_frame(frame_of[item.id], with_embeddings=True).image_emb
        probabilities = detector.probabilities(image_emb)
        predicted = {k for k in counts if probabilities[k] >= detector.thresholds[k]}
        for kind in counts:
            truth, said = item.hazard == kind, kind in predicted
            counts[kind][("tp" if truth else "fp") if said else ("fn" if truth else "tn")] += 1
        per_item.append({"item": item.id, "truth": item.hazard, "predicted": sorted(predicted),
                         "stairs": round(probabilities["stairs"], 3),
                         "closed_door": round(probabilities["closed_door"], 3)})
    by_kind = {}
    for kind, c in counts.items():
        precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        recall = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        by_kind[kind] = {**dict(c), "precision": precision, "recall": recall,
                         "threshold": detector.thresholds[kind]}
    return {"by_kind": by_kind, "frames": per_item}


# ---------- search (both modes) ----------

def run_queries(queries: list[Query], frame_of: dict[str, int], limit: int = 10) -> dict:
    """Rank frames for every question; per-question rows and averages."""
    item_of = {frame: item for item, frame in frame_of.items()}
    rows, latencies = [], []
    for query in queries:
        started = time.perf_counter()
        hits = search.rank_frames(query.text, limit=limit)
        latencies.append((time.perf_counter() - started) * 1000)
        ranked = [item_of.get(h.frame.id, f"frame{h.frame.id}") for h in hits]
        rank = metrics.rank_of_first_relevant(ranked, query.relevant)
        top_score = hits[0].score if hits else 0.0
        rows.append({
            "query": query.text, "language": query.language,
            "answerable": bool(query.relevant), "rank": rank,
            "top": ranked[0] if ranked else None, "top_score": top_score,
            "top_matched_by": hits[0].matched_by if hits else [],
        })
    return {"rows": rows, "latency_ms": metrics.summary(latencies)}


def search_scores(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    n = max(1, len(answerable))
    return {
        "questions": len(rows), "answerable": len(answerable),
        "recall@1": round(sum(metrics.recall_at(r["rank"], 1) for r in answerable) / n, 3),
        "recall@3": round(sum(metrics.recall_at(r["rank"], 3) for r in answerable) / n, 3),
        "mrr": round(sum(metrics.reciprocal_rank(r["rank"]) for r in answerable) / n, 3),
        # The assistant answers with confidence when the best score >= THRESHOLD
        "right_and_confident": round(sum(
            r["rank"] == 1 and r["top_score"] >= THRESHOLD for r in answerable) / n, 3),
        "unanswerable_wrongly_confident": (
            round(sum(r["top_score"] >= THRESHOLD for r in unanswerable) / len(unanswerable), 3)
            if unanswerable else None),
    }


def evaluate_search(queries: list[Query], frame_of: dict[str, int]) -> dict:
    result = run_queries(queries, frame_of)
    by_language = {
        lang: search_scores([r for r in result["rows"] if r["language"] == lang])
        for lang in sorted({q.language for q in queries})
    }
    ablation = {}
    saved = (search.W_IMAGE, search.W_TEXT, search.W_OCR)
    try:
        for name, weights in VARIANTS.items():
            search.W_IMAGE, search.W_TEXT, search.W_OCR = weights
            ablation[name] = search_scores(run_queries(queries, frame_of)["rows"])
    finally:
        search.W_IMAGE, search.W_TEXT, search.W_OCR = saved
    return {"overall": search_scores(result["rows"]), "by_language": by_language,
            "ablation": ablation, "latency_ms": result["latency_ms"], "questions": result["rows"]}


def evaluate_speed(timings: list[dict]) -> dict:
    per_stage = {s: metrics.summary([t.get(s, 0) for t in timings]) for s in STAGES}
    total = metrics.summary([sum(t.values()) for t in timings])
    return {"frames": len(timings), "per_stage_ms": per_stage, "total_ms": total}


# ---------- a recorded walk (--video) ----------

def read_walk_queries(path: Path) -> list[tuple[Query, float | None, float | None]]:
    """CSV: query,language,from_s,to_s  (empty from_s/to_s = nothing relevant was seen)."""
    rows = []
    with path.open(encoding="utf-8") as file:
        for row in csv.DictReader(file):
            start = float(row["from_s"]) if row["from_s"].strip() else None
            end = float(row["to_s"]) if row["to_s"].strip() else None
            rows.append((Query(row["query"], row["language"], frozenset()), start, end))
    return rows


def ingest_video(pipeline, video: Path, fps: float) -> tuple[dict[int, float], list[dict], int]:
    """Feed the video at `fps` (like the worker); return frame id -> video second."""
    cap = cv2.VideoCapture(str(video))
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 15
    step = max(1, round(source_fps / fps))
    start = datetime.now(UTC) - timedelta(hours=1)
    second_of, timings, seen, index = {}, [], 0, 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        if index % step == 0:
            seen += 1
            second = index / source_fps
            if pipeline.process(GrabbedFrame(seen, start + timedelta(seconds=second), image)):
                second_of[pipeline.last_frame_id] = second
                timings.append(pipeline.last_timings)
        index += 1
    cap.release()
    return second_of, timings, seen


def evaluate_video(pipeline, video: Path, queries_csv: Path) -> dict:
    second_of, timings, seen = ingest_video(pipeline, video, settings.ingest_fps)
    print(f"  {seen} frames sampled, {len(second_of)} kept", flush=True)
    frame_of = {f"frame{frame_id}": frame_id for frame_id in second_of}
    queries = []
    for query, start, end in read_walk_queries(queries_csv):
        relevant = frozenset(
            f"frame{fid}" for fid, s in second_of.items()
            if start is not None and end is not None and start <= s <= end
        )
        queries.append(Query(query.text, query.language, relevant))
    result = evaluate_search(queries, frame_of)
    result.pop("ablation")  # the built-in set already shows it
    return {"video": video.name, "frames_sampled": seen, "frames_kept": len(second_of),
            "search": result, "speed": evaluate_speed(timings)}


# ---------- report ----------

def fmt(value) -> str:
    if value is None:
        return "–"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def markdown(results: dict) -> str:
    out = [
        "# Student A evaluation results (A12)",
        "",
        f"Generated {results['generated']} on {results['machine']} by `eval/run_eval.py`. "
        f"Models loaded in {results['model_load_s']} s.",
        "",
    ]
    if "builtin" in results:
        b = results["builtin"]
        s = b["search"]
        out += [
            f"## Search quality ({s['overall']['questions']} questions, "
            f"{len(b['frames'])} frames, en/fr/ar)",
            "",
            "| | Recall@1 | Recall@3 | MRR | right & confident (≥ 0.25) | "
            "unanswerable but confident |",
            "|---|---|---|---|---|---|",
        ]
        rows = [("**all**", s["overall"])] + list(s["by_language"].items())
        for name, m in rows:
            out.append(f"| {name} | {fmt(m['recall@1'])} | {fmt(m['recall@3'])} | "
                       f"{fmt(m['mrr'])} | {fmt(m['right_and_confident'])} | "
                       f"{fmt(m['unanswerable_wrongly_confident'])} |")
        out += ["", "### Which signals matter (ablation)", "",
                "| Score uses | Recall@1 | MRR | unanswerable but confident |", "|---|---|---|---|"]
        for name, m in s["ablation"].items():
            out.append(f"| {name} | {fmt(m['recall@1'])} | {fmt(m['mrr'])} | "
                       f"{fmt(m['unanswerable_wrongly_confident'])} |")
        misses = [q for q in s["questions"] if q["answerable"] and q["rank"] != 1]
        out += ["", f"Search latency: {s['latency_ms']['mean']} ms mean, "
                f"{s['latency_ms']['p95']} ms p95.", ""]
        if misses:
            out += ["Questions whose first result was not a right frame:", ""]
            out += [f"- *{q['query']}* ({q['language']}): right frame at rank {fmt(q['rank'])}, "
                    f"first was `{q['top']}` ({q['top_score']:.2f})" for q in misses]
            out.append("")
        o = b["ocr"]
        out += [f"## OCR on signs (word recall {o['mean_word_recall']:.2f}, "
                f"CER {o['mean_cer']:.2f})", "",
                "| Sign | True text | Read | Word recall | CER |", "|---|---|---|---|---|"]
        out += [f"| {r['item']} | {r['truth']} | {r['read'] or '(nothing)'} | "
                f"{r['word_recall']:.2f} | {r['cer']:.2f} |" for r in o["signs"]]
        w = b["warnings"]["by_kind"]
        out += ["", "## Warnings (CLIP zero-shot)", "",
                "| Kind | Threshold | TP | FP | FN | TN | Precision | Recall |",
                "|---|---|---|---|---|---|---|---|"]
        for kind, m in w.items():
            out.append(f"| {kind} | {m['threshold']} | {m.get('tp', 0)} | {m.get('fp', 0)} | "
                       f"{m.get('fn', 0)} | {m.get('tn', 0)} | {fmt(m['precision'])} | "
                       f"{fmt(m['recall'])} |")
        out += ["", *speed_table(b["speed"]), ""]
    if "video" in results:
        v = results["video"]
        m = v["search"]["overall"]
        out += [f"## Recorded walk: {v['video']}", "",
                f"{v['frames_sampled']} frames sampled, {v['frames_kept']} kept "
                f"({v['frames_kept'] / max(1, v['frames_sampled']):.0%}).", "",
                f"Search: Recall@1 {fmt(m['recall@1'])}, Recall@3 {fmt(m['recall@3'])}, "
                f"MRR {fmt(m['mrr'])}, right & confident {fmt(m['right_and_confident'])}, "
                f"unanswerable but confident {fmt(m['unanswerable_wrongly_confident'])}.", "",
                *speed_table(v["speed"]), ""]
    return "\n".join(out)


def speed_table(speed: dict) -> list[str]:
    lines = [f"## Speed per stored frame ({speed['frames']} frames, laptop CPU)", "",
             "| Stage | mean ms | p95 ms |", "|---|---|---|"]
    lines += [f"| {stage} | {m['mean']} | {m['p95']} |"
              for stage, m in speed["per_stage_ms"].items()]
    total = speed["total_ms"]
    lines.append(f"| **total** | **{total['mean']}** | **{total['p95']}** |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="Student A evaluation (A12)")
    parser.add_argument("--video", type=Path, help="a recorded walk, e.g. eval/samples/walk.mp4")
    parser.add_argument("--queries", type=Path, help="questions with time ranges (CSV)")
    parser.add_argument("--skip-builtin", action="store_true", help="only the --video part")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="folder for the results")
    args = parser.parse_args()
    if args.video and not args.queries:
        parser.error("--video needs --queries")

    settings.frames_dir = tempfile.mkdtemp(prefix="va_eval_")  # never touches data/frames
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    open_eval_database()
    results = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
               "machine": f"{platform.system()} {platform.machine()}, Python "
                          f"{platform.python_version()}"}

    if not args.skip_builtin:
        print("Loading models...", flush=True)
        pipeline, load_s = load_pipeline(KeepAll())
        results["model_load_s"] = load_s
        print(f"Storing {len(ITEMS)} frames through the real pipeline...", flush=True)
        frame_of, timings = ingest_items(pipeline)
        print(f"Searching {len(QUERIES)} questions...", flush=True)
        results["builtin"] = {
            "frames": {item.id: item.source for item in ITEMS},
            "search": evaluate_search(QUERIES, frame_of),
            "ocr": evaluate_ocr(frame_of),
            "warnings": evaluate_warnings(pipeline, frame_of),
            "speed": evaluate_speed(timings),
        }
    if args.video:
        open_eval_database()  # a fresh memory for the walk
        pipeline, load_s = load_pipeline(FrameSelector())
        results.setdefault("model_load_s", load_s)
        print(f"Processing {args.video}...", flush=True)
        results["video"] = evaluate_video(pipeline, args.video, args.queries)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report = markdown(results)
    (args.out / "RESULTS.md").write_text(report + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n" + report)
    db.close_pool()


if __name__ == "__main__":
    main()

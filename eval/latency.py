"""Student B evaluation (task B13): how long does one spoken question take?

Every answered question is saved in the qa_log table with its timings (task B11).
This script reads them and reports, for each stage, the MEAN (the usual wait) and
the P95 (95 % of the questions were faster than this: the "bad but normal" wait).

Stages (milliseconds measured by the backend, /api/ask):
    stt     speech-to-text (Whisper) of the recorded question
    search  Student A's memory search (frames of the last minutes)
    vlm     the vision-language model (Gemini) looking at the photos
    total   from "audio received" to "answer ready" (also saving, live snapshot wait)

Only FULL answers (the model was called, vlm > 0) go into the stage table: a question
that was not heard, or asked with a covered camera, stops early and would make the
averages look better than they are. They are counted separately.

Run from backend/ (Docker must be running):
    python ../eval/latency.py                        # every question in qa_log
    python ../eval/latency.py --since 2026-11-20     # only one evaluation session
Writes to eval/results/: latency.csv (one row per question), latency_summary.csv,
latency.png and latency.md.
"""

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR.parent / "backend"))

import numpy as np  # noqa: E402
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.config import settings  # noqa: E402

STAGES = ["stt", "search", "vlm", "total"]
STAGE_NAMES = {
    "stt": "Speech-to-text (Whisper)",
    "search": "Memory search (Student A)",
    "vlm": "Vision-language model (Gemini)",
    "total": "Total (question -> answer)",
}
LANGUAGES = ["en", "fr", "ar"]

# Chart colours (validated categorical palette, light surface)
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e1e0d9"
MEAN_COLOR, P95_COLOR = "#2a78d6", "#eb6834"


def load_questions(since: date | None) -> list[dict]:
    query = "SELECT id, asked_at, language, confident, timings_ms FROM qa_log"
    params: list = []
    if since:
        query += " WHERE asked_at >= %s"
        params.append(since)
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        rows = conn.execute(query + " ORDER BY asked_at", params).fetchall()
    return [
        {
            "id": row["id"],
            "asked_at": row["asked_at"],
            "language": row["language"],
            "confident": row["confident"],
            **{stage: int((row["timings_ms"] or {}).get(stage, 0)) for stage in STAGES},
        }
        for row in rows
    ]


def is_full(question: dict) -> bool:
    """The model was called: a complete answer, not an early stop."""
    return question["vlm"] > 0


def stats(values_ms: list[int]) -> dict:
    """n, mean, median, p95 and max, in seconds (p95 = linear percentile)."""
    if not values_ms:
        return {"n": 0, "mean_s": None, "median_s": None, "p95_s": None, "max_s": None}
    seconds = np.array(values_ms) / 1000
    return {
        "n": len(seconds),
        "mean_s": round(float(seconds.mean()), 2),
        "median_s": round(float(np.median(seconds)), 2),
        "p95_s": round(float(np.percentile(seconds, 95)), 2),
        "max_s": round(float(seconds.max()), 2),
    }


def summarize(questions: list[dict]) -> list[dict]:
    full = [q for q in questions if is_full(q)]
    rows = [{"group": "all", "stage": s, **stats([q[s] for q in full])} for s in STAGES]
    for language in LANGUAGES:
        in_language = [q["total"] for q in full if q["language"] == language]
        rows.append({"group": language, "stage": "total", **stats(in_language)})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def draw_chart(summary: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")  # no window, just the PNG
    import matplotlib.pyplot as plt

    rows = [r for r in summary if r["group"] == "all" and r["n"]]
    labels = [STAGE_NAMES[r["stage"]] for r in rows]
    y = np.arange(len(rows))
    height = 0.36

    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for offset, key, color, name in [
        (-height / 2 - 0.01, "mean_s", MEAN_COLOR, "Mean"),
        (height / 2 + 0.01, "p95_s", P95_COLOR, "P95 (95 % of questions faster)"),
    ]:
        values = [r[key] for r in rows]
        bars = ax.barh(y + offset, values, height=height, color=color, label=name)
        for bar, value in zip(bars, values, strict=True):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {value:.1f} s",
                    va="center", fontsize=8, color=INK)
    ax.set_yticks(y, labels, fontsize=9, color=INK)
    ax.invert_yaxis()
    ax.set_xlabel("seconds", color=INK_2, fontsize=9)
    ax.tick_params(axis="x", colors=INK_2, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_xlim(0, max(r["p95_s"] for r in rows) * 1.18)
    n = rows[0]["n"]
    ax.set_title(f"Time per spoken question, by stage ({n} full answers)",
                 loc="left", fontsize=11, color=INK, pad=24)
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0),
              labelcolor=INK, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_markdown(path: Path, questions: list[dict], summary: list[dict], since) -> None:
    full = [q for q in questions if is_full(q)]
    early = len(questions) - len(full)
    lines = [
        "# Latency of a spoken question (Student B, task B13)",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `eval/latency.py` from the qa_log table"
        + (f" (questions since {since})." if since else " (all questions)."),
        "",
        f"- Questions: **{len(questions)}**, of which **{len(full)} full answers** "
        f"(the model was called) and {early} early stops (not heard, camera covered…).",
        "",
        "| Stage | n | Mean | Median | P95 | Max |",
        "|---|---|---|---|---|---|",
    ]
    for row in summary:
        if row["group"] != "all":
            continue
        lines.append(_md_row(STAGE_NAMES[row["stage"]], row))
    lines += ["", "Total time per language:", "", "| Language | n | Mean | Median | P95 | Max |",
              "|---|---|---|---|---|---|"]
    for row in summary:
        if row["group"] in LANGUAGES:
            lines.append(_md_row(row["group"], row))
    lines += ["", "![Latency by stage](latency.png)", "",
              "P95 = 95 % of the questions were faster than this. "
              "With fewer than 20 answers, P95 is close to the slowest one."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_row(name: str, row: dict) -> str:
    if not row["n"]:
        return f"| {name} | 0 | – | – | – | – |"
    return (f"| {name} | {row['n']} | {row['mean_s']:.1f} s | {row['median_s']:.1f} s | "
            f"**{row['p95_s']:.1f} s** | {row['max_s']:.1f} s |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--since", type=date.fromisoformat, help="only questions from this day")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results")
    args = parser.parse_args()

    questions = load_questions(args.since)
    if not questions:
        sys.exit("No questions in qa_log for this period: ask some with the phone first.")
    args.out.mkdir(parents=True, exist_ok=True)

    write_csv(args.out / "latency.csv", [
        {**q, "asked_at": q["asked_at"].isoformat(timespec="seconds"), "full": is_full(q)}
        for q in questions
    ])
    summary = summarize(questions)
    write_csv(args.out / "latency_summary.csv", summary)
    if any(r["n"] for r in summary):
        draw_chart(summary, args.out / "latency.png")
    write_markdown(args.out / "latency.md", questions, summary, args.since)

    for row in summary:
        if row["group"] == "all" and row["n"]:
            print(f"{STAGE_NAMES[row['stage']]:<32} mean {row['mean_s']:6.1f} s   "
                  f"p95 {row['p95_s']:6.1f} s   (n={row['n']})")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()

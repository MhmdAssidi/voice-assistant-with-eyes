"""A12 tests: the evaluation metrics (eval/metrics.py) and the walk labels format."""

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[3] / "eval"
sys.path.insert(0, str(EVAL_DIR))

import metrics  # noqa: E402


def test_rank_recall_and_reciprocal_rank() -> None:
    ranked = ["room", "exit_en", "exit_ar"]
    rank = metrics.rank_of_first_relevant(ranked, {"exit_en", "exit_ar"})
    assert rank == 2
    assert (metrics.recall_at(rank, 1), metrics.recall_at(rank, 3)) == (0.0, 1.0)
    assert metrics.reciprocal_rank(rank) == 0.5
    missing = metrics.rank_of_first_relevant(ranked, {"kitchen"})
    assert missing is None
    assert metrics.recall_at(missing, 3) == 0.0 and metrics.reciprocal_rank(missing) == 0.0


def test_word_recall_and_cer_ignore_case_accents_and_punctuation() -> None:
    assert metrics.word_recall("Sortie Escalier", "SORTIE escalier.") == 1.0
    assert metrics.word_recall("Sécurité", "SECURITE") == 1.0
    assert metrics.word_recall("PHARMACIE صيدلية", "PHARMACIE 4112") == 0.5
    assert metrics.cer("EXIT Room 204", "EXIT Room 204") == 0.0
    assert metrics.cer("STOP", "") == 1.0
    assert metrics.cer("مصعد", "مصعل") == pytest.approx(0.25)  # one letter of four wrong


def test_edit_distance() -> None:
    assert metrics.edit_distance("kitten", "sitting") == 3
    assert metrics.edit_distance("", "abc") == 3


def test_summary_of_timings() -> None:
    result = metrics.summary([10.0, 20.0, 30.0, 40.0, 1000.0])
    assert result["median"] == 30.0 and result["p95"] == 1000.0
    assert metrics.summary([]) == {"mean": 0.0, "median": 0.0, "p95": 0.0}


def test_example_walk_labels_are_well_formed() -> None:
    import csv

    with (EVAL_DIR / "samples" / "walk_queries.example.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows and set(rows[0]) == {"query", "language", "from_s", "to_s"}
    for row in rows:
        assert row["language"] in {"en", "fr", "ar"}
        if row["from_s"]:
            assert float(row["from_s"]) <= float(row["to_s"])

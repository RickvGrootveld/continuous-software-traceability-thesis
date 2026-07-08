"""
Unified Analysis — LLM-Enriched Knowledge Graph for Continuous Software Traceability
Models  : GPT-5.1 (frontier) vs Qwen3.5 4B (resource-constrained)
Answers : SQ2, SQ3, SQ4, SQ5 → Main RQ

Results implemented (23 total, matching the results table):
  R01  Perceived quality             — diverging stacked Likert        (SQ2, SQ4)
  R02  Quality per generated edge    — grouped bar chart               (SQ2)
  R03  Overall quality profile       — radar chart                     (SQ2, SQ4)
  R04  Objective vs perceived        — grouped bar chart               (SQ2, SQ4)
  R05  Confidence vs perceived       — scatter                         (SQ2, SQ4)
  R06  Confidence vs objective       — scatter                         (SQ2, SQ4)
  R07  Graph preference ranking      — stacked bar chart               (SQ5, SQ4)
  R08  Open responses                — theme table (console only)      (SQ5)
  R09  DIR helpfulness               — diverging stacked Likert        (SQ5)
  R10  DIR completeness              — diverging stacked Likert        (SQ5)
  R11  Runtime breakdown             — stacked bar chart               (SQ3, SQ4)
  R12  Generation time vs graph size — line chart                      (SQ3, SQ4)
  R13  Retrieval time vs graph size  — multi-line chart                (SQ3)
  R14  Context vs retrieval time     — scatter                         (SQ3)
  R15  Context vs generation time    — scatter                         (SQ3)
  R16  Context vs output tokens      — scatter                         (SQ3)
  R17  Output tokens vs valid edges  — scatter                         (SQ2, SQ3)
  R18  Graph growth through enrichmt — line chart                      (SQ3)
  R19  Correct edges vs graph size   — line chart                      (SQ2, SQ3)
  R20  CPU usage vs graph size       — line chart                      (SQ3, SQ4)
  R21  Memory usage vs graph size    — line chart                      (SQ3, SQ4)
  R22  GPT vs Qwen summary           — comparison table (console)      (SQ4)
  R23  Overall comparison radar      — radar chart                     (SQ4)

Output: ./figures/<result_id>_<name>.png  +  console report
"""

import re
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from math import pi
from pathlib import Path
from scipy import stats as sp_stats
from itertools import combinations

warnings.filterwarnings("ignore", category=FutureWarning)

# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

# ── File paths ────────────────────────────────────────────────────────────────
# Simulation — enrichment_results columns:
#   timestamp, llm_generation_time, llm_generated_edges, llm_correct_generated_edges,
#   neo4j_retrieval_time_window, graph_nodes_window, graph_edges_window, db_hits_window,
#   neo4j_retrieval_time_neighbourhood, graph_nodes_neighbourhood, graph_edges_neighbourhood,
#   db_hits_neighbourhood, neo4j_retrieval_time_vector, graph_nodes_vector, graph_edges_vector,
#   db_hits_vector, llm_insertion_time, llm_graph_nodes, llm_graph_edges
# Non-enriched rows will have NaN/0 for all llm_* columns — handled gracefully.
# Simulation has NO log file (logs only exist for scalability runs).
PATHS = {
    "GPT-5.1": {
        "enrichment": "results/correctness_simulation/log_run_results_gpt.csv",
        "kg":         "results/correctness_simulation/log_db_results_gpt.csv",
        "hardware":   "results/correctness_simulation/run_metrics_gpt.csv",
    },
    "Qwen3.5-4B": {
        "enrichment": "results/correctness_simulation/log_run_results_qwen.csv",
        "kg":         "results/correctness_simulation/log_db_results_qwen.csv",
        "hardware":   "results/correctness_simulation/run_metrics_qwen.csv",
    },
    "Non-enriched": {
        # No enrichment file — non-enriched run has no LLM calls
        "kg":       "results/correctness_simulation/log_db_results_non.csv",
        "hardware": "results/correctness_simulation/run_metrics_non.csv",
    },
}

# Scalability — only LLM models (no non-enriched scalability runs)
# Per-milestone files; set any path to None to skip that milestone.
SCALE_MILESTONES = [
    {"label": "0-184",  "node_count":     0},
    {"label": "1 000",  "node_count":  1000},
    {"label": "5 000",  "node_count":  5000},
    {"label": "10 000", "node_count": 10000},
]
SCALE_PATHS = {
    "GPT-5.1": {
        "enrichment": [
            "results/scalability issue commit validation/run_10_100_gpt/log_run_results.csv",
            "results/scalability issue commit validation/run_1000_gpt/log_run_results.csv",
            "results/scalability issue commit validation/run_5000_gpt/log_run_results.csv",
            "results/scalability issue commit validation/run_10000_gpt/log_run_results.csv",
        ],
        "kg": [
            "results/scalability issue commit validation/run_10_100_gpt/log_db_results.csv",
            "results/scalability issue commit validation/run_1000_gpt/log_db_results.csv",
            "results/scalability issue commit validation/run_5000_gpt/log_db_results.csv",
            "results/scalability issue commit validation/run_10000_gpt/log_db_results.csv",
        ],
        "hardware": [
            "results/scalability issue commit validation/run_10_100_gpt/run_metrics.csv",
            "results/scalability issue commit validation/run_1000_gpt/run_metrics.csv",
            "results/scalability issue commit validation/run_5000_gpt/run_metrics.csv",
            "results/scalability issue commit validation/run_10000_gpt/run_metrics.csv",
        ],
        "logs": [
            "results/scalability issue commit validation/run_10_100_gpt/enrichment_log.csv",
            "results/scalability issue commit validation/run_1000_gpt/enrichment_log.csv",
            "results/scalability issue commit validation/run_5000_gpt/enrichment_log.csv",
            "results/scalability issue commit validation/run_10000_gpt/enrichment_log.csv",
        ],
    },
    "Qwen3.5-4B": {
        "enrichment": [
            "results/scalability issue commit validation/run_10_100_qwen/log_run_results.csv",
            "results/scalability issue commit validation/run_1000_qwen/log_run_results.csv",
            "results/scalability issue commit validation/run_5000_qwen/log_run_results.csv",
            "results/scalability issue commit validation/run_10000_qwen/log_run_results.csv",
        ],
        "kg": [
            "results/scalability issue commit validation/run_10_100_qwen/log_db_results.csv",
            "results/scalability issue commit validation/run_1000_qwen/log_db_results.csv",
            "results/scalability issue commit validation/run_5000_qwen/log_db_results.csv",
            "results/scalability issue commit validation/run_10000_qwen/log_db_results.csv",
        ],
        "hardware": [
            "results/scalability issue commit validation/run_10_100_qwen/run_metrics.csv",
            "results/scalability issue commit validation/run_1000_qwen/run_metrics.csv",
            "results/scalability issue commit validation/run_5000_qwen/run_metrics.csv",
            "results/scalability issue commit validation/run_10000_qwen/run_metrics.csv",
        ],
        "logs": [
            "results/scalability issue commit validation/run_10_100_qwen/enrichment_log.csv",
            "results/scalability issue commit validation/run_1000_qwen/enrichment_log.csv",
            "results/scalability issue commit validation/run_5000_qwen/enrichment_log.csv",
            "results/scalability issue commit validation/run_10000_qwen/enrichment_log.csv",
        ],
    },
}

SURVEY_PATH       = "results/survey_results.csv"
SURVEY_LABEL_PATH = "results/survey_label_results.csv"

FIGURES_DIR = Path("figures_v2")
FIGURES_DIR.mkdir(exist_ok=True)

# ── Domain constants ──────────────────────────────────────────────────────────
# MODELS     : all three simulation variants (used for sim-data loading & plots)
# LLM_MODELS : only the two LLM variants (scalability, log-based, runtime breakdown)
MODELS     = ["GPT-5.1", "Qwen3.5-4B", "Non-enriched"]
LLM_MODELS = ["GPT-5.1", "Qwen3.5-4B"]
ENR_MODELS = ["GPT-5.1", "Qwen3.5-4B"]  # same as LLM_MODELS; alias used in enrichment-specific results
TREATMENTS = ["GPT-5.1", "Qwen3.5-4B", "Non-enriched"]
COLORS     = {"GPT-5.1": "#2563EB", "Qwen3.5-4B": "#DC2626", "Non-enriched": "#16A34A"}
MARKERS    = {"GPT-5.1": "o",        "Qwen3.5-4B": "s",       "Non-enriched": "^"}

DIMENSIONS = ["accuracy", "word", "explain", "support"]
DIM_LABELS = {
    "accuracy": "Label Accuracy",
    "word":     "Label Clarity",
    "explain":  "Explainability",
    "support":  "Faithfulness",
}
FLOWS      = ["f1", "f2", "f3"]
GRAPH_KEYS = ["GA", "GB", "GC"]

LIKERT_COLORS = ["#EF4444", "#F97316", "#86EFAC", "#16A34A"]  # 1 → 4

ALPHA = 0.05   # Wilcoxon / Friedman: exploratory only given n=12

# ── Survey question mapping ───────────────────────────────────────────────────
# Keys   : exact Qualtrics column names (including trailing _1)
# Values : treatment ("gpt"|"qwen"|"non"), scenario, task, confidence (str→float)
# Treatment short codes are normalised to full names via TREATMENT_NAMES below.

TREATMENT_NAMES = {"gpt": "GPT-5.1", "qwen": "Qwen3.5-4B", "non": "Non-enriched"}

survey_question_mapping: dict[str, dict] = {
    "Q1accuracyf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q1wordf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q1explainf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q1supportf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q2accuracyf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q2wordf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q2explainf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q2supportf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q3accuracyf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.88"},
    "Q3wordf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.88"},
    "Q3explainf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.88"},
    "Q3supportf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.88"},
    "Q4accuracyf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.89"},
    "Q4wordf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.98"},
    "Q4explainf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.98"},
    "Q4supportf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.98"},
    "Q5accuracyf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q5wordf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q5explainf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q5supportf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q6accuracyf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q6wordf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q6explainf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q6supportf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.95"},
    "Q7accuracyf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q7wordf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q7explainf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q7supportf1_1": {"treatment": "gpt", "scenario": "1", "task": "correctness", "confidence": "0.90"},
    "Q8accuracyf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.92"},
    "Q8wordf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.92"},
    "Q8explainf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.92"},
    "Q8supportf1_1": {"treatment": "qwen", "scenario": "1", "task": "correctness", "confidence": "0.92"},
    "Q1GAf1_1": {"treatment": "gpt",  "scenario": "1", "task": "DIR"},
    "Q2GAf1_1": {"treatment": "gpt",  "scenario": "1", "task": "DIR"},
    "Q1GBf1_1": {"treatment": "non",  "scenario": "1", "task": "DIR"},
    "Q2GBf1_1": {"treatment": "non",  "scenario": "1", "task": "DIR"},
    "Q1GCf1_1": {"treatment": "qwen", "scenario": "1", "task": "DIR"},
    "Q2GCf1_1": {"treatment": "qwen", "scenario": "1", "task": "DIR"},
    "rankingf1_1": {"treatment": "gpt",  "scenario": "1", "task": "DIR"},
    "rankingf1_2": {"treatment": "non",  "scenario": "1", "task": "DIR"},
    "rankingf1_3": {"treatment": "qwen", "scenario": "1", "task": "DIR"},
    "openf1": {"treatment": "", "scenario": "1", "task": "DIR"},
    "Q1accuracyf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q1wordf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q1explainf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q1supportf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q2accuracyf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.88"},
    "Q2wordf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.88"},
    "Q2explainf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.88"},
    "Q2supportf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.88"},
    "Q3accuracyf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q3wordf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q3explainf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q3supportf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q4accuracyf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.95"},
    "Q4wordf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.95"},
    "Q4explainf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.95"},
    "Q4supportf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.95"},
    "Q5accuracyf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q5wordf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q5explainf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q5supportf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.86"},
    "Q6accuracyf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q6wordf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q6explainf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q6supportf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q7accuracyf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.92"},
    "Q7wordf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.92"},
    "Q7explainf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.92"},
    "Q7supportf2_1": {"treatment": "qwen", "scenario": "2", "task": "correctness", "confidence": "0.92"},
    "Q8accuracyf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q8wordf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q8explainf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q8supportf2_1": {"treatment": "gpt", "scenario": "2", "task": "correctness", "confidence": "0.90"},
    "Q1GAf2_1": {"treatment": "qwen", "scenario": "2", "task": "DIR"},
    "Q2GAf2_1": {"treatment": "qwen", "scenario": "2", "task": "DIR"},
    "Q1GBf2_1": {"treatment": "gpt",  "scenario": "2", "task": "DIR"},
    "Q2GBf2_1": {"treatment": "gpt",  "scenario": "2", "task": "DIR"},
    "Q1GCf2_1": {"treatment": "non",  "scenario": "2", "task": "DIR"},
    "Q2GCf2_1": {"treatment": "non",  "scenario": "2", "task": "DIR"},
    "rankingf2_1": {"treatment": "qwen", "scenario": "2", "task": "DIR"},
    "rankingf2_2": {"treatment": "gpt",  "scenario": "2", "task": "DIR"},
    "rankingf2_3": {"treatment": "non",  "scenario": "2", "task": "DIR"},
    "openf2": {"treatment": "", "scenario": "2", "task": "DIR"},
    "Q1accuracyf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.99"},
    "Q1wordf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.99"},
    "Q1explainf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.99"},
    "Q1supportf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.99"},
    "Q2accuracyf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q2wordf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q2explainf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q2supportf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q3accuracyf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.97"},
    "Q3wordf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.97"},
    "Q3explainf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.97"},
    "Q3supportf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.97"},
    "Q4accuracyf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q4wordf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q4explainf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q4supportf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.86"},
    "Q5accuracyf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.90"},
    "Q5wordf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.90"},
    "Q5explainf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.90"},
    "Q5supportf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.90"},
    "Q6accuracyf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.95"},
    "Q6wordf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.95"},
    "Q6explainf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.95"},
    "Q6supportf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.95"},
    "Q7accuracyf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q7wordf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q7explainf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q7supportf3_1": {"treatment": "gpt", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q8accuracyf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q8wordf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q8explainf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q8supportf3_1": {"treatment": "qwen", "scenario": "3", "task": "correctness", "confidence": "0.88"},
    "Q1GAf3_1": {"treatment": "non",  "scenario": "3", "task": "DIR"},
    "Q2GAf3_1": {"treatment": "non",  "scenario": "3", "task": "DIR"},
    "Q1GBf3_1": {"treatment": "qwen", "scenario": "3", "task": "DIR"},
    "Q2GBf3_1": {"treatment": "qwen", "scenario": "3", "task": "DIR"},
    "Q1GCf3_1": {"treatment": "gpt",  "scenario": "3", "task": "DIR"},
    "Q2GCf3_1": {"treatment": "gpt",  "scenario": "3", "task": "DIR"},
    "rankingf3_1": {"treatment": "non",  "scenario": "3", "task": "DIR"},
    "rankingf3_2": {"treatment": "qwen", "scenario": "3", "task": "DIR"},
    "rankingf3_3": {"treatment": "gpt",  "scenario": "3", "task": "DIR"},
    "openf3": {"treatment": "", "scenario": "3", "task": "DIR"},
}

def _treatment(code: str) -> str:
    """Normalise short treatment code to full display name."""
    return TREATMENT_NAMES.get(code, code)

# ── Scalability constants ─────────────────────────────────────────────────────
SCALE_LABELS     = [m["label"]      for m in SCALE_MILESTONES]
SCALE_NODECOUNTS = [m["node_count"] for m in SCALE_MILESTONES]
CRASH_SENTINEL   = -1
INFERENCE_COLS   = ["generation_time", "prompt_tokens", "output_tokens",
                    "stop_reason", "valid_edges"]

# Event types present in scalability log_run_results.csv
EVENT_TYPES      = ["issue", "commit"]
EVENT_MARKERS    = {"issue": "o", "commit": "s"}
EVENT_LINESTYLE  = {"issue": "-", "commit": "--"}
EVENT_ALPHA      = {"issue": 0.45, "commit": 0.35}


# ═════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═════════════════════════════════════════════════════════════════════════════

def _read(path: str) -> pd.DataFrame | None:
    p = Path(path)
    if not p.exists():
        print(f"  [SKIP] {path}")
        return None
    df = pd.read_csv(p)
    ts_col = next((c for c in df.columns if c.lower() == "timestamp"), None)
    if ts_col:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")
        if ts_col != "timestamp":
            df.rename(columns={ts_col: "timestamp"}, inplace=True)
    return df


def load_survey_labels() -> "pd.DataFrame | None":
    """Load the Qualtrics label export (human-readable strings instead of values)."""
    p = Path(SURVEY_LABEL_PATH)
    if not p.exists():
        print(f"  [SKIP] {SURVEY_LABEL_PATH} not found — background analysis skipped")
        return None
    df = pd.read_csv(p)
    # Drop the two Qualtrics meta-rows (label row + ImportId row)
    # Keep only rows where the first column looks like a real date
    mask = pd.to_datetime(df.iloc[:, 0], errors="coerce").notna()
    df = df[mask].reset_index(drop=True)
    # Normalise flow
    FLOW_NORM = {
        "scenario 1": "f1", "scenario 2": "f2", "scenario 3": "f3",
        "1": "f1", "2": "f2", "3": "f3",
        "f1": "f1", "f2": "f2", "f3": "f3",
    }
    if "flow" in df.columns:
        df["flow"] = (df["flow"].astype(str).str.strip().str.lower()
                      .map(FLOW_NORM))
    return df


def _freq_table(series: "pd.Series", label: str, indent: int = 4) -> "pd.DataFrame":
    """Return a frequency + percentage table for a categorical series."""
    vc    = series.dropna().value_counts()
    pct   = (vc / vc.sum() * 100).round(1)
    table = pd.DataFrame({"Count": vc, "%": pct})
    table.index.name = label
    pad = " " * indent
    print(f"\n{pad}{label}:")
    for row_label, row in table.iterrows():
        print(f"{pad}  {str(row_label):<45} {int(row['Count']):>3}  ({row['%']:.1f}%)")
    return table


def r00_background(label_df: "pd.DataFrame"):
    section("R00", "Participant background — descriptive tables")

    # ── Column mapping: CSV column → display label ────────────────────────────
    # Adjust these keys if your label CSV uses different column names.
    BACKGROUND_COLS = {
        "Q1 Age":          "Age consent (18+)",
        "Q1 background":   "Primary background",
        "Q2 background":   "Field of study",
        "Q4 background":   "Software artifact experience",
    }
    # Q3 background_1..4 are familiarity Likert items — treat separately
    FAMILIARITY_COLS = {
        "Q3 background_1": "Software traceability",
        "Q3 background_2": "Requirements engineering",
        "Q3 background_3": "Graph comprehension",
        "Q3 background_4": "Model-driven engineering",
    }

    tables = {}

    print(f"\n  Total responses loaded: {len(label_df)}")
    if "flow" in label_df.columns:
        fc = label_df["flow"].value_counts()
        print(f"  Flow distribution: {fc.to_dict()}")

    # ── Categorical background questions ─────────────────────────────────────
    for col, disp in BACKGROUND_COLS.items():
        if col not in label_df.columns:
            print(f"  [SKIP] column not found: {col}")
            continue
        tables[disp] = _freq_table(label_df[col], disp)

    # ── Familiarity ratings (ordinal) ────────────────────────────────────────
    print("\n    Familiarity with key concepts:")
    fam_rows = []
    for col, disp in FAMILIARITY_COLS.items():
        if col not in label_df.columns:
            continue
        vc  = label_df[col].dropna().value_counts()
        pct = (vc / vc.sum() * 100).round(1)
        fam_rows.append({"Concept": disp, **{k: f"{v} ({pct[k]:.0f}%)"
                          if k in pct else "0 (0%)"
                          for k, v in vc.items()}})
    if fam_rows:
        fam_df = pd.DataFrame(fam_rows).set_index("Concept")
        print(fam_df.to_string())
        tables["Familiarity"] = fam_df

    # ── Save figure: stacked bar of familiarity ratings ──────────────────────
    fam_data = {}
    FAM_ORDER = ["Not at all familiar", "Slightly familiar",
                 "Moderately familiar", "Very familiar", "Extremely familiar"]
    FAM_COLORS = ["#FEE2E2", "#FED7AA", "#FEF9C3", "#BBF7D0", "#6EE7B7"]

    for col, disp in FAMILIARITY_COLS.items():
        if col not in label_df.columns:
            continue
        vc = label_df[col].dropna().value_counts()
        fam_data[disp] = [int(vc.get(lvl, 0)) for lvl in FAM_ORDER]

    if fam_data:
        fig, ax = plt.subplots(figsize=(11, max(3, len(fam_data) * 0.7 + 1.5)))
        lefts = np.zeros(len(fam_data))
        labels_fam = list(fam_data.keys())
        totals_fam = np.array([sum(fam_data[l]) for l in labels_fam], dtype=float)
        totals_fam = np.where(totals_fam == 0, 1, totals_fam)

        for i, (lvl, color) in enumerate(zip(FAM_ORDER, FAM_COLORS)):
            vals = np.array([fam_data[l][i] for l in labels_fam], dtype=float)
            pcts = vals / totals_fam * 100
            bars = ax.barh(labels_fam, pcts, left=lefts,
                           color=color, edgecolor="white", linewidth=0.5,
                           label=lvl)
            for bar, cnt in zip(bars, vals):
                if bar.get_width() > 8:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_y() + bar.get_height() / 2,
                            f"{int(cnt)}", ha="center", va="center",
                            fontsize=8, color="#1F2937", fontweight="bold")
            lefts += pcts

        ax.set_xlim(0, 100)
        ax.set_xlabel("% of participants")
        ax.set_title("Familiarity with key concepts", fontweight="bold")
        ax.invert_yaxis()
        ax.axvline(50, color="grey", linewidth=0.7, linestyle="--", alpha=0.5)
        ax.grid(axis="x", linestyle="--", alpha=0.3)
        ax.legend(title="Familiarity level", bbox_to_anchor=(1.01, 1),
                  loc="upper left", fontsize=8)
        plt.tight_layout()
        savefig("R00_familiarity")

    # ── Save figure: primary background bar chart ─────────────────────────────
    bg_col = "Q1 background"
    if bg_col in label_df.columns:
        vc  = label_df[bg_col].dropna().value_counts()
        pct = vc / vc.sum() * 100

        fig, ax = plt.subplots(figsize=(8, max(3, len(vc) * 0.55 + 1.5)))
        bars = ax.barh(vc.index, pct.values,
                       color="#2563EB", alpha=0.80, edgecolor="white")
        for bar, cnt in zip(bars, vc.values):
            ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                    f"n={cnt}", va="center", fontsize=8, color="#374151")
        ax.set_xlabel("% of participants")
        ax.set_xlim(0, pct.max() + 12)
        ax.set_title("Primary background of participants", fontweight="bold")
        ax.invert_yaxis()
        ax.grid(axis="x", linestyle="--", alpha=0.3)
        plt.tight_layout()
        savefig("R00_primary_background")

    # ── Save figure: software artifact experience ─────────────────────────────
    exp_col = "Q4 background"
    if exp_col in label_df.columns:
        vc  = label_df[exp_col].dropna().value_counts()
        pct = vc / vc.sum() * 100

        fig, ax = plt.subplots(figsize=(8, max(3, len(vc) * 0.55 + 1.5)))
        ax.barh(vc.index, pct.values,
                color="#16A34A", alpha=0.80, edgecolor="white")
        for bar, cnt in zip(ax.patches, vc.values):
            ax.text(bar.get_width() + 0.8, bar.get_y() + bar.get_height() / 2,
                    f"n={cnt}", va="center", fontsize=8, color="#374151")
        ax.set_xlabel("% of participants")
        ax.set_xlim(0, pct.max() + 12)
        ax.set_title("Software artifact experience", fontweight="bold")
        ax.invert_yaxis()
        ax.grid(axis="x", linestyle="--", alpha=0.3)
        plt.tight_layout()
        savefig("R00_artifact_experience")

    # ── Export all tables to CSV ──────────────────────────────────────────────
    for name, tbl in tables.items():
        safe = name.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        tbl.to_csv(FIGURES_DIR / f"R00_table_{safe}.csv")
    print(f"\n  Tables saved to {FIGURES_DIR}/R00_table_*.csv")


def load_simulation() -> dict:
    """Load per-model simulation CSVs (enrichment, kg, hardware — no logs)."""
    data = {}
    for model in MODELS:
        data[model] = {}
        for src, path in PATHS[model].items():
            df = _read(path)
            if df is not None:
                data[model][src] = df
    return data


def load_scalability() -> dict:
    """Load per-milestone scalability CSVs, attach milestone metadata."""
    data = {}
    for model in LLM_MODELS:
        frames = {src: [] for src in SCALE_PATHS[model]}
        for src in SCALE_PATHS[model]:
            for i, ms in enumerate(SCALE_MILESTONES):
                path = SCALE_PATHS[model][src][i]
                df   = _read(path)
                if df is None:
                    continue
                df["milestone"]  = ms["label"]
                df["node_count"] = ms["node_count"]
                df["run_index"]  = range(len(df))
                # Replace crash sentinels
                if src == "logs":
                    for col in INFERENCE_COLS:
                        if col in df.columns:
                            df[col] = df[col].replace(CRASH_SENTINEL, np.nan)
                    if "HTTP_response" in df.columns:
                        df["http_status"] = (
                            df["HTTP_response"].astype(str)
                            .str.extract(r"(\d{3})")[0]
                            .astype(float)
                        )
                frames[src].append(df)
        data[model] = {
            src: pd.concat(fs, ignore_index=True)
            for src, fs in frames.items() if fs
        }
    return data


def load_survey() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and reshape Qualtrics CSV using survey_question_mapping for all lookups."""
    df = _read(SURVEY_PATH)
    if df is None:
        return None, None, None, None
    # Drop second Qualtrics header row if present
    if df.iloc[0].astype(str).str.contains(r"Q_|ImportId|{", regex=True).any():
        df = df.iloc[1:].reset_index(drop=True)
    df = df[df["Finished"].astype(str).str.lower().isin(["true", "1", "yes"])].copy()
    # Normalise flow values: "scenario 1" / "scenario 2" / "scenario 3" → "f1" / "f2" / "f3"
    FLOW_NORMALISE = {
        "scenario 1": "f1", "scenario 2": "f2", "scenario 3": "f3",
        "1": "f1", "2": "f2", "3": "f3",
        "f1": "f1", "f2": "f2", "f3": "f3",
    }
    df["flow"] = (df["flow"].astype(str).str.strip().str.lower()
                  .map(FLOW_NORMALISE))
    # Drop rows where flow could not be resolved (e.g. the two "nan" rows)
    before = len(df)
    df = df[df["flow"].notna()].copy()
    dropped = before - len(df)
    if dropped:
        print(f"  [INFO] Dropped {dropped} rows with unresolvable flow value")
    print(f"  Survey: {len(df)} completed responses, flows: {df['flow'].value_counts().to_dict()}")

    # ── Edge ratings (long format) ───────────────────────────────────────────
    # Column name IS the mapping key (keys already include _1 suffix)
    edge_rows = []
    for pid, row in df.iterrows():
        flow = row["flow"]
        for qnum in range(1, 9):
            for dim in DIMENSIONS:
                col = f"Q{qnum}{dim}{flow}_1"
                if col not in df.columns or col not in survey_question_mapping:
                    continue
                val = pd.to_numeric(row[col], errors="coerce")
                # Keep 0 ("I don't know") as 0 — excluded in standard charts
                # via count_likert (range 1–4), included as neutral in diverging chart.
                if pd.isna(val):
                    val = np.nan
                m   = survey_question_mapping[col]
                edge_rows.append({
                    "participant": pid,
                    "flow":        flow,
                    "edge_num":    qnum,
                    "edge_id":     f"E{qnum}f{flow[-1]}",  # e.g. E3f2
                    "dimension":   dim,
                    "treatment":   _treatment(m.get("treatment", "")),
                    "confidence":  float(m["confidence"]) if "confidence" in m else np.nan,
                    "scenario":    m.get("scenario", ""),
                    "rating":      val,
                })
    edge_ratings = pd.DataFrame(edge_rows)

    # ── Graph ratings (long format) ──────────────────────────────────────────
    # Q1G*/Q2G* columns: Q1=usefulness, Q2=completeness; treatment from mapping
    graph_rows = []
    for pid, row in df.iterrows():
        flow = row["flow"]
        for gk in GRAPH_KEYS:                               # GA, GB, GC
            for q_idx, gdim in enumerate(["usefulness", "completeness"], 1):
                col = f"Q{q_idx}G{gk[1]}{flow}_1"          # e.g. Q1GAf1_1
                if col not in df.columns or col not in survey_question_mapping:
                    continue
                val = pd.to_numeric(row[col], errors="coerce")
                m   = survey_question_mapping[col]
                graph_rows.append({
                    "participant": pid,
                    "flow":        flow,
                    "graph_key":   gk,
                    "graph_dim":   gdim,
                    "treatment":   _treatment(m.get("treatment", "")),
                    "scenario":    m.get("scenario", ""),
                    "rating":      val,
                })
    graph_ratings = pd.DataFrame(graph_rows)

    # ── Rankings (long format) ───────────────────────────────────────────────
    # rankingfX_N: value = rank assigned to that graph; treatment from mapping
    rank_rows = []
    for pid, row in df.iterrows():
        flow = row["flow"]
        for col_suffix in ["_1", "_2", "_3"]:
            col = f"ranking{flow}{col_suffix}"
            if col not in df.columns or col not in survey_question_mapping:
                continue
            val = pd.to_numeric(row[col], errors="coerce")
            m   = survey_question_mapping[col]
            rank_rows.append({
                "participant": pid,
                "flow":        flow,
                "treatment":   _treatment(m.get("treatment", "")),
                "scenario":    m.get("scenario", ""),
                "rank":        val,
            })
    rankings = pd.DataFrame(rank_rows)

    return df, edge_ratings, graph_ratings, rankings


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def savefig(name: str):
    path = FIGURES_DIR / f"{name}.png"
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  → {path.name}")


def section(rid: str, title: str):
    print(f"\n{'═'*70}\n  {rid}  {title}\n{'═'*70}")


def describe(s: pd.Series, label: str = "", indent: int = 4):
    s = s.dropna()
    pad = " " * indent
    tag = f"{label}: " if label else ""
    if s.empty:
        print(f"{pad}{tag}(no data)")
        return
    print(f"{pad}{tag}n={len(s)}  mean={s.mean():.3f}  median={s.median():.1f}  "
          f"sd={s.std():.3f}  min={s.min():.3f}  max={s.max():.3f}")


def count_likert(s: pd.Series, n: int = 4) -> list[int]:
    """Count ratings 1..n, ignoring NaN. Used for the standard (0-excluded) chart."""
    return [int((s.dropna() == v).sum()) for v in range(1, n + 1)]


def count_likert_with_neutral(s: pd.Series) -> dict:
    """
    Count ratings 0..4 where 0 = 'I do not know' (neutral).
    Returns dict with keys: 'neg' [count_1, count_2], 'neutral' [count_0], 'pos' [count_3, count_4]
    so the diverging chart can split them correctly.
    """
    s_num = pd.to_numeric(s, errors="coerce")
    return {
        "neg":     [int((s_num == v).sum()) for v in [1, 2]],
        "neutral": [int((s_num == 0).sum())],
        "pos":     [int((s_num == v).sum()) for v in [3, 4]],
        "total":   int(s_num.notna().sum()),
    }


def regression(x, y):
    mask = ~(np.isnan(x) | np.isnan(y))
    if mask.sum() < 3:
        return 0, float(np.nanmean(y)), 0
    sl, ic, r, *_ = sp_stats.linregress(x[mask], y[mask])
    return sl, ic, r ** 2


def wilcoxon_pair(a: pd.Series, b: pd.Series, label: str):
    paired = pd.DataFrame({"a": a.reset_index(drop=True),
                           "b": b.reset_index(drop=True)}).dropna()
    if len(paired) < 4:
        print(f"    Wilcoxon [{label}]: n={len(paired)} too small, skipped")
        return
    try:
        stat, p = sp_stats.wilcoxon(paired["a"], paired["b"])
        sig = "*" if p < ALPHA else "ns"
        print(f"    Wilcoxon [{label}]: W={stat:.1f} p={p:.4f} ({sig})  ⚠ exploratory n={len(paired)}")
    except Exception as e:
        print(f"    Wilcoxon [{label}]: {e}")


def friedman_test(groups: dict, label: str):
    arrays = [np.array(g.dropna()) for g in groups.values()]
    n = min(len(a) for a in arrays)
    if n < 4:
        print(f"    Friedman [{label}]: n={n} too small, skipped")
        return
    arrays = [a[:n] for a in arrays]
    try:
        stat, p = sp_stats.friedmanchisquare(*arrays)
        sig = "*" if p < ALPHA else "ns"
        print(f"    Friedman [{label}]: χ²={stat:.3f} p={p:.4f} ({sig})  ⚠ exploratory n={n}")
    except Exception as e:
        print(f"    Friedman [{label}]: {e}")


# ─── Plot helpers ─────────────────────────────────────────────────────────────

def diverging_likert(data: dict[str, list[int]], title: str, name: str,
                     note: str = "", scale_labels: list[str] | None = None):
    """Horizontal stacked bar, left-to-right 1→4."""
    labels = list(data.keys())
    counts = np.array([data[l] for l in labels], dtype=float)
    totals = counts.sum(axis=1, keepdims=True)
    pcts   = np.where(totals > 0, counts / totals * 100, 0)

    fig, ax = plt.subplots(figsize=(10, max(3, 0.55 * len(labels) + 1.8)))
    lefts = np.zeros(len(labels))
    for i in range(4):
        bars = ax.barh(labels, pcts[:, i], left=lefts,
                       color=LIKERT_COLORS[i], edgecolor="white", linewidth=0.5,
                       label=(scale_labels[i] if scale_labels else str(i + 1)))
        for bar, cnt in zip(bars, counts[:, i]):
            if cnt > 0 and pcts[list(labels).index(bar.get_label()) if False else 0][i] > 6:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{int(cnt)}", ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")
        lefts += pcts[:, i]

    ax.set_xlim(0, 100)
    ax.set_xlabel("% of responses")
    ax.set_title(title, fontweight="bold")
    ax.axvline(50, color="grey", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    ax.legend(title="Rating", bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    if note:
        fig.text(0.01, 0.01, f"Note: {note}", fontsize=7, color="grey")
    plt.tight_layout()
    savefig(name)


def diverging_likert_neutral(data: dict[str, dict], title: str, name: str,
                             note: str = ""):
    """
    True diverging stacked bar chart with neutral centre.

    Layout (left → right):
      [1 | 2]  |  [0 = I don't know]  |  [3 | 4]
       negative        neutral              positive

    data: {row_label: count_likert_with_neutral(series)}
    The x-axis is centred so negatives go left and positives go right.
    """
    labels = list(data.keys())
    n_rows = len(labels)

    NEG_COLORS  = ["#EF4444", "#F97316"]          # 1, 2
    POS_COLORS  = ["#86EFAC", "#16A34A"]           # 3, 4
    NEUT_COLOR  = "#E5E7EB"                        # 0 — light grey / near-white

    # Compute totals and percentages
    totals = np.array([
        data[l]["neg"][0] + data[l]["neg"][1] +
        data[l]["neutral"][0] +
        data[l]["pos"][0] + data[l]["pos"][1]
        for l in labels
    ], dtype=float)
    totals = np.where(totals == 0, 1, totals)     # avoid /0

    neg_pcts  = np.array([[data[l]["neg"][i] / totals[j] * 100
                           for j, l in enumerate(labels)] for i in range(2)])
    neut_pcts = np.array([data[l]["neutral"][0] / totals[j] * 100
                          for j, l in enumerate(labels)])
    pos_pcts  = np.array([[data[l]["pos"][i] / totals[j] * 100
                           for j, l in enumerate(labels)] for i in range(2)])

    # Half the neutral bar extends each side of centre
    neut_half = neut_pcts / 2

    fig, ax = plt.subplots(figsize=(12, max(3, 0.6 * n_rows + 2)))
    y = np.arange(n_rows)

    # ── Negative side (extends left from -neut_half) ─────────────────────────
    left_neg = -neut_half.copy()
    for i in range(1, -1, -1):           # plot 2 first so 1 is outermost
        widths = -neg_pcts[i]            # negative = goes left
        bars = ax.barh(y, widths, left=left_neg,
                       color=NEG_COLORS[i], edgecolor="white", linewidth=0.5,
                       label=f"{i + 1} – {'Strongly disagree' if i==0 else 'Disagree'}")
        for bar, cnt_idx in zip(bars, range(n_rows)):
            cnt = data[labels[cnt_idx]]["neg"][i]
            w   = abs(bar.get_width())
            if w > 2:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{cnt}", ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")
        left_neg += widths      # move further left

    # ── Positive side (extends right from +neut_half) ────────────────────────
    left_pos = neut_half.copy()
    for i in range(2):
        widths = pos_pcts[i]
        bars = ax.barh(y, widths, left=left_pos,
                       color=POS_COLORS[i], edgecolor="white", linewidth=0.5,
                       label=f"{i + 3} – {'Agree' if i==0 else 'Strongly agree'}")
        for bar, cnt_idx in zip(bars, range(n_rows)):
            cnt = data[labels[cnt_idx]]["pos"][i]
            w   = bar.get_width()
            if w > 2:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{cnt}", ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")
        left_pos += widths

    # ── Neutral centre bar ────────────────────────────────────────────────────
    ax.barh(y, neut_pcts, left=-neut_half,
            color=NEUT_COLOR, edgecolor="#9CA3AF", linewidth=0.6,
            label="0 – I don't know")
    for i, l in enumerate(labels):
        cnt = data[l]["neutral"][0]
        if cnt == 0:
            continue
        bar_w = neut_pcts[i]   # full width of neutral bar in % units
        if bar_w >= 6:
            # Wide enough — label sits centred inside the bar at x=0
            ax.text(0, i, f"{cnt}",
                    ha="center", va="center",
                    fontsize=8, color="#374151", fontweight="bold")
        else:
            # Narrow or zero-width bar — label floats just above with an arrow-style
            # annotation so it is always visible
            ax.annotate(f"n={cnt}",
                        xy=(0, i),
                        xytext=(0, i - 0.45),
                        ha="center", va="bottom",
                        fontsize=7, color="#374151", fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color="#9CA3AF",
                                        lw=0.8, shrinkA=0, shrinkB=2))

    # ── Axes & decoration ─────────────────────────────────────────────────────
    max_extent = max(
        np.max(np.abs(left_neg)) if n_rows else 50,
        np.max(left_pos)         if n_rows else 50,
    ) + 5
    ax.set_xlim(-max_extent, max_extent)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("← Disagree   |   % of responses   |   Agree →")
    ax.set_title(title, fontweight="bold")
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.3)

    # Custom x-tick labels showing absolute percentages
    xticks = ax.get_xticks()
    ax.set_xticklabels([f"{abs(int(t))}%" for t in xticks])

    handles, legend_labels = ax.get_legend_handles_labels()
    # Reorder: 1, 2, neutral, 3, 4
    order = [0, 1, 4, 2, 3] if len(handles) == 5 else list(range(len(handles)))
    ax.legend([handles[i] for i in order if i < len(handles)],
              [legend_labels[i] for i in order if i < len(handles)],
              title="Rating", bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)

    if note:
        fig.text(0.01, 0.01, f"Note: {note}", fontsize=7, color="grey")
    plt.tight_layout()
    savefig(name)


def radar_chart(values: dict[str, list[float]], categories: list[str],
                title: str, name: str, vmin: float = 1, vmax: float = 4):
    N   = len(categories)
    angles = [n / float(N) * 2 * pi for n in range(N)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    ax.set_theta_offset(pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=9)
    ax.set_ylim(vmin, vmax)
    ax.set_yticks(np.linspace(vmin, vmax, 4))

    for model, vals in values.items():
        v = vals + vals[:1]
        ax.plot(angles, v, linewidth=2, color=COLORS.get(model, "#888"),
                label=model, marker=MARKERS.get(model, "o"))
        ax.fill(angles, v, color=COLORS.get(model, "#888"), alpha=0.12)

    ax.set_title(title, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    plt.tight_layout()
    savefig(name)


def scatter_reg(ax, x, y, model: str, label: str = "", jitter: float = 0):
    xj = x + np.random.uniform(-jitter, jitter, len(x)) if jitter else x
    ax.scatter(xj, y, color=COLORS.get(model, "#888"), alpha=0.4,
               s=25, marker=MARKERS.get(model, "o"))
    sl, ic, r2 = regression(x, y)
    xr = np.linspace(np.nanmin(x), np.nanmax(x), 200)
    ax.plot(xr, sl * xr + ic, color=COLORS.get(model, "#888"),
            linewidth=2, linestyle="--",
            label=f"{model}  R²={r2:.2f}" + (f"  {label}" if label else ""))
    return sl, ic, r2


def line_milestone(ax, scale_data: dict, col: str, src: str, unit: float = 1):
    x = SCALE_NODECOUNTS
    for model in scale_data:  # iterate only the keys passed in
        df = scale_data[model].get(src)
        if df is None or col not in df.columns:
            continue
        means = [df[df["milestone"] == ms][col].mean() * unit
                 for ms in SCALE_LABELS]
        sds   = [df[df["milestone"] == ms][col].std()  * unit
                 for ms in SCALE_LABELS]
        ax.plot(x, means, "o-", color=COLORS[model], label=model, linewidth=2)
        ax.fill_between(x,
                        np.array(means) - np.array(sds),
                        np.array(means) + np.array(sds),
                        color=COLORS[model], alpha=0.15)
    ax.set_xticks(SCALE_NODECOUNTS)
    ax.set_xticklabels(SCALE_LABELS, rotation=15, ha="right")
    ax.grid(linestyle="--", alpha=0.35)
    ax.legend()


def scatter_reg_event(ax, df: "pd.DataFrame", x_col: str, y_col: str,
                      model: str, event_col: str = "event",
                      unit_y: float = 1.0, jitter_x: float = 0):
    """
    Scatter + regression line split by event type (issue / commit).
    Points: colour = model, marker = event type.
    Regression lines: one per event type, same colour, different linestyle.
    Returns dict of {event: (slope, intercept, r2)}.
    """
    results = {}
    valid = df[[x_col, y_col]].dropna()
    if event_col in df.columns:
        events = df.loc[valid.index, event_col].fillna("unknown")
    else:
        events = pd.Series(["unknown"] * len(valid), index=valid.index)

    for evt in EVENT_TYPES:
        mask = events == evt
        sub  = valid[mask]
        if sub.empty:
            continue
        x = sub[x_col].values.astype(float)
        y = sub[y_col].values.astype(float) * unit_y
        if jitter_x:
            x = x + np.random.uniform(-jitter_x, jitter_x, len(x))

        ax.scatter(x, y,
                   color=COLORS.get(model, "#888"),
                   marker=EVENT_MARKERS[evt],
                   alpha=EVENT_ALPHA[evt], s=28,
                   label=f"{model} – {evt}")

        sl, ic, r2 = regression(sub[x_col].values.astype(float),
                                sub[y_col].values.astype(float) * unit_y)
        if len(sub) >= 3:
            xr = np.linspace(sub[x_col].min(), sub[x_col].max(), 200)
            ax.plot(xr, sl * xr + ic,
                    color=COLORS.get(model, "#888"),
                    linewidth=1.8,
                    linestyle=EVENT_LINESTYLE[evt],
                    label=f"{model} – {evt}  R²={r2:.2f}")
        results[evt] = (sl, ic, r2)
    return results


def line_milestone_event(ax, scale_data: dict, col: str, src: str,
                         unit: float = 1, event_col: str = "event"):
    """
    Mean ± SD trend lines across milestones per model, showing:
      - issue line       (solid,   circle marker)
      - commit line      (dashed,  square marker)
      - combined line    (dotted,  diamond marker) — all events together
    Colour = model, linestyle/marker = event type.
    """
    x = SCALE_NODECOUNTS
    for model in scale_data:  # iterate only the keys passed in
        df = scale_data[model].get(src)
        if df is None or col not in df.columns:
            continue
        ec = event_col if event_col in df.columns else None

        # Build list of (subset, label, linestyle, marker)
        splits = []
        if ec:
            for evt in EVENT_TYPES:
                sub = df[df[ec] == evt]
                if not sub.empty:
                    splits.append((sub, evt,
                                   EVENT_LINESTYLE[evt],
                                   EVENT_MARKERS[evt]))
        # Combined (all events regardless of type)
        splits.append((df, "combined", ":", "D"))

        for sub, label, ls, mk in splits:
            if sub.empty:
                continue
            means = [sub[sub["milestone"] == ms][col].mean() * unit
                     for ms in SCALE_LABELS]
            sds   = [sub[sub["milestone"] == ms][col].std()  * unit
                     for ms in SCALE_LABELS]
            # Combined line slightly thinner and more transparent
            lw    = 1.5 if label == "combined" else 2
            alpha = 0.07 if label == "combined" else 0.12
            ax.plot(x, means, ls, marker=mk, color=COLORS[model],
                    linewidth=lw, label=f"{model} – {label}",
                    alpha=0.75 if label == "combined" else 1.0)
            ax.fill_between(x,
                            np.array(means) - np.array(sds),
                            np.array(means) + np.array(sds),
                            color=COLORS[model], alpha=alpha)
    ax.set_xticks(SCALE_NODECOUNTS)
    ax.set_xticklabels(SCALE_LABELS, rotation=15, ha="right")
    ax.grid(linestyle="--", alpha=0.35)
    ax.legend(fontsize=7, ncol=2)


# ═════════════════════════════════════════════════════════════════════════════
# R01 — Perceived quality (diverging stacked Likert)
# ═════════════════════════════════════════════════════════════════════════════

def r01_perceived_quality(edge_ratings: pd.DataFrame):
    section("R01", "Perceived quality — diverging stacked Likert")

    scale_lbl = ["1 – Strongly disagree", "2 – Disagree",
                  "3 – Agree", "4 – Strongly agree"]

    # Per dimension, both LLM treatments — two versions per dimension
    for dim in DIMENSIONS:
        data_std  = {}   # 0 excluded
        data_neut = {}   # 0 as neutral centre
        for t in ["GPT-5.1", "Qwen3.5-4B"]:
            sub = edge_ratings[(edge_ratings["dimension"] == dim) &
                               (edge_ratings["treatment"] == t)]["rating"]
            describe(sub[sub > 0], f"{t} – {DIM_LABELS[dim]}")
            data_std[t]  = count_likert(sub[sub > 0])
            data_neut[t] = count_likert_with_neutral(sub)

        # Standard chart (0 excluded)
        diverging_likert(data_std,
                         title=f"Perceived quality — {DIM_LABELS[dim]} (excl. 'I don't know')",
                         name=f"R01_{dim}_standard",
                         note="0 = 'I do not know' excluded. Scale 1–4.",
                         scale_labels=scale_lbl)
        # Neutral diverging chart (0 centred)
        diverging_likert_neutral(data_neut,
                                 title=f"Perceived quality — {DIM_LABELS[dim]} (incl. neutral)",
                                 name=f"R01_{dim}_neutral",
                                 note="0 = 'I don't know' shown as neutral centre bar.")

    # All dimensions combined — both versions
    data_std_all  = {}
    data_neut_all = {}
    for t in ["GPT-5.1", "Qwen3.5-4B"]:
        sub = edge_ratings[edge_ratings["treatment"] == t]["rating"]
        data_std_all[t]  = count_likert(sub[sub > 0])
        data_neut_all[t] = count_likert_with_neutral(sub)
    diverging_likert(data_std_all,
                     title="Perceived quality — all dimensions combined (excl. 'I don't know')",
                     name="R01_combined_standard",
                     note="Aggregated across accuracy, clarity, explainability, faithfulness.",
                     scale_labels=scale_lbl)
    diverging_likert_neutral(data_neut_all,
                             title="Perceived quality — all dimensions combined (incl. neutral)",
                             name="R01_combined_neutral",
                             note="0 = 'I don't know' shown as neutral centre bar.")

    # ── Overview figure: all 4 dimensions × 2 models in one diverging chart ────
    # Row order: GPT then Qwen for each dimension, grouped by dimension
    NEG_COLORS_OV  = ["#EF4444", "#F97316"]
    POS_COLORS_OV  = ["#86EFAC", "#16A34A"]
    NEUT_COLOR_OV  = "#E5E7EB"
    DIM_ROW_COLORS = {          # subtle background stripe per dimension group
        "accuracy": "#EFF6FF",
        "word":     "#F0FDF4",
        "explain":  "#FFFBEB",
        "support":  "#FDF4FF",
    }

    # Build ordered row data
    row_labels  = []
    row_data    = []
    for dim in DIMENSIONS:
        for t in ["GPT-5.1", "Qwen3.5-4B"]:
            sub = edge_ratings[(edge_ratings["dimension"] == dim) &
                               (edge_ratings["treatment"] == t)]["rating"]
            row_labels.append(f"{DIM_LABELS[dim]}\n{t}")
            row_data.append(count_likert_with_neutral(sub))

    n_rows  = len(row_labels)
    y       = np.arange(n_rows)
    totals  = np.array([
        d["neg"][0] + d["neg"][1] + d["neutral"][0] + d["pos"][0] + d["pos"][1]
        for d in row_data
    ], dtype=float)
    totals  = np.where(totals == 0, 1, totals)

    neg_pcts  = np.array([[row_data[j]["neg"][i] / totals[j] * 100
                           for j in range(n_rows)] for i in range(2)])
    neut_pcts = np.array([row_data[j]["neutral"][0] / totals[j] * 100
                          for j in range(n_rows)])
    pos_pcts  = np.array([[row_data[j]["pos"][i] / totals[j] * 100
                           for j in range(n_rows)] for i in range(2)])
    neut_half = neut_pcts / 2

    fig, ax = plt.subplots(figsize=(14, n_rows * 0.65 + 2.5))

    # Dimension group background stripes (2 rows per dimension)
    for d_idx, dim in enumerate(DIMENSIONS):
        ax.axhspan(d_idx * 2 - 0.5, d_idx * 2 + 1.5,
                   color=DIM_ROW_COLORS[dim], alpha=0.35, zorder=0)
        # Dimension label on the left margin
        ax.text(-105, d_idx * 2 + 0.5, DIM_LABELS[dim],
                ha="right", va="center", fontsize=8,
                fontweight="bold", color="#374151")

    def _label_bar(ax, bar, cnt, side="left"):
        """Always show count: inside bar if wide enough, annotated outside if narrow."""
        if cnt == 0:
            return
        w = abs(bar.get_width())
        cx = bar.get_x() + bar.get_width() / 2
        cy = bar.get_y() + bar.get_height() / 2
        if w >= 5:
            ax.text(cx, cy, f"{cnt}", ha="center", va="center",
                    fontsize=7, color="white", fontweight="bold")
        else:
            # Float label just outside the bar end
            x_anchor = bar.get_x() if side == "left" else bar.get_x() + bar.get_width()
            ha = "right" if side == "left" else "left"
            offset = -1.0 if side == "left" else 1.0
            ax.annotate(f"{cnt}",
                        xy=(x_anchor, cy),
                        xytext=(x_anchor + offset, cy),
                        ha=ha, va="center",
                        fontsize=6.5, color="#374151", fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color="#9CA3AF",
                                        lw=0.6, shrinkA=0, shrinkB=2))

    # Negative bars (left)
    left_neg = -neut_half.copy()
    for i in range(1, -1, -1):
        widths = -neg_pcts[i]
        bars = ax.barh(y, widths, left=left_neg,
                       color=NEG_COLORS_OV[i], edgecolor="white", linewidth=0.4,
                       label=f"{i+1} – {'Strongly disagree' if i==0 else 'Disagree'}")
        for j, bar in enumerate(bars):
            _label_bar(ax, bar, row_data[j]["neg"][i], side="left")
        left_neg += widths

    # Positive bars (right)
    left_pos = neut_half.copy()
    for i in range(2):
        widths = pos_pcts[i]
        bars = ax.barh(y, widths, left=left_pos,
                       color=POS_COLORS_OV[i], edgecolor="white", linewidth=0.4,
                       label=f"{i+3} – {'Agree' if i==0 else 'Strongly agree'}")
        for j, bar in enumerate(bars):
            _label_bar(ax, bar, row_data[j]["pos"][i], side="right")
        left_pos += widths

    # Neutral centre bars
    ax.barh(y, neut_pcts, left=-neut_half,
            color=NEUT_COLOR_OV, edgecolor="#9CA3AF", linewidth=0.5,
            label="0 – I don't know")
    for j in range(n_rows):
        cnt = row_data[j]["neutral"][0]
        if cnt == 0:
            continue
        if neut_pcts[j] >= 6:
            ax.text(0, j, f"{cnt}", ha="center", va="center",
                    fontsize=7, color="#374151", fontweight="bold")
        else:
            ax.annotate(f"n={cnt}", xy=(0, j), xytext=(0, j - 0.42),
                        ha="center", va="bottom", fontsize=6.5, color="#374151",
                        fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color="#9CA3AF",
                                        lw=0.7, shrinkA=0, shrinkB=2))

    # Separator lines between dimension groups
    for d_idx in range(1, len(DIMENSIONS)):
        ax.axhline(d_idx * 2 - 0.5, color="#CBD5E1", linewidth=1, zorder=1)

    # Axes
    max_ext = max(np.max(np.abs(left_neg)), np.max(left_pos)) + 5
    ax.set_xlim(-max_ext, max_ext)
    ax.set_yticks(y)
    ax.set_yticklabels(row_labels, fontsize=8)
    ax.axvline(0, color="black", linewidth=0.9)
    ax.set_xlabel("← Disagree   |   % of responses   |   Agree →")
    ax.set_title("Perceived edge quality — all dimensions (incl. 'I don't know')",
                 fontweight="bold", pad=12)
    ax.invert_yaxis()
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    xticks = ax.get_xticks()
    ax.set_xticklabels([f"{abs(int(t))}%" for t in xticks])

    handles, leg_labels = ax.get_legend_handles_labels()
    order = [0, 1, 4, 2, 3] if len(handles) >= 5 else list(range(len(handles)))
    ax.legend([handles[i] for i in order if i < len(handles)],
              [leg_labels[i]  for i in order if i < len(handles)],
              title="Rating", bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    fig.text(0.01, 0.01, "Note: 0 = 'I don't know' shown as neutral centre bar.",
             fontsize=7, color="grey")
    plt.tight_layout()
    savefig("R01_overview_all_dimensions")

    # Exploratory Wilcoxon
    for dim in DIMENSIONS:
        a = edge_ratings[(edge_ratings["dimension"] == dim) &
                         (edge_ratings["treatment"] == "GPT-5.1")]["rating"]
        b = edge_ratings[(edge_ratings["dimension"] == dim) &
                         (edge_ratings["treatment"] == "Qwen3.5-4B")]["rating"]
        wilcoxon_pair(a, b, f"GPT vs Qwen – {DIM_LABELS[dim]}")


# ═════════════════════════════════════════════════════════════════════════════
# R02 — Quality per generated edge (grouped bar)
# ═════════════════════════════════════════════════════════════════════════════

def r02_quality_per_edge(edge_ratings: pd.DataFrame):
    section("R02", "Quality per generated edge — grouped bar chart")

    # Average the four dimensions per edge per treatment
    avg = (edge_ratings.groupby(["edge_id", "treatment"])["rating"]
           .mean().reset_index().rename(columns={"rating": "mean_rating"}))

    treatments_llm = ["GPT-5.1", "Qwen3.5-4B"]
    edge_ids = sorted(avg["edge_id"].unique())
    x = np.arange(len(edge_ids))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(8, len(edge_ids) * 1.2), 5))
    for i, t in enumerate(treatments_llm):
        sub  = avg[avg["treatment"] == t].set_index("edge_id").reindex(edge_ids)
        vals = sub["mean_rating"].values.astype(float)
        bars = ax.bar(x + i * width, vals, width, label=t,
                      color=COLORS[t], alpha=0.85, edgecolor="black", linewidth=0.5)
        for bar, v in zip(bars, vals):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                        f"{v:.1f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x + width / 2)
    ax.set_xticklabels(edge_ids, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Mean rating across dimensions (1–4)")
    ax.set_ylim(0, 4.5)
    ax.set_title("Average perceived quality per generated edge", fontweight="bold")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R02_quality_per_edge")

    # Console summary
    print("\n  Mean quality per edge:")
    print(avg.pivot(index="edge_id", columns="treatment", values="mean_rating").to_string())


# ═════════════════════════════════════════════════════════════════════════════
# R03 — Overall quality profile (radar)
# ═════════════════════════════════════════════════════════════════════════════

def r03_quality_radar(edge_ratings: pd.DataFrame):
    section("R03", "Overall quality profile — radar chart")

    values = {}
    for t in ["GPT-5.1", "Qwen3.5-4B"]:
        vals = []
        for dim in DIMENSIONS:
            sub = edge_ratings[(edge_ratings["treatment"] == t) &
                               (edge_ratings["dimension"] == dim)]["rating"]
            vals.append(sub.mean() if not sub.dropna().empty else 1.0)
            describe(sub, f"{t} – {DIM_LABELS[dim]}")
        values[t] = vals

    radar_chart(values,
                categories=[DIM_LABELS[d] for d in DIMENSIONS],
                title="Overall quality profile (mean per dimension)",
                name="R03_quality_radar")


# ═════════════════════════════════════════════════════════════════════════════
# R04 — Objective vs perceived correctness (grouped bar)
# ═════════════════════════════════════════════════════════════════════════════

def r04_objective_vs_perceived(edge_ratings: pd.DataFrame, sim_data: dict):
    section("R04", "Objective vs perceived correctness — grouped bar")
    # TODO: requires joining survey edge_id → enrichment_results llm_correct_generated_edges
    # Objective correctness (1 = correct, 0 = incorrect) must be mapped to the
    # same edge_id used in question_mapping.
    # Once that join is available, uncomment and adapt:
    #
    # perceived = edge_ratings[edge_ratings["dimension"] == "accuracy"] \
    #     .groupby(["edge_id", "treatment"])["rating"].mean().reset_index()
    # objective = ...  # load from enrichment_results, map edge_id
    # merged = perceived.merge(objective, on=["edge_id", "treatment"])
    #
    # fig, ax = plt.subplots(figsize=(9, 5))
    # for t in ["GPT-5.1", "Qwen3.5-4B"]:
    #     sub = merged[merged["treatment"] == t]
    #     ax.bar(...)
    # savefig("R04_objective_vs_perceived")
    print("  ⚠ TODO: requires edge_id join between survey and enrichment_results")


# ═════════════════════════════════════════════════════════════════════════════
# R05 — Confidence vs perceived quality (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r05_confidence_vs_perceived(edge_ratings: pd.DataFrame):
    section("R05", "Confidence vs perceived quality — scatter")

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    fig.suptitle("LLM confidence score vs perceived quality", fontweight="bold")

    for ax, dim in zip(axes.flat, DIMENSIONS):
        sub = edge_ratings[edge_ratings["dimension"] == dim].dropna(
            subset=["confidence", "rating"])
        for t in ["GPT-5.1", "Qwen3.5-4B"]:
            tdf = sub[sub["treatment"] == t]
            if tdf.empty:
                continue
            sl, ic, r2 = scatter_reg(ax, tdf["confidence"].values,
                                     tdf["rating"].values, t, jitter=0.02)
            print(f"  {DIM_LABELS[dim]} – {t}: slope={sl:.3f} R²={r2:.3f}")
        ax.set_xlabel("LLM confidence score (0–1)")
        ax.set_ylabel("Perceived rating (1–4)")
        ax.set_title(DIM_LABELS[dim], fontweight="bold")
        ax.set_yticks([1, 2, 3, 4])
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.3)

    plt.tight_layout()
    savefig("R05_confidence_vs_perceived")


# ═════════════════════════════════════════════════════════════════════════════
# R06 — Confidence vs objective correctness (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r06_confidence_vs_objective(scale_data: dict):
    section("R06", "Confidence vs objective correctness — scatter")
    # Proxy: use valid_edges from enrichment_log_results as objective quality signal
    # confidence is per-edge from question_mapping; for scalability runs, only
    # aggregate counts are available → this plot is best generated from the
    # simulation run logs where confidence + valid_edges are on the same row.

    fig, ax = plt.subplots(figsize=(7, 5))
    for model in LLM_MODELS:  # scale_data only has LLM models
        logs = scale_data[model].get("logs")
        if logs is None or "valid_edges" not in logs.columns:
            continue
        # TODO: if your log CSV has a confidence column per row, use it here.
        # Currently leaving as a placeholder awaiting per-run confidence column.
        print(f"  ⚠ {model}: confidence column not yet in log CSV — add to enrichment_log_results")

    ax.set_xlabel("LLM confidence score (0–1)")
    ax.set_ylabel("Valid edges produced")
    ax.set_title("LLM confidence vs objective edge quality", fontweight="bold")
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R06_confidence_vs_objective")


# ═════════════════════════════════════════════════════════════════════════════
# R07 — Graph preference ranking (stacked bar)
# ═════════════════════════════════════════════════════════════════════════════

def r07_graph_ranking(rankings: pd.DataFrame):
    section("R07", "Graph preference ranking — stacked bar")

    rank_colors = ["#16A34A", "#86EFAC", "#EF4444"]
    rank_labels = ["1st (best)", "2nd", "3rd (worst)"]

    data = {}
    for t in TREATMENTS:
        sub  = rankings[rankings["treatment"] == t]["rank"].dropna()
        data[t] = [int((sub == v).sum()) for v in [1, 2, 3]]
        describe(rankings[rankings["treatment"] == t]["rank"], t)

    x      = np.arange(len(TREATMENTS))
    lefts  = np.zeros(len(TREATMENTS))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for i in range(3):
        vals   = np.array([data[t][i] for t in TREATMENTS], dtype=float)
        totals = np.array([sum(data[t]) for t in TREATMENTS], dtype=float)
        pcts   = np.where(totals > 0, vals / totals * 100, 0)
        bars   = ax.bar(x, pcts, bottom=lefts, color=rank_colors[i],
                        edgecolor="white", label=rank_labels[i])
        for bar, cnt in zip(bars, vals):
            if cnt > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{int(cnt)}", ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold")
        lefts += pcts

    ax.set_xticks(x)
    ax.set_xticklabels(TREATMENTS, rotation=10, ha="right")
    ax.set_ylabel("% of participants")
    ax.set_ylim(0, 105)
    ax.set_title("Graph preference ranking per treatment", fontweight="bold")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R07_graph_ranking")

    # Exploratory tests
    friedman_test({t: rankings[rankings["treatment"] == t]["rank"] for t in TREATMENTS},
                  "ranking")
    for t1, t2 in combinations(TREATMENTS, 2):
        wilcoxon_pair(rankings[rankings["treatment"] == t1]["rank"],
                      rankings[rankings["treatment"] == t2]["rank"],
                      f"{t1} vs {t2}")


# ═════════════════════════════════════════════════════════════════════════════
# R08 — Open responses (theme table)
# ═════════════════════════════════════════════════════════════════════════════

def r08_open_responses(survey_raw: pd.DataFrame):
    section("R08", "Open responses — theme table (console)")
    open_cols = [c for c in survey_raw.columns if c.startswith("open")]
    if not open_cols:
        print("  No open response columns found.")
        return
    for col in open_cols:
        flow = col.replace("open", "")
        print(f"\n  Flow {flow} open responses:")
        for i, val in enumerate(survey_raw[col].dropna(), 1):
            val = str(val).strip()
            if val:
                print(f"    [{i}] {val}")
    print("\n  ⚠ Manual thematic coding required — see open responses above.")


# ═════════════════════════════════════════════════════════════════════════════
# R09 — DIR helpfulness (diverging stacked Likert)
# R10 — DIR completeness (diverging stacked Likert)
# ═════════════════════════════════════════════════════════════════════════════

def r09_r10_dir_ratings(graph_ratings: pd.DataFrame):
    section("R09/R10", "DIR helpfulness & completeness — diverging stacked Likert")

    scale_lbl = ["1 – Not useful at all", "2 – Somewhat useful",
                  "3 – Useful", "4 – Very useful"]

    for gdim, rid, title in [
        ("usefulness",   "R09", "DIR helpfulness"),
        ("completeness", "R10", "DIR completeness"),
    ]:
        data = {}
        for t in TREATMENTS:
            sub = graph_ratings[(graph_ratings["graph_dim"] == gdim) &
                                (graph_ratings["treatment"] == t)]["rating"]
            describe(sub, t)
            data[t] = count_likert(sub)
        diverging_likert(data, title=title, name=f"{rid}_{gdim}",
                         scale_labels=scale_lbl)

    # Exploratory tests
    for gdim in ["usefulness", "completeness"]:
        groups = {t: graph_ratings[(graph_ratings["graph_dim"] == gdim) &
                                   (graph_ratings["treatment"] == t)]["rating"]
                  for t in TREATMENTS}
        friedman_test(groups, gdim)
        for t1, t2 in combinations(TREATMENTS, 2):
            wilcoxon_pair(groups[t1], groups[t2], f"{gdim}: {t1} vs {t2}")


# ═════════════════════════════════════════════════════════════════════════════
# R11 — Runtime breakdown (stacked bar)
# ═════════════════════════════════════════════════════════════════════════════

def r11_runtime_breakdown(sim_data: dict):
    section("R11", "Runtime breakdown — stacked bar chart")

    components = {
        "Window retrieval":        ("enrichment", "neo4j_retrieval_time_window"),
        "Neighbourhood retrieval": ("enrichment", "neo4j_retrieval_time_neighbourhood"),
        "Vector retrieval":        ("enrichment", "neo4j_retrieval_time_vector"),
        "LLM generation":          ("enrichment", "llm_generation_time"),
        "LLM insertion":           ("enrichment", "llm_insertion_time"),
    }
    comp_colors = ["#6366F1", "#0EA5E9", "#10B981", "#F59E0B", "#DC2626"]

    means = {model: {} for model in MODELS}
    for model in MODELS:
        for label, (src, col) in components.items():
            df = sim_data[model].get(src)
            means[model][label] = df[col].mean() * 1000 if (df is not None and col in df.columns) else 0

    x      = np.arange(len(MODELS))
    width  = 0.5
    fig, ax = plt.subplots(figsize=(7, 5))
    bottoms = np.zeros(len(MODELS))
    for (label, _), color in zip(components.items(), comp_colors):
        vals = np.array([means[m][label] for m in MODELS])
        ax.bar(x, vals, width, bottom=bottoms, color=color,
               edgecolor="white", label=label)
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Mean time per enrichment (ms)")
    ax.set_title("Runtime breakdown per enrichment event", fontweight="bold")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11_runtime_breakdown")

    print("\n  Mean times (ms):")
    for model in MODELS:
        total = sum(means[model].values())
        print(f"\n  {model}  (total ≈ {total:.1f} ms)")
        for label, v in means[model].items():
            pct = f"{v/total*100:.1f}%" if total > 0 else "n/a"
            print(f"    {label:<28}: {v:.1f} ms  ({pct})")


# ═════════════════════════════════════════════════════════════════════════════
# R11b — Simulation results: runtime, graph growth, hardware, scatter plots
# ═════════════════════════════════════════════════════════════════════════════

def _elapsed_seconds(df: "pd.DataFrame") -> "pd.Series":
    """Return elapsed seconds from the first timestamp in df."""
    ts = pd.to_datetime(df["timestamp"], errors="coerce")
    return (ts - ts.iloc[0]).dt.total_seconds()


def _sim_desc_table(sim_data: dict, col: str, label: str, unit: str = "",
                    unit_mult: float = 1.0) -> "pd.DataFrame":
    """Print and return a descriptive stats table across all three treatments."""
    rows = []
    for model in MODELS:
        src = "hardware" if col in ["Total_Host_CPU_%", "Total_Host_Mem_MB"] else "enrichment"
        df  = sim_data[model].get(src)
        if df is None or col not in df.columns:
            continue
        s = df[col].dropna() * unit_mult
        rows.append({
            "Treatment": model,
            "n":      len(s),
            "Mean":   round(s.mean(), 3),
            "Median": round(s.median(), 3),
            "SD":     round(s.std(), 3),
            "Min":    round(s.min(), 3),
            "Max":    round(s.max(), 3),
        })
    tbl = pd.DataFrame(rows).set_index("Treatment")
    u   = f" ({unit})" if unit else ""
    print(f"\n  {label}{u}:")
    print(tbl.to_string())
    tbl.to_csv(FIGURES_DIR / f"R11b_table_{label.replace(' ','_').replace('/','_')}.csv")
    return tbl


def r11b_simulation_analysis(sim_data: dict):
    section("R11b", "Simulation analysis — runtime, graph growth, hardware, scatter plots")

    # ── 1. Stacked bar: retrieval + generation + insertion time per treatment ─
    section("R11b-1", "Runtime overhead stacked bar (simulation)")

    RUNTIME_COMPS = [
        ("neo4j_retrieval_time_window",        "Window retrieval",        "#6366F1"),
        ("neo4j_retrieval_time_neighbourhood", "Neighbourhood retrieval", "#0EA5E9"),
        ("neo4j_retrieval_time_vector",        "Vector retrieval",        "#10B981"),
        ("llm_generation_time",                "LLM generation",          "#F59E0B"),
        ("llm_insertion_time",                 "LLM insertion",           "#DC2626"),
    ]

    means_rt = {}
    for model in MODELS:
        enr = sim_data[model].get("enrichment")
        means_rt[model] = {}
        for col, label, _ in RUNTIME_COMPS:
            if enr is not None and col in enr.columns:
                means_rt[model][label] = enr[col].mean() * 1000
            else:
                means_rt[model][label] = 0.0

    fig, ax = plt.subplots(figsize=(9, 5))
    x       = np.arange(len(MODELS))
    bottoms = np.zeros(len(MODELS))
    for col, label, color in RUNTIME_COMPS:
        vals = np.array([means_rt[m][label] for m in MODELS])
        bars = ax.bar(x, vals, 0.5, bottom=bottoms, color=color,
                      edgecolor="white", linewidth=0.5, label=label)
        for bar, v in zip(bars, vals):
            if v > 5:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{v:.0f}", ha="center", va="center",
                        fontsize=7.5, color="white", fontweight="bold")
        bottoms += vals

    # Total labels on top
    for i, model in enumerate(MODELS):
        total = sum(means_rt[model].values())
        ax.text(i, total + 2, f"{total:.0f} ms", ha="center", va="bottom",
                fontsize=8, fontweight="bold", color="#1F2937")

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS, rotation=10, ha="right")
    ax.set_ylabel("Mean time per event (ms)")
    ax.set_title("Runtime overhead per enrichment event — simulation", fontweight="bold")
    ax.legend(bbox_to_anchor=(1.01, 1), loc="upper left", fontsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11b_1_runtime_stacked")

    # Descriptive table
    for col, label, _ in RUNTIME_COMPS:
        _sim_desc_table(sim_data, col, label, unit="ms", unit_mult=1000)

    # ── 2. Line chart: graph edges over time ──────────────────────────────────
    section("R11b-2", "Graph edge growth over time (simulation)")

    fig, ax = plt.subplots(figsize=(10, 5))
    for model in MODELS:
        kg = sim_data[model].get("kg")
        if kg is None or "graph_edges" not in kg.columns or "timestamp" not in kg.columns:
            continue
        elapsed = _elapsed_seconds(kg)
        edges   = kg["graph_edges"].values
        ax.plot(elapsed, edges, color=COLORS[model], linewidth=2,
                label=model, marker=MARKERS.get(model, "o"), markersize=4,
                markevery=max(1, len(elapsed)//20))
        # Final value annotation
        ax.annotate(f"{int(edges[-1])} edges",
                    xy=(elapsed.iloc[-1], edges[-1]),
                    xytext=(elapsed.iloc[-1] - elapsed.iloc[-1] * 0.05, edges[-1] + edges.max() * 0.03),
                    fontsize=8, color=COLORS[model], fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=COLORS[model], lw=0.8))

    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Total edges in graph")
    ax.set_title("Graph edge growth over elapsed time — simulation", fontweight="bold")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11b_2_graph_edge_growth")

    # Also nodes
    fig, ax = plt.subplots(figsize=(10, 5))
    for model in MODELS:
        kg = sim_data[model].get("kg")
        if kg is None or "graph_nodes" not in kg.columns or "timestamp" not in kg.columns:
            continue
        elapsed = _elapsed_seconds(kg)
        nodes   = kg["graph_nodes"].values
        ax.plot(elapsed, nodes, color=COLORS[model], linewidth=2,
                label=model, marker=MARKERS.get(model, "o"), markersize=4,
                markevery=max(1, len(elapsed)//20))
        ax.annotate(f"{int(nodes[-1])} nodes",
                    xy=(elapsed.iloc[-1], nodes[-1]),
                    xytext=(elapsed.iloc[-1] - elapsed.iloc[-1] * 0.05, nodes[-1] + nodes.max() * 0.03),
                    fontsize=8, color=COLORS[model], fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=COLORS[model], lw=0.8))

    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Total nodes in graph")
    ax.set_title("Graph node growth over elapsed time — simulation", fontweight="bold")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11b_2b_graph_node_growth")

    # Final counts table
    print("\n  Final graph counts per treatment:")
    rows_gc = []
    for model in MODELS:
        kg = sim_data[model].get("kg")
        if kg is None:
            continue
        rows_gc.append({
            "Treatment":    model,
            "Final nodes":  int(kg["graph_nodes"].iloc[-1]) if "graph_nodes" in kg.columns else "n/a",
            "Final edges":  int(kg["graph_edges"].iloc[-1]) if "graph_edges" in kg.columns else "n/a",
            "Duration (s)": round(_elapsed_seconds(kg).iloc[-1], 1) if "timestamp" in kg.columns else "n/a",
        })
    tbl_gc = pd.DataFrame(rows_gc).set_index("Treatment")
    print(tbl_gc.to_string())
    tbl_gc.to_csv(FIGURES_DIR / "R11b_table_graph_final_counts.csv")

    # ── 3. CPU usage over time ────────────────────────────────────────────────
    section("R11b-3", "CPU usage over elapsed time (simulation)")

    fig, ax = plt.subplots(figsize=(11, 5))
    for model in MODELS:
        hw = sim_data[model].get("hardware")
        if hw is None or "Total_Host_CPU_%" not in hw.columns or "timestamp" not in hw.columns:
            continue
        elapsed = _elapsed_seconds(hw)
        cpu     = hw["Total_Host_CPU_%"].values
        ax.plot(elapsed, cpu, color=COLORS[model], linewidth=1.5,
                label=model, alpha=0.85)

    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Total host CPU (%)")
    ax.set_title("CPU usage over elapsed time — simulation", fontweight="bold")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11b_3_cpu_over_time")

    _sim_desc_table(sim_data, "Total_Host_CPU_%", "Total Host CPU", unit="%")

    # ── 4. Memory usage over time ─────────────────────────────────────────────
    section("R11b-4", "Memory usage over elapsed time (simulation)")

    fig, ax = plt.subplots(figsize=(11, 5))
    for model in MODELS:
        hw = sim_data[model].get("hardware")
        if hw is None or "Total_Host_Mem_MB" not in hw.columns or "timestamp" not in hw.columns:
            continue
        elapsed = _elapsed_seconds(hw)
        mem     = hw["Total_Host_Mem_MB"].values
        ax.plot(elapsed, mem, color=COLORS[model], linewidth=1.5,
                label=model, alpha=0.85)

    ax.set_xlabel("Elapsed time (s)")
    ax.set_ylabel("Total host memory (MB)")
    ax.set_title("Memory usage over elapsed time — simulation", fontweight="bold")
    ax.legend()
    ax.grid(linestyle="--", alpha=0.35)
    plt.tight_layout()
    savefig("R11b_4_memory_over_time")

    _sim_desc_table(sim_data, "Total_Host_Mem_MB", "Total Host Memory", unit="MB")

    # ── 5. Scatter plots: graph nodes vs retrieval / generation / insertion ───
    section("R11b-5", "Graph nodes vs timing — scatter plots (simulation)")

    # 5a. LLM-model metrics from log_run_results (enrichment source)
    SCATTER_METRICS_ENR = [
        ("neo4j_retrieval_time_window",        "Window retrieval time",        "ms", 1000),
        ("neo4j_retrieval_time_neighbourhood", "Neighbourhood retrieval time", "ms", 1000),
        ("neo4j_retrieval_time_vector",        "Vector retrieval time",        "ms", 1000),
        ("llm_generation_time",                "LLM generation time",          "s",  1),
    ]

    for col, label, unit, mult in SCATTER_METRICS_ENR:
        fig, ax = plt.subplots(figsize=(8, 5))
        for model in LLM_MODELS:   # only GPT and Qwen have these columns
            enr = sim_data[model].get("enrichment")
            kg  = sim_data[model].get("kg")
            if enr is None or kg is None:
                continue
            if col not in enr.columns or "graph_nodes" not in kg.columns:
                continue
            n   = min(len(enr), len(kg))
            x_v = kg["graph_nodes"].iloc[:n].values.astype(float)
            y_v = enr[col].iloc[:n].dropna().values.astype(float) * mult
            n   = min(len(x_v), len(y_v))
            ax.scatter(x_v[:n], y_v[:n], color=COLORS[model], alpha=0.45,
                       s=28, marker=MARKERS.get(model, "o"), label=model)
            sl, ic, r2 = regression(x_v[:n], y_v[:n])
            xr = np.linspace(x_v.min(), x_v.max(), 200)
            ax.plot(xr, sl * xr + ic, color=COLORS[model],
                    linewidth=2, linestyle="--", label=f"{model}  R²={r2:.2f}")
            print(f"  {label} – {model}: slope={sl:.4f}  R²={r2:.3f}")

        # Clip y-axis at 99th percentile across all plotted points
        all_y_5a = ax.collections[0].get_offsets()[:, 1].tolist() if ax.collections else []
        for coll in ax.collections[1:]:
            all_y_5a.extend(coll.get_offsets()[:, 1].tolist())
        if all_y_5a:
            y_ceil_5a    = float(np.percentile(all_y_5a, 99))
            n_clip_5a    = sum(1 for v in all_y_5a if v > y_ceil_5a)
            pct_clip_5a  = n_clip_5a / len(all_y_5a) * 100
            ax.set_ylim(bottom=0, top=y_ceil_5a * 1.05)
            if n_clip_5a > 0:
                ax.annotate(
                    f"{n_clip_5a} outlier{'s' if n_clip_5a > 1 else ''} "
                    f"({pct_clip_5a:.1f}%) above {y_ceil_5a:.2f} {unit} not shown",
                    xy=(0.01, 0.98), xycoords="axes fraction",
                    va="top", ha="left", fontsize=7, color="#6B7280",
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
                )
        ax.set_xlabel("Graph nodes")
        ax.set_ylabel(f"{label} ({unit})")
        ax.set_title(f"Graph nodes vs {label}", fontweight="bold")
        ax.legend(fontsize=8, ncol=2)
        ax.grid(linestyle="--", alpha=0.3)
        plt.tight_layout()
        safe = label.replace(" ", "_").replace("/", "_")
        savefig(f"R11b_5_nodes_vs_{safe}")
        _sim_desc_table(sim_data, col, label, unit=unit, unit_mult=mult)

    # 5b. Insertion times from log_db_results — all three treatments
    section("R11b-5b", "Graph nodes vs insertion time (all treatments, from log_db_results)")

    for ins_col, ins_label in [
        ("insertion_time_edges", "Edge insertion time"),
        ("insertion_time_nodes", "Node insertion time"),
    ]:
        CLIP_PCT = 99   # clip y-axis at this percentile to suppress outliers

        # Collect all y values across treatments to compute a shared clip ceiling
        all_y = []
        plot_data = {}   # {model: (x_v, y_v, n)}
        for model in MODELS:
            kg = sim_data[model].get("kg")
            if kg is None:
                continue
            if ins_col not in kg.columns or "graph_nodes" not in kg.columns:
                print(f"  [SKIP] {ins_col} not in kg for {model} — "
                      f"check log_db_results has this column")
                continue
            x_v = kg["graph_nodes"].dropna().values.astype(float)
            y_v = kg[ins_col].dropna().values.astype(float) * 1000   # → ms
            n   = min(len(x_v), len(y_v))
            plot_data[model] = (x_v[:n], y_v[:n], n)
            all_y.extend(y_v[:n].tolist())

        if not all_y:
            continue

        y_ceil   = float(np.percentile(all_y, CLIP_PCT))
        n_clipped = sum(1 for v in all_y if v > y_ceil)
        pct_clipped = n_clipped / len(all_y) * 100

        fig, ax = plt.subplots(figsize=(8, 5))
        for model, (x_v, y_v, n) in plot_data.items():
            ax.scatter(x_v, y_v, color=COLORS[model], alpha=0.45,
                       s=28, marker=MARKERS.get(model, "o"), label=model)
            sl, ic, r2 = regression(x_v, y_v)
            if n >= 3:
                xr = np.linspace(x_v.min(), x_v.max(), 200)
                ax.plot(xr, sl * xr + ic, color=COLORS[model],
                        linewidth=2, linestyle="--",
                        label=f"{model}  R²={r2:.2f}")
            print(f"  {ins_label} – {model}: slope={sl:.4f}  R²={r2:.3f}")

        ax.set_ylim(bottom=0, top=y_ceil * 1.05)
        ax.set_xlabel("Graph nodes")
        ax.set_ylabel(f"{ins_label} (ms)")
        ax.set_title(f"Graph nodes vs {ins_label} — all treatments",
                     fontweight="bold")
        ax.legend(fontsize=8, ncol=2)
        ax.grid(linestyle="--", alpha=0.3)
        if n_clipped > 0:
            ax.annotate(
                f"{n_clipped} outlier{'s' if n_clipped > 1 else ''} "
                f"({pct_clipped:.1f}%) above {y_ceil:.1f} ms not shown",
                xy=(0.01, 0.98), xycoords="axes fraction",
                va="top", ha="left", fontsize=7, color="#6B7280",
                bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
            )
        plt.tight_layout()
        safe = ins_label.replace(" ", "_")
        savefig(f"R11b_5b_nodes_vs_{safe}")

        # Descriptive table from kg (log_db_results)
        print(f"\n  {ins_label} (ms) — all treatments:")
        rows_ins = []
        for model in MODELS:
            kg = sim_data[model].get("kg")
            if kg is None or ins_col not in kg.columns:
                continue
            s = kg[ins_col].dropna() * 1000
            rows_ins.append({
                "Treatment": model,
                "n":      len(s),
                "Mean":   round(s.mean(), 3),
                "Median": round(s.median(), 3),
                "SD":     round(s.std(), 3),
                "Min":    round(s.min(), 3),
                "Max":    round(s.max(), 3),
            })
        if rows_ins:
            tbl_ins = pd.DataFrame(rows_ins).set_index("Treatment")
            print(tbl_ins.to_string())
            tbl_ins.to_csv(
                FIGURES_DIR / f"R11b_table_{safe}.csv"
            )

# ═════════════════════════════════════════════════════════════════════════════
# R11b-5c — Graph neighbourhood nodes vs valid edges inserted (simulation)
# ═════════════════════════════════════════════════════════════════════════════

def r11b_5c_nodes_vs_valid_edges(sim_data: dict):
    section("R11b-5c", "Graph neighbourhood nodes vs cumulative valid edges inserted (simulation)")

    X_COL = "graph_nodes_neighbourhood"   # neighbourhood context size as graph size proxy
    Y_COL = "llm_correct_generated_edges"

    all_y = []
    plot_data = {}

    for model in MODELS:
        enr = sim_data[model].get("enrichment")
        if enr is None:
            continue
        if X_COL not in enr.columns or Y_COL not in enr.columns:
            print(f"  [SKIP] {model}: missing {X_COL} or {Y_COL} in enrichment file")
            continue
        
        # 1. Drop NaNs and immediately sort by graph size to ensure chronological/size progression
        valid = enr[[X_COL, Y_COL]].dropna().sort_values(by=X_COL)
        if valid.empty:
            continue
        
        x_v = valid[X_COL].values.astype(float)
        
        # 2. Key Fix: Calculate the cumulative sum so the line increases as the graph size grows
        y_v = valid[Y_COL].cumsum().values.astype(float)
        
        plot_data[model] = (x_v, y_v)
        all_y.extend(y_v.tolist())

    if not plot_data:
        print("  [SKIP] No data available for this plot.")
        return

    # 99th-percentile y clip (Note: Since this is cumulative, your max y will be much higher now)
    y_ceil     = float(np.percentile(all_y, 99)) if all_y else None
    n_clipped  = sum(1 for v in all_y if y_ceil and v > y_ceil)
    pct_clipped = n_clipped / len(all_y) * 100 if all_y else 0

    fig, ax = plt.subplots(figsize=(8, 5))
    for model, (x_v, y_v) in plot_data.items():
        # Scatter plot now shows the step-by-step accumulation points
        ax.scatter(x_v, y_v, color=COLORS[model], alpha=0.45,
                   s=30, marker=MARKERS.get(model, "o"), label=model)
        sl, ic, r2 = regression(x_v, y_v)
        if len(x_v) >= 3:
            xr = np.linspace(x_v.min(), x_v.max(), 200)
            ax.plot(xr, sl * xr + ic, color=COLORS[model],
                    linewidth=2, linestyle="--",
                    label=f"{model}  R²={r2:.2f}")
        print(f"  {model}: slope={sl:.4f}  R²={r2:.3f}")

    if y_ceil is not None:
        ax.set_ylim(bottom=0, top=y_ceil * 1.05)
    if n_clipped > 0:
        ax.annotate(
            f"{n_clipped} outlier{'s' if n_clipped > 1 else ''} "
            f"({pct_clipped:.1f}%) above {y_ceil:.1f} edges not shown",
            xy=(0.01, 0.98), xycoords="axes fraction",
            va="top", ha="left", fontsize=7, color="#6B7280",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
        )

    ax.set_xlabel("Neighbourhood nodes (graph size proxy)")
    # Label updated to accurately describe the new cumulative behavior
    ax.set_ylabel("Cumulative valid edges inserted")
    ax.set_title("Graph size vs cumulative valid edges inserted — simulation", fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R11b_5c_neighbourhood_nodes_vs_valid_edges")

    # ── Descriptive table (Kept intact to look at raw, non-cumulative summary metrics) ──────
    print(f"\n  Valid edges inserted (llm_correct_generated_edges) per treatment:")
    rows = []
    for model in MODELS:
        enr = sim_data[model].get("enrichment")
        if enr is None or Y_COL not in enr.columns:
            continue
        s = enr[Y_COL].dropna()
        rows.append({
            "Treatment": model,
            "n":         len(s),
            "Mean":      round(s.mean(), 3),
            "Median":    round(s.median(), 3),
            "SD":        round(s.std(), 3),
            "Min":       round(s.min(), 3),
            "Max":       round(s.max(), 3),
            "Total":     int(s.sum()),
        })
    if rows:
        tbl = pd.DataFrame(rows).set_index("Treatment")
        print(tbl.to_string())
        tbl.to_csv(FIGURES_DIR / "R11b_table_valid_edges_inserted.csv")

    # ── Also table for neighbourhood nodes (x-axis) ───────────────────────────
    print(f"\n  Neighbourhood nodes (graph_nodes_neighbourhood) per treatment:")
    rows_x = []
    for model in MODELS:
        enr = sim_data[model].get("enrichment")
        if enr is None or X_COL not in enr.columns:
            continue
        s = enr[X_COL].dropna()
        rows_x.append({
            "Treatment": model,
            "n":         len(s),
            "Mean":      round(s.mean(), 3),
            "Median":    round(s.median(), 3),
            "SD":        round(s.std(), 3),
            "Min":       round(s.min(), 3),
            "Max":       round(s.max(), 3),
        })
    if rows_x:
        tbl_x = pd.DataFrame(rows_x).set_index("Treatment")
        print(tbl_x.to_string())
        tbl_x.to_csv(FIGURES_DIR / "R11b_table_neighbourhood_nodes.csv")



# ═════════════════════════════════════════════════════════════════════════════
# SQ3_SCALE — Scalability analysis results (GPT-5.1 vs Qwen3.5-4B)
# ═════════════════════════════════════════════════════════════════════════════

def _scale_desc(scale_data: dict, src: str, col: str, label: str,
                unit: str = "", mult: float = 1.0) -> "pd.DataFrame":
    """Descriptive table per model across all milestones for a scalability metric."""
    rows = []
    for model in LLM_MODELS:
        df = scale_data[model].get(src)
        if df is None or col not in df.columns:
            continue
        s = df[col].dropna() * mult
        rows.append({
            "Model": model, "n": len(s),
            "Mean": round(s.mean(), 3), "Median": round(s.median(), 3),
            "SD": round(s.std(), 3), "Min": round(s.min(), 3), "Max": round(s.max(), 3),
        })
    tbl = pd.DataFrame(rows).set_index("Model")
    u   = f" ({unit})" if unit else ""
    print(f"\n  {label}{u}:")
    print(tbl.to_string())
    safe = label.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    tbl.to_csv(FIGURES_DIR / f"SQ3_table_{safe}.csv")
    return tbl


def _scale_desc_milestone(scale_data: dict, src: str, col: str, label: str,
                           unit: str = "", mult: float = 1.0):
    """Descriptive table split by model AND milestone."""
    print(f"\n  {label}{' (' + unit + ')' if unit else ''} — by milestone:")
    rows = []
    for model in LLM_MODELS:
        df = scale_data[model].get(src)
        if df is None or col not in df.columns or "milestone" not in df.columns:
            continue
        for ms in SCALE_LABELS:
            s = df[df["milestone"] == ms][col].dropna() * mult
            if s.empty:
                continue
            rows.append({
                "Model": model, "Milestone": ms, "n": len(s),
                "Mean": round(s.mean(), 3), "Median": round(s.median(), 3),
                "SD": round(s.std(), 3), "Min": round(s.min(), 3), "Max": round(s.max(), 3),
            })
    tbl = pd.DataFrame(rows).set_index(["Model", "Milestone"])
    print(tbl.to_string())
    safe = label.replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
    tbl.to_csv(FIGURES_DIR / f"SQ3_table_{safe}_by_milestone.csv")
    return tbl


def _clip_ax(ax, pct: int = 99, unit: str = ""):
    """Clip y-axis at percentile, annotate clipped count."""
    y_data = []
    for coll in ax.collections:
        offsets = coll.get_offsets()
        if len(offsets):
            y_data.extend(offsets[:, 1].tolist())
    if not y_data:
        return
    ceil    = float(np.percentile(y_data, pct))
    n_clip  = sum(1 for v in y_data if v > ceil)
    pct_c   = n_clip / len(y_data) * 100
    ax.set_ylim(bottom=0, top=ceil * 1.05)
    if n_clip > 0:
        ax.annotate(
            f"{n_clip} outlier{'s' if n_clip > 1 else ''} ({pct_c:.1f}%) "
            f"above {ceil:.2f}{' ' + unit if unit else ''} not shown",
            xy=(0.01, 0.98), xycoords="axes fraction",
            va="top", ha="left", fontsize=7, color="#6B7280",
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7),
        )


def _line_milestone_multi(ax, scale_data: dict, src: str,
                          cols: list[tuple[str, str, str]],
                          model: str, unit: float = 1):
    """
    Multi-line chart for one model: one line per (col, label, linestyle).
    x = milestone index, y = mean per milestone.
    """
    x = SCALE_NODECOUNTS
    df = scale_data[model].get(src)
    for col, label, ls in cols:
        if df is None or col not in df.columns:
            continue
        means = [df[df["milestone"] == ms][col].mean() * unit for ms in SCALE_LABELS]
        sds   = [df[df["milestone"] == ms][col].std()  * unit for ms in SCALE_LABELS]
        ax.plot(x, means, ls, marker="o", linewidth=2, label=label)
        ax.fill_between(x,
                        np.array(means) - np.array(sds),
                        np.array(means) + np.array(sds), alpha=0.12)
    ax.set_xticks(x)
    ax.set_xticklabels(SCALE_LABELS, rotation=15, ha="right")
    ax.grid(linestyle="--", alpha=0.35)
    ax.legend(fontsize=8)


def _scatter_scale(ax, scale_data: dict, src: str,
                   x_col: str, y_col: str,
                   model: str, x_mult: float = 1, y_mult: float = 1):
    """Scatter + regression for one model on a pre-created axis."""
    df = scale_data[model].get(src)
    if df is None or x_col not in df.columns or y_col not in df.columns:
        return None
    valid = df[[x_col, y_col]].dropna()
    x_v   = valid[x_col].values.astype(float) * x_mult
    y_v   = valid[y_col].values.astype(float) * y_mult
    ax.scatter(x_v, y_v, color=COLORS[model], alpha=0.4,
               s=25, marker=MARKERS.get(model, "o"), label=model)
    sl, ic, r2 = regression(x_v, y_v)
    if len(x_v) >= 3:
        xr = np.linspace(x_v.min(), x_v.max(), 200)
        ax.plot(xr, sl * xr + ic, color=COLORS[model],
                linewidth=2, linestyle="--", label=f"{model}  R²={r2:.2f}")
    return sl, ic, r2


def sq3_scalability_analysis(scale_data: dict):
    section("SQ3_SCALE", "Scalability analysis — GPT-5.1 vs Qwen3.5-4B")

    # ── 1. Graph size vs generation time ─────────────────────────────────────
    section("SQ3-1", "Graph size vs generation time")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("Graph size vs LLM generation time", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        line_milestone_event(ax, {model: scale_data[model]},
                             "llm_generation_time", "enrichment")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Generation time (s)")
    plt.tight_layout()
    savefig("SQ3_1_graphsize_vs_gentime")
    _scale_desc_milestone(scale_data, "enrichment", "llm_generation_time",
                          "Generation time", "s")

    # ── 2. Graph size vs retrieval time (3 strategies, models separate) ───────
    section("SQ3-2", "Graph size vs retrieval time")
    RETRIEVAL_COLS = [
        ("neo4j_retrieval_time_window",        "Window",        "-"),
        ("neo4j_retrieval_time_neighbourhood", "Neighbourhood", "--"),
        ("neo4j_retrieval_time_vector",        "Vector",        ":"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("Graph size vs retrieval time (ms)", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        _line_milestone_multi(ax, scale_data, "enrichment",
                              [(c, l, ls) for c, l, ls in RETRIEVAL_COLS],
                              model, unit=1000)
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Retrieval time (ms)")
    plt.tight_layout()
    savefig("SQ3_2_graphsize_vs_retrieval_time")
    for col, label, _ in RETRIEVAL_COLS:
        _scale_desc_milestone(scale_data, "enrichment", col,
                              f"Retrieval time {label}", "ms", mult=1000)

    # ── 3. Graph size vs retrieved nodes (3 strategies, models separate) ──────
    section("SQ3-3", "Graph size vs retrieved nodes")
    NODE_COLS = [
        ("window_nodes",        "Window",        "-"),
        ("neighbourhood_nodes", "Neighbourhood", "--"),
        ("vector_nodes",        "Vector",        ":"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("Graph size vs retrieved nodes", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        _line_milestone_multi(ax, scale_data, "logs",
                              [(c, l, ls) for c, l, ls in NODE_COLS],
                              model)
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Nodes retrieved")
    plt.tight_layout()
    savefig("SQ3_3_graphsize_vs_retrieved_nodes")
    for col, label, _ in NODE_COLS:
        _scale_desc_milestone(scale_data, "logs", col,
                              f"Retrieved nodes {label}")

    # ── 4. Graph size vs valid edges ──────────────────────────────────────────
    section("SQ3-4", "Graph size vs valid edges")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("Graph size vs valid edges inserted", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        line_milestone_event(ax, {model: scale_data[model]},
                             "llm_correct_generated_edges", "enrichment")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Valid edges per enrichment")
    plt.tight_layout()
    savefig("SQ3_4_graphsize_vs_valid_edges")
    _scale_desc_milestone(scale_data, "enrichment", "llm_correct_generated_edges",
                          "Valid edges")

    # ── 5. Graph size vs prompt tokens ────────────────────────────────────────
    section("SQ3-5", "Graph size vs prompt tokens")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("Graph size vs prompt tokens (input)", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        line_milestone_event(ax, {model: scale_data[model]},
                             "prompt_tokens", "logs")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Prompt tokens")
    plt.tight_layout()
    savefig("SQ3_5_graphsize_vs_prompt_tokens")
    _scale_desc_milestone(scale_data, "logs", "prompt_tokens", "Prompt tokens")

    # ── 6. Graph size vs HTTP responses (bar chart per milestone) ─────────────
    section("SQ3-6", "Graph size vs HTTP responses — bar chart")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("HTTP response distribution per milestone", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        df = scale_data[model].get("logs")
        if df is None or "HTTP_response" not in df.columns:
            ax.set_title(f"{model} (no data)", fontweight="bold")
            continue
        # Extract numeric status code
        codes = df["HTTP_response"].astype(str).str.extract(r"(\d{3})")[0]
        df    = df.copy()
        df["status"] = pd.to_numeric(codes, errors="coerce")
        # Group by milestone and status
        summary = (df.groupby(["milestone", "status"])
                     .size().unstack(fill_value=0)
                     .reindex(SCALE_LABELS))
        x      = np.arange(len(SCALE_LABELS))
        width  = 0.35
        status_colors = {200.0: "#16A34A", 500.0: "#EF4444",
                         400.0: "#F97316", 503.0: "#6366F1"}
        bottoms = np.zeros(len(SCALE_LABELS))
        for status_code in sorted(summary.columns):
            vals  = summary[status_code].fillna(0).values.astype(float)
            color = status_colors.get(float(status_code), "#9CA3AF")
            bars  = ax.bar(x, vals, width * 2, bottom=bottoms,
                           color=color, edgecolor="white", linewidth=0.5,
                           label=f"HTTP {int(status_code)}")
            for bar, v in zip(bars, vals):
                if v > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2,
                            bar.get_y() + bar.get_height() / 2,
                            f"{int(v)}", ha="center", va="center",
                            fontsize=8, color="white", fontweight="bold")
            bottoms += vals
        ax.set_xticks(x)
        ax.set_xticklabels(SCALE_LABELS, rotation=15, ha="right")
        ax.set_ylabel("Count")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(axis="y", linestyle="--", alpha=0.3)

        # Console summary
        print(f"\n  {model} HTTP responses:")
        print(summary.to_string())
        summary.to_csv(FIGURES_DIR / f"SQ3_table_http_{model.replace('.','').replace(' ','_').replace('-','')}.csv")

    plt.tight_layout()
    savefig("SQ3_6_http_responses_by_milestone")

    # ── 7. Prompt tokens vs generation time — one subplot per model ─────────────
    section("SQ3-7", "Prompt tokens vs generation time — scatter (per model)")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("Prompt tokens vs generation time", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        res = _scatter_scale(ax, scale_data, "logs",
                             "prompt_tokens", "generation_time", model)
        if res:
            sl, ic, r2 = res
            print(f"  {model}: slope={sl:.4f}  R²={r2:.3f}")
        ax.set_xlabel("Prompt tokens")
        ax.set_ylabel("Generation time (s)")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("SQ3_7_prompt_tokens_vs_gentime")
    _scale_desc(scale_data, "logs", "prompt_tokens", "Prompt tokens")
    _scale_desc(scale_data, "logs", "generation_time", "Generation time", "s")

    # ── 8. Prompt tokens vs output tokens (scatter) ───────────────────────────
    section("SQ3-8", "Prompt tokens vs output tokens — scatter")
    fig, ax = plt.subplots(figsize=(8, 5))
    for model in LLM_MODELS:
        res = _scatter_scale(ax, scale_data, "logs",
                             "prompt_tokens", "output_tokens", model)
        if res:
            sl, ic, r2 = res
            print(f"  {model}: slope={sl:.4f}  R²={r2:.3f}")
    ax.set_xlabel("Prompt tokens")
    ax.set_ylabel("Output tokens")
    ax.set_title("Prompt tokens vs output tokens", fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("SQ3_8_prompt_tokens_vs_output_tokens")
    _scale_desc(scale_data, "logs", "output_tokens", "Output tokens")

    # ── 9. Retrieved nodes vs generation time — one subplot per model ────────
    section("SQ3-9", "Retrieved nodes (total) vs generation time — scatter (per model)")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("Total retrieved nodes vs generation time", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        logs = scale_data[model].get("logs")
        if logs is None:
            continue
        ctx_cols = ["window_nodes", "neighbourhood_nodes", "vector_nodes"]
        present  = [c for c in ctx_cols if c in logs.columns]
        if not present or "generation_time" not in logs.columns:
            print(f"  [SKIP] {model}: missing node cols or generation_time in logs")
            continue
        logs = logs.copy()
        logs["_total_ctx"] = logs[present].sum(axis=1)
        res = _scatter_scale(ax, {model: {"logs": logs}},
                             "logs", "_total_ctx", "generation_time", model)
        if res:
            sl, ic, r2 = res
            print(f"  {model}: slope={sl:.4f}  R²={r2:.3f}")
        ax.set_xlabel("Total retrieved nodes (window + neighbourhood + vector)")
        ax.set_ylabel("Generation time (s)")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("SQ3_9_retrieved_nodes_vs_gentime")

    # ── 10. Retrieved nodes vs prompt tokens — one subplot per model ──────────
    section("SQ3-10", "Retrieved nodes (total) vs prompt tokens — scatter (per model)")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("Total retrieved nodes vs prompt tokens", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        logs = scale_data[model].get("logs")
        if logs is None:
            continue
        ctx_cols = ["window_nodes", "neighbourhood_nodes", "vector_nodes"]
        present  = [c for c in ctx_cols if c in logs.columns]
        if not present or "prompt_tokens" not in logs.columns:
            print(f"  [SKIP] {model}: missing node cols or prompt_tokens in logs")
            continue
        logs = logs.copy()
        logs["_total_ctx"] = logs[present].sum(axis=1)
        res = _scatter_scale(ax, {model: {"logs": logs}},
                             "logs", "_total_ctx", "prompt_tokens", model)
        if res:
            sl, ic, r2 = res
            print(f"  {model}: slope={sl:.4f}  R²={r2:.3f}")
        ax.set_xlabel("Total retrieved nodes (window + neighbourhood + vector)")
        ax.set_ylabel("Prompt tokens")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("SQ3_10_retrieved_nodes_vs_prompt_tokens")

# ═════════════════════════════════════════════════════════════════════════════
# R12 — Generation time vs graph size (line chart)
# ═════════════════════════════════════════════════════════════════════════════

def r12_generation_time_vs_size(scale_data: dict):
    section("R12", "Generation time vs graph size — line chart (split by event type)")

    # ── Line chart: mean per milestone per model per event type ───────────────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("LLM generation time vs graph size", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        line_milestone_event(ax, {model: scale_data[model]},
                             "llm_generation_time", "enrichment")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Mean generation time (s)")
    plt.tight_layout()
    savefig("R12_generation_time_vs_size")

    # ── Scatter: per-run observations coloured by model, shaped by event ──────
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("LLM generation time vs graph size — per event", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        df = scale_data[model].get("enrichment")
        if df is None:
            continue
        res = scatter_reg_event(ax, df, "node_count", "llm_generation_time",
                                model, jitter_x=80)
        for evt, (sl, ic, r2) in res.items():
            print(f"  {model} – {evt}: slope={sl:.4f} R²={r2:.3f}")
        ax.set_xlabel("Graph size at milestone start (nodes)")
        ax.set_ylabel("Generation time (s)")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.legend(fontsize=7, ncol=2)
        ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R12b_generation_time_scatter_event")

    # ── Descriptive stats per event type ─────────────────────────────────────
    for model in LLM_MODELS:
        df = scale_data[model].get("enrichment")
        if df is None:
            continue
        print(f"\n  {model}:")
        for evt in EVENT_TYPES:
            sub = df[df.get("event", pd.Series()).eq(evt)] if "event" in df.columns else df
            for ms in SCALE_LABELS:
                describe(sub[sub["milestone"] == ms]["llm_generation_time"],
                         f"{evt} – {ms}", indent=6)


# ═════════════════════════════════════════════════════════════════════════════
# R13 — Retrieval time vs graph size (multi-line)
# ═════════════════════════════════════════════════════════════════════════════

def r13_retrieval_time_vs_size(scale_data: dict):
    section("R13", "Retrieval time vs graph size — multi-line chart (split by event type)")

    strategies = [
        ("neo4j_retrieval_time_window",        "Window"),
        ("neo4j_retrieval_time_neighbourhood", "Neighbourhood"),
        ("neo4j_retrieval_time_vector",        "Vector"),
    ]
    strat_ls = ["-", "--", ":"]   # linestyle per strategy (within-event variation)
    x = SCALE_NODECOUNTS

    # One figure per model: strategies as line styles, event types as marker shapes
    for model in LLM_MODELS:
        df = scale_data[model].get("enrichment")
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.set_title(f"Retrieval time vs graph size — {model}", fontweight="bold")

        for (col, strat_label), ls in zip(strategies, strat_ls):
            if df is None or col not in df.columns:
                continue
            ec = "event" if "event" in df.columns else None
            events = df[ec].dropna().unique() if ec else ["all"]
            for evt in (EVENT_TYPES if ec else ["all"]):
                sub   = df[df[ec] == evt] if ec else df
                means = [sub[sub["milestone"] == ms][col].mean() * 1000 for ms in SCALE_LABELS]
                sds   = [sub[sub["milestone"] == ms][col].std()  * 1000 for ms in SCALE_LABELS]
                mk    = EVENT_MARKERS.get(evt, "o")
                ax.plot(x, means, linestyle=ls, marker=mk, linewidth=2,
                        label=f"{strat_label} – {evt}")
                ax.fill_between(x,
                                np.array(means) - np.array(sds),
                                np.array(means) + np.array(sds), alpha=0.10)

        ax.set_xticks(x)
        ax.set_xticklabels(SCALE_LABELS, rotation=15, ha="right")
        ax.set_ylabel("Retrieval time (ms)")
        ax.legend(fontsize=7, ncol=2, bbox_to_anchor=(1.01, 1), loc="upper left")
        ax.grid(linestyle="--", alpha=0.35)
        plt.tight_layout()
        savefig(f"R13_retrieval_time_{model.replace('.', '').replace(' ', '_').replace('-', '')}")


# ═════════════════════════════════════════════════════════════════════════════
# R14 — Retrieved context vs retrieval time (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r14_context_vs_retrieval(scale_data: dict):
    section("R14", "Retrieved context vs retrieval time — scatter")

    strategies = [
        ("graph_nodes_window",        "neo4j_retrieval_time_window",        "Window"),
        ("graph_nodes_neighbourhood", "neo4j_retrieval_time_neighbourhood", "Neighbourhood"),
        ("graph_nodes_vector",        "neo4j_retrieval_time_vector",        "Vector"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    fig.suptitle("Retrieved context size vs retrieval time", fontweight="bold")

    for ax, (nodes_col, time_col, label) in zip(axes, strategies):
        for model in LLM_MODELS:
            df = scale_data[model].get("enrichment")
            if df is None:
                continue
            res = scatter_reg_event(ax, df, nodes_col, time_col, model, unit_y=1000)
            for evt, (sl, ic, r2) in res.items():
                print(f"  {label} – {model} – {evt}: slope={sl:.4f} R²={r2:.3f}")
        ax.set_xlabel("Nodes retrieved")
        ax.set_ylabel("Retrieval time (ms)")
        ax.set_title(label, fontweight="bold")
        ax.legend(fontsize=7, ncol=2)
        ax.grid(linestyle="--", alpha=0.3)

    plt.tight_layout()
    savefig("R14_context_vs_retrieval")


# ═════════════════════════════════════════════════════════════════════════════
# R15 — Retrieved context vs generation time (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r15_context_vs_generation(scale_data: dict):
    section("R15", "Retrieved context vs generation time — scatter")

    fig, ax = plt.subplots(figsize=(7, 5))
    # Use total retrieved nodes (window + neighbourhood + vector) as context proxy
    for model in LLM_MODELS:
        df = scale_data[model].get("enrichment")
        if df is None:
            continue
        ctx_cols = ["graph_nodes_window", "graph_nodes_neighbourhood", "graph_nodes_vector"]
        present  = [c for c in ctx_cols if c in df.columns]
        if not present:
            continue
        df = df.copy()
        df["_total_ctx"] = df[present].sum(axis=1)
        res = scatter_reg_event(ax, df, "_total_ctx", "llm_generation_time", model)
        for evt, (sl, ic, r2) in res.items():
            print(f"  {model} – {evt}: slope={sl:.4f} R²={r2:.3f}")

    ax.set_xlabel("Total nodes retrieved (window + neighbourhood + vector)")
    ax.set_ylabel("LLM generation time (s)")
    ax.set_title("Retrieved context size vs generation time", fontweight="bold")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R15_context_vs_generation")


# ═════════════════════════════════════════════════════════════════════════════
# R16 — Retrieved context vs output tokens (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r16_context_vs_output_tokens(scale_data: dict):
    section("R16", "Retrieved context vs output tokens — scatter")

    fig, ax = plt.subplots(figsize=(7, 5))
    for model in LLM_MODELS:
        logs = scale_data[model].get("logs")
        if logs is None or "output_tokens" not in logs.columns:
            continue
        ctx_cols = ["window_nodes", "neighbourhood_nodes", "vector_nodes"]
        present  = [c for c in ctx_cols if c in logs.columns]
        if not present:
            continue
        logs = logs.copy()
        logs["_total_ctx"] = logs[present].sum(axis=1)
        res = scatter_reg_event(ax, logs, "_total_ctx", "output_tokens", model)
        for evt, (sl, ic, r2) in res.items():
            print(f"  {model} – {evt}: slope={sl:.4f} R²={r2:.3f}")

    ax.set_xlabel("Total nodes in context")
    ax.set_ylabel("Output tokens")
    ax.set_title("Retrieved context size vs output tokens", fontweight="bold")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R16_context_vs_output_tokens")


# ═════════════════════════════════════════════════════════════════════════════
# R17 — Output tokens vs valid edges (scatter)
# ═════════════════════════════════════════════════════════════════════════════

def r17_output_tokens_vs_valid_edges(scale_data: dict):
    section("R17", "Output tokens vs valid edges — scatter")

    fig, ax = plt.subplots(figsize=(7, 5))
    for model in LLM_MODELS:
        logs = scale_data[model].get("logs")
        if logs is None:
            continue
        if "output_tokens" not in logs.columns or "valid_edges" not in logs.columns:
            continue
        res = scatter_reg_event(ax, logs, "output_tokens", "valid_edges", model)
        for evt, (sl, ic, r2) in res.items():
            print(f"  {model} – {evt}: slope={sl:.4f} R²={r2:.3f}")

    ax.set_xlabel("Output tokens")
    ax.set_ylabel("Valid edges produced")
    ax.set_title("Output tokens vs valid edges", fontweight="bold")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(linestyle="--", alpha=0.3)
    plt.tight_layout()
    savefig("R17_output_tokens_vs_valid_edges")


# ═════════════════════════════════════════════════════════════════════════════
# R18 — Graph growth through enrichment (line chart)
# ═════════════════════════════════════════════════════════════════════════════

def r18_graph_growth(sim_data: dict):
    section("R18", "Graph growth through enrichment — line chart")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    titles = ["Graph nodes over time", "Graph edges over time"]
    node_cols = [("graph_nodes", "llm_graph_nodes"),
                 ("graph_edges", "llm_graph_edges")]

    for ax, title, (base_col, llm_col) in zip(axes, titles, node_cols):
        for model in MODELS:
            kg  = sim_data[model].get("kg")
            enr = sim_data[model].get("enrichment")
            if kg is None:
                continue
            # KG baseline growth
            ax.plot(range(len(kg)), kg[base_col].values,
                    color=COLORS[model], linewidth=1.5, linestyle="--",
                    label=f"{model} (baseline)", alpha=0.6)
            # After enrichment (if available)
            if enr is not None and llm_col in enr.columns:
                ax.plot(range(len(enr)), enr[llm_col].values,
                        color=COLORS[model], linewidth=2,
                        label=f"{model} (enriched)")
        ax.set_xlabel("Enrichment event index")
        ax.set_ylabel("Count")
        ax.set_title(title, fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(linestyle="--", alpha=0.35)

    plt.tight_layout()
    savefig("R18_graph_growth")


# ═════════════════════════════════════════════════════════════════════════════
# R19 — Correct edges vs graph size (line chart)
# ═════════════════════════════════════════════════════════════════════════════

def r19_correct_edges_vs_size(scale_data: dict):
    section("R19", "Correct edges vs graph size — line chart (split by event type)")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    fig.suptitle("Correct generated edges vs graph size", fontweight="bold")
    for ax, model in zip(axes, LLM_MODELS):
        line_milestone_event(ax, {model: scale_data[model]},
                             "llm_correct_generated_edges", "enrichment")
        ax.set_title(model, color=COLORS[model], fontweight="bold")
        ax.set_ylabel("Mean correct generated edges")
    plt.tight_layout()
    savefig("R19_correct_edges_vs_size")

    for model in LLM_MODELS:
        df = scale_data[model].get("enrichment")
        if df is None:
            continue
        print(f"\n  {model}:")
        ec = "event" if "event" in df.columns else None
        for evt in (EVENT_TYPES if ec else ["all"]):
            sub = df[df[ec] == evt] if ec else df
            print(f"    {evt}:")
            for ms in SCALE_LABELS:
                describe(sub[sub["milestone"] == ms]["llm_correct_generated_edges"],
                         ms, indent=6)


# ═════════════════════════════════════════════════════════════════════════════
# R20 — CPU usage vs graph size (line chart)
# R21 — Memory usage vs graph size (line chart)
# ═════════════════════════════════════════════════════════════════════════════

def r20_r21_hardware_vs_size(scale_data: dict):
    section("R20/R21", "CPU & memory usage vs graph size — line charts")

    for col, ylabel, rid, title in [
        ("Total_Host_CPU_%",  "Host CPU (%)",    "R20", "CPU usage vs graph size"),
        ("Total_Host_Mem_MB", "Host memory (MB)","R21", "Memory usage vs graph size"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 5))
        line_milestone(ax, scale_data, col, "hardware")
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontweight="bold")
        plt.tight_layout()
        savefig(f"{rid}_{col.lower().replace('%','pct').replace(' ','_')}")

        for model in LLM_MODELS:  # scale_data only has LLM models
            df = scale_data[model].get("hardware")
            if df is None or col not in df.columns:
                continue
            print(f"\n  {model} – {col}:")
            for ms in SCALE_LABELS:
                describe(df[df["milestone"] == ms][col], ms)


# ═════════════════════════════════════════════════════════════════════════════
# R22 — GPT vs Qwen summary table
# ═════════════════════════════════════════════════════════════════════════════

def r22_summary_table(sim_data: dict, scale_data: dict, edge_ratings: pd.DataFrame):
    section("R22", "GPT vs Qwen summary — comparison table")

    rows = []

    def _mean(model, src, col, data=None, unit=1):
        d = (data or sim_data)[model].get(src)
        if d is None or col not in d.columns:
            return np.nan
        return d[col].mean() * unit

    for model in MODELS:
        row = {"Model": model}
        row["Mean generation time (s)"]     = _mean(model, "enrichment", "llm_generation_time")
        row["Mean insertion time (ms)"]     = _mean(model, "enrichment", "llm_insertion_time", unit=1000)
        row["Mean correct edges / run"]     = _mean(model, "enrichment", "llm_correct_generated_edges")
        row["Mean host CPU (%)"]            = _mean(model, "hardware",   "Total_Host_CPU_%")
        row["Mean host memory (MB)"]        = _mean(model, "hardware",   "Total_Host_Mem_MB")
        # Survey metrics (if available)
        if edge_ratings is not None:
            for dim in DIMENSIONS:
                sub = edge_ratings[(edge_ratings["treatment"] == model) &
                                   (edge_ratings["dimension"] == dim)]["rating"]
                row[f"Mean {DIM_LABELS[dim]}"] = sub.mean()
        rows.append(row)

    table = pd.DataFrame(rows).set_index("Model").T
    print(f"\n{'─'*70}")
    print(table.to_string(float_format=lambda x: f"{x:.3f}"))
    print(f"{'─'*70}")

    # Also save as CSV for easy copying into thesis
    table.to_csv(FIGURES_DIR / "R22_summary_table.csv")
    print("  → R22_summary_table.csv")


# ═════════════════════════════════════════════════════════════════════════════
# R23 — Overall comparison radar
# ═════════════════════════════════════════════════════════════════════════════

def r23_overall_radar(sim_data: dict, scale_data: dict, edge_ratings: pd.DataFrame):
    section("R23", "Overall comparison radar — normalised metrics")

    # Collect raw means, then normalise 0–1 within each metric
    # Metrics: mean quality, mean gen time (inverted), mean CPU (inverted),
    #          mean memory (inverted), mean correct edges
    raw = {}
    for model in MODELS:
        enr = sim_data[model].get("enrichment")
        hw  = sim_data[model].get("hardware")

        quality = (edge_ratings[edge_ratings["treatment"] == model]["rating"].mean()
                   if edge_ratings is not None else np.nan)
        gen_time = enr["llm_generation_time"].mean() if enr is not None else np.nan
        cpu      = hw["Total_Host_CPU_%"].mean()     if hw is not None else np.nan
        mem      = hw["Total_Host_Mem_MB"].mean()    if hw is not None else np.nan
        correct  = enr["llm_correct_generated_edges"].mean() if enr is not None else np.nan

        raw[model] = {
            "Perceived quality (↑)": quality,
            "Generation speed (↑)":  gen_time,   # will be inverted
            "CPU efficiency (↑)":    cpu,         # will be inverted
            "Memory efficiency (↑)": mem,         # will be inverted
            "Correct edges (↑)":     correct,
        }

    # Build normalised values (higher = better on all axes)
    categories = list(list(raw.values())[0].keys())
    invert = {"Generation speed (↑)", "CPU efficiency (↑)", "Memory efficiency (↑)"}

    all_vals = {cat: [raw[m][cat] for m in MODELS] for cat in categories}
    norm = {}
    for model in MODELS:
        norm[model] = []
        for cat in categories:
            vals = [v for v in all_vals[cat] if not np.isnan(v)]
            lo, hi = (min(vals), max(vals)) if vals else (0, 1)
            v = raw[model][cat]
            if np.isnan(v) or hi == lo:
                n = 0.5
            else:
                n = (v - lo) / (hi - lo)
                if cat in invert:
                    n = 1 - n
            norm[model].append(n * 3 + 1)   # scale to 1–4 range

    radar_chart(norm, categories=categories,
                title="Overall model comparison (normalised)",
                name="R23_overall_radar", vmin=1, vmax=4)
    print("  ⚠ Normalisation is within-metric across models; values are relative.")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  UNIFIED ANALYSIS — LLM KG ENRICHMENT FOR SOFTWARE TRACEABILITY")
    print(f"  Models  : {' vs '.join(MODELS)}")
    print(f"  Figures : {FIGURES_DIR}/")
    print("=" * 70)

    print("\nLoading simulation data…")
    sim_data = load_simulation()

    print("\nLoading scalability data…")
    scale_data = load_scalability()

    print("\nLoading survey data…")
    survey_raw, edge_ratings, graph_ratings, rankings = load_survey()
    label_df = load_survey_labels()

    # ── Background (R00) ─────────────────────────────────────────────────────
    if label_df is not None:
        r00_background(label_df)

    # ── Survey results ────────────────────────────────────────────────────────
    if edge_ratings is not None:
        r01_perceived_quality(edge_ratings)
        r02_quality_per_edge(edge_ratings)
        r03_quality_radar(edge_ratings)
        #r04_objective_vs_perceived(edge_ratings, sim_data)
        r05_confidence_vs_perceived(edge_ratings)
    else:
        print("\n  [SKIP] Survey results not loaded — R01–R05 skipped")

    #r06_confidence_vs_objective(scale_data)

    if rankings is not None:
        r07_graph_ranking(rankings)
    if survey_raw is not None:
        r08_open_responses(survey_raw)
    if graph_ratings is not None:
        r09_r10_dir_ratings(graph_ratings)

    # ── Performance / scalability results ─────────────────────────────────────
    r11_runtime_breakdown(sim_data)
    r11b_simulation_analysis(sim_data)
    r11b_5c_nodes_vs_valid_edges(sim_data)
    sq3_scalability_analysis(scale_data)
    r12_generation_time_vs_size(scale_data)
    r13_retrieval_time_vs_size(scale_data)
    r14_context_vs_retrieval(scale_data)
    r15_context_vs_generation(scale_data)
    r16_context_vs_output_tokens(scale_data)
    r17_output_tokens_vs_valid_edges(scale_data)
    r18_graph_growth(sim_data)
    r19_correct_edges_vs_size(scale_data)
    r20_r21_hardware_vs_size(scale_data)

    # ── Cross-cutting comparisons ─────────────────────────────────────────────
    r22_summary_table(sim_data, scale_data, edge_ratings)
    r23_overall_radar(sim_data, scale_data, edge_ratings)

    print(f"\n{'═'*70}")
    print(f"  DONE — figures saved to ./{FIGURES_DIR}/")
    print(f"{'═'*70}")


if __name__ == "__main__":
    main()
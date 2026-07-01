import os
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.stats import (
    wilcoxon,
    friedmanchisquare,
    mannwhitneyu,
    kruskal
)

RESULT_DIR = "results"
OUTPUT_DIR = "analysis_results"

os.makedirs(OUTPUT_DIR, exist_ok=True)


##############################################################################
# Utility functions
##############################################################################

def descriptive_stats(df):
    return pd.DataFrame({
        "mean": df.mean(numeric_only=True),
        "median": df.median(numeric_only=True),
        "std": df.std(numeric_only=True),
        "min": df.min(numeric_only=True),
        "max": df.max(numeric_only=True)
    })


def wilcoxon_effect_size(x, y):
    """
    Calculates Wilcoxon test and effect size r.
    """
    stat, p = wilcoxon(x, y)

    n = len(x)
    mean_w = n * (n + 1) / 4
    sd_w = np.sqrt(n * (n + 1) * (2 * n + 1) / 24)

    z = (stat - mean_w) / sd_w
    r = abs(z) / np.sqrt(n)

    return stat, p, r


##############################################################################
# Simulation results analysis
##############################################################################

sim_dir = os.path.join(RESULT_DIR, "correctness_simulation")

gpt_enrichment = pd.read_csv(
    os.path.join(sim_dir, "enrichment_results_gpt.csv")
)

qwen_enrichment = pd.read_csv(
    os.path.join(sim_dir, "enrichment_results_qwen.csv")
)

gpt_hw = pd.read_csv(
    os.path.join(sim_dir, "hardware_performance_gpt.csv")
)

qwen_hw = pd.read_csv(
    os.path.join(sim_dir, "hardware_performance_qwen.csv")
)

non_hw = pd.read_csv(
    os.path.join(sim_dir, "hardware_performance_non_enrichment.csv")
)

##############################################################################
# Descriptive statistics
##############################################################################

desc_gpt = descriptive_stats(gpt_enrichment)
desc_qwen = descriptive_stats(qwen_enrichment)

desc_gpt.to_csv(
    os.path.join(OUTPUT_DIR, "gpt_descriptive.csv")
)

desc_qwen.to_csv(
    os.path.join(OUTPUT_DIR, "qwen_descriptive.csv")
)

##############################################################################
# GPT vs Qwen enrichment comparison
##############################################################################

comparison_results = []

common_cols = list(
    set(gpt_enrichment.columns).intersection(
        qwen_enrichment.columns
    )
)

for col in common_cols:
    if col == "timestamp":
        continue

    try:
        x = gpt_enrichment[col]
        y = qwen_enrichment[col]

        if (
            np.issubdtype(x.dtype, np.number)
            and np.issubdtype(y.dtype, np.number)
        ):
            n = min(len(x), len(y))

            stat, p, r = wilcoxon_effect_size(
                x.iloc[:n],
                y.iloc[:n]
            )

            comparison_results.append({
                "metric": col,
                "wilcoxon_stat": stat,
                "p_value": p,
                "effect_size_r": r
            })

    except:
        pass

comparison_df = pd.DataFrame(comparison_results)

comparison_df.to_csv(
    os.path.join(
        OUTPUT_DIR,
        "gpt_qwen_comparison.csv"
    ),
    index=False
)

##############################################################################
# Hardware comparison
##############################################################################

hardware_results = []

hardware_cols = [
    "Total_Host_CPU_%",
    "Total_Host_Mem_MB",
    "Ollama_CPU_%",
    "Ollama_Mem_MB"
]

for col in hardware_cols:
    try:
        n = min(len(gpt_hw), len(qwen_hw))

        stat, p, r = wilcoxon_effect_size(
            gpt_hw[col].iloc[:n],
            qwen_hw[col].iloc[:n]
        )

        hardware_results.append({
            "metric": col,
            "wilcoxon_stat": stat,
            "p_value": p,
            "effect_size_r": r
        })

    except:
        pass

hardware_df = pd.DataFrame(hardware_results)

hardware_df.to_csv(
    os.path.join(
        OUTPUT_DIR,
        "hardware_comparison.csv"
    ),
    index=False
)

##############################################################################
# Scalability analysis
##############################################################################

scalability_dir = os.path.join(
    RESULT_DIR,
    "scalability validation"
)

runs = glob.glob(
    os.path.join(
        scalability_dir,
        "run_*"
    )
)

all_scalability = []

for run in runs:

    name = os.path.basename(run)

    enrich_file = os.path.join(
        run,
        "enrichment_results.csv"
    )

    hw_file = os.path.join(
        run,
        "hardware_performance.csv"
    )

    if os.path.exists(enrich_file):

        df = pd.read_csv(enrich_file)

        stats = descriptive_stats(df)

        stats["run"] = name
        stats["metric"] = stats.index

        all_scalability.append(stats)

    if os.path.exists(hw_file):

        df = pd.read_csv(hw_file)

        stats = descriptive_stats(df)

        stats["run"] = name
        stats["metric"] = stats.index

        all_scalability.append(stats)

if all_scalability:
    scalability_df = pd.concat(all_scalability)

    scalability_df.to_csv(
        os.path.join(
            OUTPUT_DIR,
            "scalability_results.csv"
        )
    )

##############################################################################
# Plots
##############################################################################

for metric in [
    "llm_generation_time",
    "llm_generated_edges",
    "llm_correct_generated_edges"
]:
    if (
        metric in gpt_enrichment.columns
        and metric in qwen_enrichment.columns
    ):

        plt.figure(figsize=(8, 5))

        plt.boxplot([
            gpt_enrichment[metric].dropna(),
            qwen_enrichment[metric].dropna()
        ])

        plt.xticks(
            [1, 2],
            ["GPT", "Qwen"]
        )

        plt.ylabel(metric)
        plt.title(metric)

        plt.tight_layout()

        plt.savefig(
            os.path.join(
                OUTPUT_DIR,
                f"{metric}.png"
            )
        )

        plt.close()

print("Analysis completed.")
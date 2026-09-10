"""CLI: generate tailored CV suggestions for selected jobs from a daily CSV.

Usage:
    python tailor_jobs.py output/jobs_2026-09-10.csv 0 3 7
"""

import sys

import pandas as pd

from scripts.tailor import tailor_job


def main():
    if len(sys.argv) < 3:
        print("Usage: python tailor_jobs.py <csv_path> <row_index> [row_index ...]")
        sys.exit(1)

    csv_path = sys.argv[1]
    row_indices = [int(arg) for arg in sys.argv[2:]]

    df = pd.read_csv(csv_path)

    for idx in row_indices:
        if idx < 0 or idx >= len(df):
            print(f"Skipping index {idx}: out of range (0-{len(df) - 1})")
            continue
        job = df.iloc[idx].to_dict()
        tailor_job(job)


if __name__ == "__main__":
    main()

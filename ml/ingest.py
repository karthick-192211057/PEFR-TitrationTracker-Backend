"""
Ingestion and preprocessing for real datasets.

This script searches `ml/data/` for CSV files, attempts to map columns
to the features expected by the trainer (`age`, `pefr_value`, `wheeze_rating`,
`cough_rating`, `dust_exposure`, `smoke_exposure`). If label columns
(`medicine`, `days`, `cure_prob`) are missing, it creates heuristic labels
so the dataset can be used to retrain the models.

Usage:
    python ingest.py --out combined.csv

"""
from pathlib import Path
import pandas as pd
import argparse
import numpy as np


DATA_DIR = Path(__file__).parent / "data"


def try_map_columns(df: pd.DataFrame):
    # lower-case mapping
    cols = {c.lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    mapped = pd.DataFrame()
    mapped["age"] = df[pick("age", "patient_age", "years", "ageyears")] if pick("age", "patient_age", "years", "ageyears") else None
    # find pefr/peak flow
    pefr_col = pick("pefr", "pefr_value", "peak_expiratory_flow", "peak_flow", "peakflow", "pef", "peak_expiratory_flow_rate")
    if pefr_col:
        mapped["pefr_value"] = df[pefr_col]
    # try common spirometry fields (FEV1) which we can use to estimate PEFR
    fev1_col = pick("fev1", "lungfunctionfev1", "fev_1", "fev1_l")
    if fev1_col:
        mapped["fev1"] = pd.to_numeric(df[fev1_col], errors="coerce")
    # wheeze, cough
    mapped["wheeze_rating"] = df[pick("wheeze", "wheeze_rating")] if pick("wheeze", "wheeze_rating") else None
    mapped["cough_rating"] = df[pick("cough", "cough_rating")] if pick("cough", "cough_rating") else None
    # exposures
    mapped["dust_exposure"] = df[pick("dust_exposure", "dust", "dust_exposure_bool")] if pick("dust_exposure", "dust", "dust_exposure_bool") else None
    mapped["smoke_exposure"] = df[pick("smoke_exposure", "smoking", "smoker", "smoke")] if pick("smoke_exposure", "smoking", "smoker", "smoke") else None

    # labels if present
    med_col = pick("medicine", "medication", "drug")
    days_col = pick("days", "duration", "treatment_days")
    prob_col = pick("cure_prob", "cure_probability", "probability")

    if med_col:
        mapped["medicine"] = df[med_col]
    if days_col:
        mapped["days"] = df[days_col]
    if prob_col:
        mapped["cure_prob"] = df[prob_col]

    return mapped


def heuristic_label(row, rng=np.random.RandomState(0)):
    # Build a severity score similar to the synthetic generator
    p = row.get("pefr_value")
    pnorm = 0
    try:
        if pd.notnull(p):
            pnorm = int((p / 600) * 100)
    except Exception:
        pnorm = 0

    w = row.get("wheeze_rating") or 0
    c = row.get("cough_rating") or 0
    d = 1 if row.get("dust_exposure") else 0
    s = 1 if row.get("smoke_exposure") else 0

    severity = (100 - min(100, pnorm)) + (w * 5) + (c * 3) + (d * 10) + (s * 10)
    if severity < 30:
        med = "Inhaled Corticosteroid"
        day = int(rng.normal(5, 2))
        prob = 0.85
    elif severity < 60:
        med = "Short Acting Beta Agonist"
        day = int(rng.normal(7, 3))
        prob = 0.6
    else:
        med = "Oral Steroid"
        day = int(rng.normal(10, 4))
        prob = 0.4

    day = max(1, min(30, day))
    prob = min(1.0, max(0.0, prob + rng.normal(0, 0.05)))
    return med, day, prob


def main(out_path: Path):
    files = list(DATA_DIR.glob("*.csv"))
    if not files:
        print("No CSV files found in", DATA_DIR)
        return

    parts = []
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception:
            try:
                df = pd.read_excel(f)
            except Exception:
                print("Skipping", f, "(unreadable)")
                continue

        mapped = try_map_columns(df)
        parts.append(mapped)

    full = pd.concat(parts, ignore_index=True, sort=False)

    # fill missing numeric columns
    for c in ["age", "pefr_value", "wheeze_rating", "cough_rating"]:
        if c in full.columns:
            full[c] = pd.to_numeric(full[c], errors="coerce")

    # fill exposures
    for c in ["dust_exposure", "smoke_exposure"]:
        if c in full.columns:
            full[c] = full[c].apply(lambda x: True if str(x).strip().lower() in ("1","true","yes","y","t") else False if pd.notnull(x) else False)
        else:
            full[c] = False

    # create heuristic labels where missing
    rng = np.random.RandomState(1)
    meds = []
    days = []
    probs = []
    for _, r in full.iterrows():
        if pd.notnull(r.get("medicine")) and pd.notnull(r.get("days")) and pd.notnull(r.get("cure_prob")):
            meds.append(r.get("medicine"))
            days.append(int(r.get("days")))
            probs.append(float(r.get("cure_prob")))
        else:
            m, d, p = heuristic_label(r, rng)
            meds.append(m)
            days.append(d)
            probs.append(p)

    full["medicine"] = meds
    full["days"] = days
    full["cure_prob"] = probs

    # keep only needed columns
    # if PEFR missing, try to estimate from FEV1 or synthesize
    if "pefr_value" not in full.columns or full["pefr_value"].isna().all():
        if "fev1" in full.columns:
            # rough estimate: scale FEV1 to PEFR range
            full["pefr_value"] = (full["fev1"].fillna(0) * 200).astype(float)
        else:
            # synthesize PEFR based on age and symptom severity
            def synth_pefr(r):
                base = 400
                if pd.notnull(r.get("age")):
                    base = max(150, 500 - (r.get("age") * 1.5))
                w = r.get("wheeze_rating") or 0
                c = r.get("cough_rating") or 0
                penalty = (w * 20) + (c * 10)
                return max(50.0, base - penalty + np.random.normal(0, 30))

            full["pefr_value"] = full.apply(synth_pefr, axis=1)

    out = full[["age", "pefr_value", "wheeze_rating", "cough_rating", "dust_exposure", "smoke_exposure", "medicine", "days", "cure_prob"]]
    out.to_csv(out_path, index=False)
    print("Written combined dataset to", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DATA_DIR / "combined_real.csv"))
    args = parser.parse_args()
    main(Path(args.out))

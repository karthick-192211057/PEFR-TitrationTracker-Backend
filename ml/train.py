"""
Training script for asthma treatment recommendation models.

NOTE: This script generates a synthetic dataset when no CSV is provided.
It trains simple scikit-learn models and saves them to disk. This block is
marked 'for deep learning' in comments so it can be replaced with a
TensorFlow/PyTorch model later without changing the API.

Usage:
    python train.py            # trains on synthetic data and saves models
    python train.py --data mydata.csv

"""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import joblib


MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def generate_synthetic(n=2000, seed=42):
    rng = np.random.RandomState(seed)
    ages = rng.randint(5, 80, size=n)
    pefr = rng.randint(50, 600, size=n)
    wheeze = rng.randint(0, 4, size=n)
    cough = rng.randint(0, 4, size=n)
    dust = rng.randint(0, 2, size=n)
    smoke = rng.randint(0, 2, size=n)

    # Simple heuristics to assign medicine and days for synthetic labels
    medicines = []
    days = []
    cure_prob = []
    for a, p, w, c, d, s in zip(ages, pefr, wheeze, cough, dust, smoke):
        severity = (100 - min(100, int((p / 600) * 100))) + w * 5 + c * 3 + d * 10 + s * 10
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

        medicines.append(med)
        days.append(day)
        cure_prob.append(prob)

    df = pd.DataFrame({
        "age": ages,
        "pefr_value": pefr,
        "wheeze_rating": wheeze,
        "cough_rating": cough,
        "dust_exposure": dust,
        "smoke_exposure": smoke,
        "medicine": medicines,
        "days": days,
        "cure_prob": cure_prob,
    })
    return df


def train(args):
    if args.data:
        df = pd.read_csv(args.data)
    else:
        df = generate_synthetic()

    # Features
    X = df[["age", "pefr_value", "wheeze_rating", "cough_rating", "dust_exposure", "smoke_exposure"]].fillna(0)

    # Medicine classifier
    le = LabelEncoder()
    y_med = le.fit_transform(df["medicine"])
    clf = RandomForestClassifier(n_estimators=100, random_state=0)
    clf.fit(X, y_med)

    # Days regressor
    y_days = df["days"].values
    reg_days = RandomForestRegressor(n_estimators=100, random_state=0)
    reg_days.fit(X, y_days)

    # Cure probability regressor
    y_prob = df["cure_prob"].values
    reg_prob = RandomForestRegressor(n_estimators=100, random_state=0)
    reg_prob.fit(X, y_prob)

    # Save models
    joblib.dump(clf, MODEL_DIR / "medicine_clf.joblib")
    joblib.dump(le, MODEL_DIR / "label_encoder.joblib")
    joblib.dump(reg_days, MODEL_DIR / "days_reg.joblib")
    joblib.dump(reg_prob, MODEL_DIR / "prob_reg.joblib")

    print("Models saved to:", MODEL_DIR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="Path to CSV data (optional)")
    args = parser.parse_args()
    train(args)

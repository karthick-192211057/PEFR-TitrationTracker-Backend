"""
Model loader and predictor helpers.

This module loads the models produced by `train.py` and exposes a
`predict` function that accepts a dictionary of features and returns
the recommended medicine, days, and cure probability.

Comment: // this for deep learning - placeholder for model code
"""
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
import time

MODEL_DIR = Path(__file__).parent / "models"


class Predictor:
    def __init__(self):
        self._loaded = False
        self._load_models()

    def _load_models(self):
        clf_path = MODEL_DIR / "medicine_clf.joblib"
        le_path = MODEL_DIR / "label_encoder.joblib"
        days_path = MODEL_DIR / "days_reg.joblib"
        prob_path = MODEL_DIR / "prob_reg.joblib"

        if not clf_path.exists() or not le_path.exists() or not days_path.exists() or not prob_path.exists():
            raise FileNotFoundError("Models not found. Please run ml/train.py to generate models.")

        self.clf = joblib.load(clf_path)
        self.le = joblib.load(le_path)
        self.days_reg = joblib.load(days_path)
        self.prob_reg = joblib.load(prob_path)
        self._loaded = True

    def predict(self, features: dict):
        # Expected keys: age, pefr_value, wheeze_rating, cough_rating, dust_exposure, smoke_exposure
        # Build a DataFrame with the same column names used during training
        cols = ["age", "pefr_value", "wheeze_rating", "cough_rating", "dust_exposure", "smoke_exposure"]
        # Build and sanitize input row with explicit dtypes
        row = {
            "age": int(features.get("age") or 0),
            "pefr_value": float(features.get("pefr_value") or 0.0),
            "wheeze_rating": int(features.get("wheeze_rating") or 0),
            "cough_rating": int(features.get("cough_rating") or 0),
            "dust_exposure": 1 if features.get("dust_exposure") else 0,
            "smoke_exposure": 1 if features.get("smoke_exposure") else 0,
        }

        # Basic sanity/clamping for inputs (helps ensure consistent preprocessing)
        if row["age"] < 0:
            row["age"] = 0
        # reasonable PEFR range: 0 - 1000 (clamp unexpected readings)
        row["pefr_value"] = float(max(0.0, min(1000.0, row["pefr_value"])))
        for k in ("wheeze_rating", "cough_rating"):
            row[k] = int(max(0, min(10, row[k])))

        arr = pd.DataFrame([row], columns=cols)

        # enforce dtypes to avoid differences between pandas/numpy versions
        arr = arr.astype({
            "age": "int64",
            "pefr_value": "float64",
            "wheeze_rating": "int64",
            "cough_rating": "int64",
            "dust_exposure": "int64",
            "smoke_exposure": "int64",
        })

        # Predict (sklearn models should be deterministic if trained/saved consistently)
        med_idx = int(self.clf.predict(arr)[0])
        med = self.le.inverse_transform([med_idx])[0]
        days = int(round(float(self.days_reg.predict(arr)[0])))
        prob = float(self.prob_reg.predict(arr)[0])

        # clamp values
        days = max(1, min(30, days))
        prob = max(0.0, min(1.0, prob))

        return {
            "recommended_medicine": med,
            "recommended_days": days,
            "predicted_cure_probability": prob,
        }


# Singleton predictor instance (will raise if models missing)
_PREDICTOR = None


def get_predictor():
    global _PREDICTOR
    if _PREDICTOR is None:
        _PREDICTOR = Predictor()
    return _PREDICTOR


def model_and_env_info():
    """Return versions and model file timestamps useful for reproducibility checks.

    Useful to return in API responses when debugging inconsistent outputs across
    environments (e.g., local vs Colab)."""
    info = {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__ if hasattr(joblib, "__version__") else "unknown",
        "model_files": {},
    }
    for fname in ("medicine_clf.joblib", "label_encoder.joblib", "days_reg.joblib", "prob_reg.joblib"):
        p = MODEL_DIR / fname
        if p.exists():
            info["model_files"][fname] = {
                "path": str(p),
                "modified_ts": int(p.stat().st_mtime)
            }
        else:
            info["model_files"][fname] = None
    return info

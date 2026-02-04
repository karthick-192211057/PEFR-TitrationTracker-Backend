# Machine Learning extension for PEFR Titration Tracker

This folder contains a minimal ML pipeline added to the backend as an optional extension.

Files added:

- `ml/train.py` — training script (generates synthetic data by default) — comment markers added for deep learning replacement.
- `ml/predictor.py` — loads trained models and exposes a `predict()` helper.
- `ml/test_predict.py` — small runner to sanity-check predictions.
- `models/` — generated after running the trainer; contains joblib model files.

## Quick start

1. Install dependencies (inside your Python venv):

```bash
pip install -r requirements.txt
```

2. Train models (creates `ml/models/`):

```bash
python ml/train.py
```

3. Run a quick check:

```bash
python -m ml.test_predict
```

4. Start the API server and call the authenticated endpoint `POST /ml/predict` with the `MLInput` payload.

## Notes

- The training script currently uses scikit-learn with synthetic data and includes comments marking where to replace with a deep-learning model (TensorFlow/PyTorch) if desired.
- The API endpoint will return `503` if the model files are missing. Run the trainer before calling the endpoint in production.

## Reproducibility and Colab

To ensure the same predictions across environments (local, Colab, server):

- Use the provided trained models in `ml/models/` — do not retrain unless you intend to change outputs.
- Pin package versions (see `requirements.txt`) so scikit-learn, numpy and pandas match across environments.
- Copy the `ml/models/` directory into your Colab workspace (or mount Drive) and use the same `predictor.py` API.
- When debugging differing outputs, call `from ml.predictor import model_and_env_info; print(model_and_env_info())` to see package versions and model file timestamps.

Example Colab snippet:

```python
!pip install -r /path/to/asthma-backend/requirements.txt
from ml.predictor import get_predictor, model_and_env_info
print(model_and_env_info())
pred = get_predictor().predict({"age":30, "pefr_value":400, "wheeze_rating":1, "cough_rating":0, "dust_exposure":0, "smoke_exposure":0})
print(pred)
```

If outputs still differ, ensure the model files in Colab match the ones on your device (compare the `modified_ts` values returned by `model_and_env_info`).

"""
Simple test runner for ml.predictor

Run after training models:
    python -m ml.test_predict
"""
from ml.predictor import get_predictor


def main():
    p = get_predictor()
    sample = {
        "age": 30,
        "pefr_value": 200,
        "wheeze_rating": 2,
        "cough_rating": 1,
        "dust_exposure": True,
        "smoke_exposure": False,
    }
    print(p.predict(sample))


if __name__ == "__main__":
    main()

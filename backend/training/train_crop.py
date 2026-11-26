"""Train the crop recommendation model on the Crop Recommendation dataset (Ingle, Kaggle; 2,200 rows, 22 crops).

Compares several classifiers with 5-fold stratified CV, keeps the best one, and reports held-out test metrics.
Outputs backend/models/crop_model.joblib and crop_metrics.json (+ crop_profiles.json: per-crop feature ranges).
"""
import json, time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import GaussianNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]

df = pd.read_csv(ROOT / "data" / "crop_recommendation.csv")
X, y = df[FEATURES].values, df["label"].values
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

candidates = {
    "Random Forest": RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1),
    "Gradient Boosting": GradientBoostingClassifier(random_state=42),
    "Logistic Regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000)),
    "Gaussian Naive Bayes": GaussianNB(),
}
cv = StratifiedKFold(5, shuffle=True, random_state=42)
comparison = {}
for name, m in candidates.items():
    s = cross_val_score(m, Xtr, ytr, cv=cv, scoring="f1_macro", n_jobs=1)
    comparison[name] = {"cv_macro_f1_mean": round(float(s.mean()), 4), "cv_macro_f1_std": round(float(s.std()), 4)}
    print(name, comparison[name])

best = max(comparison, key=lambda k: comparison[k]["cv_macro_f1_mean"])
model = candidates[best].fit(Xtr, ytr)
pred = model.predict(Xte)
labels = sorted(set(y))
rep = classification_report(yte, pred, output_dict=True, zero_division=0)
metrics = {
    "selected_model": best, "dataset": "Crop Recommendation Dataset (A. Ingle, Kaggle) - 2,200 rows, 22 crops",
    "features": FEATURES, "split": {"train": len(ytr), "test": len(yte)}, "cv_comparison": comparison,
    "test_accuracy": round(accuracy_score(yte, pred), 4), "test_macro_f1": round(f1_score(yte, pred, average="macro"), 4),
    "per_class": {c: {k: round(v, 4) for k, v in rep[c].items()} for c in labels},
    "confusion_matrix": confusion_matrix(yte, pred, labels=labels).tolist(), "classes": labels,
    "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "limitations": ("The dataset is a compiled/augmented benchmark with clean, well-separated classes, so the very high "
                    "scores overstate real-field accuracy. Use recommendations as a starting point alongside local advice."),
}
if hasattr(model, "feature_importances_"):
    metrics["feature_importance"] = dict(zip(FEATURES, [round(float(v), 4) for v in model.feature_importances_]))
# Refit on all data for deployment
model = candidates[best].fit(X, y)
joblib.dump({"model": model, "features": FEATURES}, ROOT / "models" / "crop_model.joblib", compress=3)
json.dump(metrics, open(ROOT / "models" / "crop_metrics.json", "w"), indent=2)

profiles = {}
for crop, g in df.groupby("label"):
    profiles[crop] = {f: {"p10": round(float(np.percentile(g[f], 10)), 2), "median": round(float(g[f].median()), 2),
                          "p90": round(float(np.percentile(g[f], 90)), 2)} for f in FEATURES}
json.dump(profiles, open(ROOT / "models" / "crop_profiles.json", "w"), indent=2)
print("best", best, metrics["test_accuracy"], metrics["test_macro_f1"])

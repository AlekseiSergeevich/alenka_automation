from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_FEATURES = [
    "lag_1",
    "lag_2",
    "lag_3",
    "lag_6",
    "lag_12",
    "ma3",
    "ma6",
    "rolling_std_3",
    "rolling_std_6",
    "diff_1",
    "diff_12",
    "month_num",
    "month_sin",
    "month_cos",
    "is_december",
    "unit_кг",
    "unit_шт",
]


@dataclass
class SplitResult:
    train: pd.DataFrame
    test: pd.DataFrame
    feature_columns: list[str]


def load_monthly_sales(csv_path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["sku"] = df["sku"].fillna("").astype(str).str.strip()
    df["product"] = df["product"].fillna("").astype(str).str.strip()
    df["unit"] = df["unit"].fillna("").astype(str).str.strip()
    df["month"] = pd.to_datetime(df["month"], format="%Y-%m")
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce").fillna(0.0)

    df = df.loc[df["sku"] != ""].copy()

    monthly = (
        df.groupby(["sku", "month"], as_index=False)
        .agg(
            product=("product", "first"),
            unit=("unit", "first"),
            qty=("qty", "sum"),
        )
        .sort_values(["sku", "month"])
        .reset_index(drop=True)
    )
    return monthly


def expand_to_month_grid(monthly: pd.DataFrame) -> pd.DataFrame:
    all_months = pd.date_range(monthly["month"].min(), monthly["month"].max(), freq="MS")
    sku_meta = monthly[["sku", "product", "unit"]].drop_duplicates("sku")

    full_index = pd.MultiIndex.from_product(
        [sku_meta["sku"].tolist(), all_months],
        names=["sku", "month"],
    )

    expanded = (
        pd.DataFrame(index=full_index)
        .reset_index()
        .merge(sku_meta, on="sku", how="left")
        .merge(monthly[["sku", "month", "qty"]], on=["sku", "month"], how="left")
    )

    expanded["qty"] = expanded["qty"].fillna(0.0)
    expanded = expanded.sort_values(["sku", "month"]).reset_index(drop=True)
    return expanded


def add_time_series_features(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy().sort_values(["sku", "month"]).reset_index(drop=True)
    grp = df.groupby("sku", sort=False)["qty"]
    history = grp.shift(1)

    for lag in [1, 2, 3, 6, 12]:
        df[f"lag_{lag}"] = grp.shift(lag)

    df["ma3"] = history.rolling(window=3).mean().reset_index(level=0, drop=True)
    df["ma6"] = history.rolling(window=6).mean().reset_index(level=0, drop=True)
    df["rolling_std_3"] = history.rolling(window=3).std().reset_index(level=0, drop=True)
    df["rolling_std_6"] = history.rolling(window=6).std().reset_index(level=0, drop=True)

    df["diff_1"] = grp.diff(1).shift(1)
    df["diff_12"] = grp.diff(12).shift(1)

    df["month_num"] = df["month"].dt.month # type: ignore
    angle = 2 * np.pi * df["month_num"] / 12
    df["month_sin"] = np.sin(angle)
    df["month_cos"] = np.cos(angle)
    df["is_december"] = (df["month_num"] == 12).astype(int)

    unit_dummies = pd.get_dummies(df["unit"], prefix="unit", dtype=int)
    df = pd.concat([df, unit_dummies], axis=1)

    for column in ["unit_кг", "unit_шт"]:
        if column not in df.columns:
            df[column] = 0

    return df


def build_model_frame(
    csv_path: str | Path,
    min_history: int = 24,
    feature_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    monthly = load_monthly_sales(csv_path)
    expanded = expand_to_month_grid(monthly)
    featured = add_time_series_features(expanded)

    history_count = featured.groupby("sku")["qty"].transform("size")
    featured = featured.loc[history_count >= min_history].copy()

    feature_columns = list(feature_columns or DEFAULT_FEATURES)
    required_columns = ["sku", "product", "unit", "month", "qty", *feature_columns]
    featured = featured[required_columns].copy()
    featured = featured.dropna(subset=["lag_12"]).reset_index(drop=True)
    return featured


def choose_sku_subset(
    featured: pd.DataFrame,
    n_skus: int = 6,
    random_state: int = 42,
) -> list[str]:
    sku_summary = (
        featured.groupby("sku", as_index=False)
        .agg(
            mean_qty=("qty", "mean"),
            total_qty=("qty", "sum"),
            non_zero_share=("qty", lambda s: (s > 0).mean()),
            unit=("unit", "first"),
        )
        .sort_values("total_qty", ascending=False)
        .reset_index(drop=True)
    )

    sku_summary["volume_bucket"] = pd.qcut(
        sku_summary["total_qty"].rank(method="first"),
        q=min(3, len(sku_summary)),
        labels=["low", "mid", "high"][: min(3, len(sku_summary))],
    )

    rng = np.random.default_rng(random_state)
    chosen: list[str] = []
    for _, bucket in sku_summary.groupby(["unit", "volume_bucket"], dropna=False):
        if len(chosen) >= n_skus:
            break
        take = min(2, len(bucket), n_skus - len(chosen))
        sampled = bucket.sample(n=take, random_state=int(rng.integers(0, 1_000_000)))
        chosen.extend(sampled["sku"].tolist())

    if len(chosen) < n_skus:
        extra = sku_summary.loc[~sku_summary["sku"].isin(chosen), "sku"].head(n_skus - len(chosen))
        chosen.extend(extra.tolist())

    return chosen[:n_skus]


def temporal_split(
    featured: pd.DataFrame,
    test_months: int = 3,
    feature_columns: Iterable[str] | None = None,
) -> SplitResult:
    feature_columns = list(feature_columns or DEFAULT_FEATURES)
    cutoff = featured["month"].max() - pd.DateOffset(months=test_months - 1)
    train = featured.loc[featured["month"] < cutoff].copy()
    test = featured.loc[featured["month"] >= cutoff].copy()
    return SplitResult(train=train, test=test, feature_columns=feature_columns)


def train_random_forest(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: Iterable[str] | None = None,
):
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "scikit-learn is not installed in the current environment. "
            "Install it before training the RandomForestRegressor."
        ) from exc

    feature_columns = list(feature_columns or DEFAULT_FEATURES)

    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train[feature_columns], train["qty"])

    predictions = test[["sku", "month", "qty"]].copy()
    predictions["prediction"] = model.predict(test[feature_columns]).clip(min=0)
    return model, predictions


def evaluate_predictions(predictions: pd.DataFrame) -> dict[str, float]:
    actual = predictions["qty"].to_numpy(dtype=float)
    pred = predictions["prediction"].to_numpy(dtype=float)

    mae = float(np.mean(np.abs(actual - pred)))
    rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))

    non_zero_mask = actual != 0
    if non_zero_mask.any():
        mape = float(
            np.mean(np.abs((actual[non_zero_mask] - pred[non_zero_mask]) / actual[non_zero_mask])) * 100
        )
    else:
        mape = float("nan")

    wape = float(np.abs(actual - pred).sum() / np.maximum(np.abs(actual).sum(), 1e-9) * 100)

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape_non_zero": round(mape, 4),
        "wape": round(wape, 4),
    }


def run_subset_experiment(
    csv_path: str | Path,
    n_skus: int = 6,
    min_history: int = 24,
    test_months: int = 3,
) -> tuple[pd.DataFrame, dict[str, float]]:
    featured = build_model_frame(csv_path, min_history=min_history)
    subset_skus = choose_sku_subset(featured, n_skus=n_skus)
    subset = featured.loc[featured["sku"].isin(subset_skus)].copy()

    split = temporal_split(subset, test_months=test_months)
    _, predictions = train_random_forest(split.train, split.test, split.feature_columns)
    metrics = evaluate_predictions(predictions)
    return predictions, metrics


if __name__ == "__main__":
    csv_path = Path("data/clean/new_sales_data.csv")
    featured = build_model_frame(csv_path, min_history=24)
    subset_skus = choose_sku_subset(featured, n_skus=6)
    subset = featured.loc[featured["sku"].isin(subset_skus)].copy()
    split = temporal_split(subset, test_months=3)

    print("Selected SKU subset:", subset_skus)
    print("Train rows:", len(split.train), "Test rows:", len(split.test))
    print("Feature columns:", split.feature_columns)

    try:
        _, predictions = train_random_forest(split.train, split.test, split.feature_columns)
        print("Metrics:", evaluate_predictions(predictions))
        print(predictions.head(10).to_string(index=False))
    except ModuleNotFoundError as exc:
        print(exc)

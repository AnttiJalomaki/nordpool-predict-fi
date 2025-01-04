"""
Trains an XGBoost model for wind power prediction using meteorological features.

- Reads hyperparameters from a JSON file set by WIND_POWER_XGB_HYPERPARAMS in the environment.
- Trains XGBoost with early stopping and returns the trained model

"""

import os
import sys
import json
import numpy as np
import pandas as pd
from typing import Tuple, List
from rich import print
from sklearn.model_selection import train_test_split
import xgboost as xgb

pd.options.mode.copy_on_write = True

def preprocess_data(df: pd.DataFrame, target_col: str, wp_fmisid: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    # print("→ Preprocess: Starting data preprocessing")

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)

    if 'WindPowerCapacityMW' in df.columns:
        df['WindPowerCapacityMW'] = df['WindPowerCapacityMW'].ffill()
    else:
        print("[ERROR] 'WindPowerCapacityMW' column not found.")
        sys.exit(1)

    ws_cols = [f"ws_{id}" for id in wp_fmisid]
    t_cols = [f"t_{id}" for id in wp_fmisid]

    if not all(col in df.columns for col in ws_cols):
        missing_ws_cols = [col for col in ws_cols if col not in df.columns]
        raise KeyError(f"[ERROR] Missing wind speed columns: {missing_ws_cols}")
    df['Avg_WindSpeed'] = df[ws_cols].mean(axis=1)
    df['WindSpeed_Variance'] = df[ws_cols].var(axis=1)

    feature_columns = ws_cols + t_cols + [
        # 'hour_sin', 'hour_cos', # 2025-01-01: Consider adding these later
        'WindPowerCapacityMW',
        'Avg_WindSpeed',
        'WindSpeed_Variance'
    ]

    missing_cols = [col for col in feature_columns if col not in df.columns]
    if missing_cols:
        raise KeyError(f"[ERROR] Missing feature columns: {missing_cols}")

    if target_col not in df.columns:
        raise KeyError(f"[ERROR] Target column '{target_col}' not found in dataframe.")

    initial_count = df.shape[0]
    df.dropna(subset=feature_columns + [target_col], inplace=True)
    dropped_count = initial_count - df.shape[0]
    if dropped_count > 0:
        print(f"→ Dropped {dropped_count} rows with NaN values.")

    X = df[feature_columns]
    y = df[target_col]

    return X, y

def train_windpower_xgb(df: pd.DataFrame, target_col: str, wp_fmisid: List[str]):
    # print("→ Train model: Reading hyperparameters")

    try:
        WIND_POWER_XGB_HYPERPARAMS = os.getenv("WIND_POWER_XGB_HYPERPARAMS", "models/windpower_xgb_hyperparams.json")
        if WIND_POWER_XGB_HYPERPARAMS is None:
            raise ValueError("WIND_POWER_XGB_HYPERPARAMS is not set.")
    except ValueError as e:
        print("[ERROR] Missing environment variable for XGB hyperparams.")
        sys.exit(1)

    try:
        with open(WIND_POWER_XGB_HYPERPARAMS, 'r') as f:
            hyperparams = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Hyperparameters file not found at {WIND_POWER_XGB_HYPERPARAMS}.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Decoding JSON: {e}")
        sys.exit(1)

    test_size = hyperparams.get("test_size", 0.1) # Use nearly all data for live training

    # print("→ Train model: Preprocessing wind power data")
    X_features, y_target = preprocess_data(df, target_col, wp_fmisid)

    # print(f"→ Input data shape: {X_features.shape}, Target shape: {y_target.shape}")

    train_X, test_X, train_y, test_y = train_test_split(X_features, 
                                                        y_target, 
                                                        test_size=test_size, 
                                                        shuffle=True, 
                                                        random_state=42
                                                        )

    print(f"→ Train set: {train_X.shape}, Test set: {test_X.shape}")
   
    # print("→ X features description:")
    # print(X_features.describe())
    
    # print("→ Y target description:")
    # print(y_target.describe())
    
    # Train the model
    print("→ XGBoost for wind power: ", end="")
    print(", ".join(f"{k}={v}" for k, v in hyperparams.items()))
    xgb_model = xgb.XGBRegressor(**{k: v for k, v in hyperparams.items() if k not in ["test_size"]})

    xgb_model.fit(
        train_X, train_y,
        eval_set=[(test_X, test_y)],
        verbose=500
    )

    # print("→ Wind power model training complete.")
    return xgb_model

import os
import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
from imblearn.over_sampling import SMOTE
from src.database import get_watchlist_tickers, get_prices

def engineer_features(df):
    """
    Calculates quantitative features and a target variable for a given DataFrame of OHLCV prices.
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    
    # Standardize column names to lowercase
    col_map = {c: str(c).lower() for c in df.columns}
    df.rename(columns=col_map, inplace=True)
    
    if 'close' not in df.columns:
        return pd.DataFrame()

    close = df['close']
    high = df.get('high', close)
    low = df.get('low', close)
    volume = df.get('volume', pd.Series(np.zeros(len(df)), index=df.index))

    # 1. Moving Averages & Distances
    df['sma_20'] = close.rolling(window=20).mean()
    df['sma_50'] = close.rolling(window=50).mean()
    df['sma_200'] = close.rolling(window=200).mean()
    
    df['dist_sma_20'] = (close - df['sma_20']) / df['sma_20']
    df['dist_sma_50'] = (close - df['sma_50']) / df['sma_50']
    df['dist_sma_200'] = (close - df['sma_200']) / df['sma_200']

    # 2. Rolling Returns
    df['return_1d'] = close.pct_change(1)
    df['return_3d'] = close.pct_change(3)
    df['return_5d'] = close.pct_change(5)
    df['return_10d'] = close.pct_change(10)
    df['return_20d'] = close.pct_change(20)

    # 3. RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # 4. MACD
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # 5. Bollinger Bands (20, 2)
    std_20 = close.rolling(window=20).std()
    df['bb_upper'] = df['sma_20'] + (std_20 * 2)
    df['bb_lower'] = df['sma_20'] - (std_20 * 2)
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['sma_20']

    # 6. ATR (14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(window=14).mean()

    # 7. Volume Averages
    df['vol_sma_10'] = volume.rolling(window=10).mean()
    df['vol_sma_50'] = volume.rolling(window=50).mean()
    # Avoid division by zero
    df['vol_ratio'] = volume / df['vol_sma_10'].replace(0, np.nan)

    # Target Variable: 1 if max high in next 5 days is > 3% above current close, else 0
    future_highs = pd.concat([high.shift(-i) for i in range(1, 6)], axis=1)
    max_high_next_5d = future_highs.max(axis=1)
    
    # Calculate target and cast to float to support NaNs
    df['target_3pct_5d'] = ((max_high_next_5d / close - 1) > 0.03).astype(float)
    
    # Set the last 5 rows to NaN since we cannot fully compute their future 5-day high
    if len(df) >= 5:
        df.iloc[-5:, df.columns.get_loc('target_3pct_5d')] = np.nan

    return df


def train_model():
    tickers = get_watchlist_tickers()
    all_data = []
    
    for ticker in tickers:
        df = get_prices(ticker)
        if df is not None and not df.empty:
            df_features = engineer_features(df)
            if 'ticker' not in df_features.columns:
                df_features['ticker'] = ticker
            all_data.append(df_features)
            
    if not all_data:
        print("No data available for training.")
        return
        
    master_df = pd.concat(all_data, ignore_index=True)
    master_df = master_df.dropna()
    
    if master_df.empty:
        print("No valid data after dropping NaNs.")
        return
        
    # Sort chronologically if a date column exists to avoid lookahead bias in train/test split
    if 'date' in master_df.columns:
        master_df = master_df.sort_values('date')
        
    cols_to_drop = ['target_3pct_5d', 'date', 'ticker', 'symbol']
    feature_cols = [c for c in master_df.columns if c not in cols_to_drop]
    
    X = master_df[feature_cols]
    y = master_df['target_3pct_5d']
    
    # Split into train/test (80% train, 20% test)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Original training class distribution:\n{y_train.value_counts()}")
    
    # Apply SMOTE to fix class imbalance
    smote = SMOTE(random_state=42)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train, y_train)
    
    print(f"Resampled training class distribution:\n{y_train_resampled.value_counts()}")
    
    # Train an xgboost.XGBClassifier
    model = xgb.XGBClassifier(eval_metric='logloss', random_state=42)
    model.fit(X_train_resampled, y_train_resampled)
    
    # Feature Importances Log
    importances = model.feature_importances_
    feature_imp_df = pd.DataFrame({'Feature': feature_cols, 'Importance': importances})
    feature_imp_df = feature_imp_df.sort_values(by='Importance', ascending=False)
    
    print("\n--- Feature Importances ---")
    print(feature_imp_df.to_string(index=False))
    
    # Save the feature importances to a log file
    os.makedirs('logs', exist_ok=True)
    feature_imp_df.to_csv('logs/feature_importance.log', index=False)
    
    # Create models directory and save
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, 'models/xgb_model.joblib')
    print("\nModel trained successfully and saved to models/xgb_model.joblib")

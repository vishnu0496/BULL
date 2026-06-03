# ml_ensemble.py
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class MLBreakoutEnsemble:
    def __init__(self):
        self.xgb_model = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, eval_metric='logloss')
        self.rf_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # Calculate robust predictive features without lookahead bias
        df = df.copy()
        
        # Returns and Momentum
        df['return_1d'] = df['Close'].pct_change()
        df['return_5d'] = df['Close'].pct_change(5)
        
        # Volatility & ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr_20'] = true_range.rolling(20).mean()
        df['natr'] = df['atr_20'] / df['Close']
        
        # Volume features
        df['vol_sma20'] = df['Volume'].rolling(20).mean()
        df['rvol'] = df['Volume'] / (df['vol_sma20'] + 1e-8)
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Trend / Moving average distance
        df['sma_50'] = df['Close'].rolling(50).mean()
        df['sma_200'] = df['Close'].rolling(200).mean()
        df['dist_sma50'] = (df['Close'] - df['sma_50']) / df['sma_50']
        df['dist_sma200'] = (df['Close'] - df['sma_200']) / df['sma_200']
        
        # Temporal lags (Simulates sequence model behavior safely)
        for lag in [1, 2, 3, 5]:
            df[f'rsi_lag_{lag}'] = df['rsi_14'].shift(lag)
            df[f'rvol_lag_{lag}'] = df['rvol'].shift(lag)
            df[f'return_lag_{lag}'] = df['return_1d'].shift(lag)
            
        return df.dropna()

    def generate_labels(self, df: pd.DataFrame, target_r: float = 2.0) -> pd.Series:
        # Labels breakouts: 1 if price reaches entry + (target_r * ATR) before hitting entry - 1 * ATR
        labels = []
        close = df['Close'].values
        atr = df['atr_20'].values
        
        for i in range(len(df)):
            if i >= len(df) - 5:
                labels.append(0)
                continue
            
            entry_price = close[i]
            stop_loss = entry_price - atr[i]
            take_profit = entry_price + (target_r * atr[i])
            
            triggered = 0
            for step in range(1, 6):
                future_high = df['High'].values[i + step]
                future_low = df['Low'].values[i + step]
                
                if future_low <= stop_loss:
                    triggered = 0
                    break
                if future_high >= take_profit:
                    triggered = 1
                    break
            labels.append(triggered)
            
        return pd.Series(labels, index=df.index)

    def train_walk_forward(self, df: pd.DataFrame):
        # Train models using strict temporal sequencing to prevent lookahead leakage
        df_feats = self.calculate_indicators(df)
        labels = self.generate_labels(df_feats)
        
        feature_cols = [col for col in df_feats.columns if 'lag' in col or col in 
                        ['rsi_14', 'rvol', 'dist_sma50', 'dist_sma200', 'natr']]
        
        X = df_feats[feature_cols]
        y = labels
        
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        self.xgb_model.fit(X_train_scaled, y_train)
        self.rf_model.fit(X_train_scaled, y_train)
        self.is_trained = True
        print("[ML Engine] Out-of-Sample Walk-Forward Training Completed.")

    def predict_prob_scaled(self, X_scaled) -> np.ndarray:
        xgb_probs = self.xgb_model.predict_proba(X_scaled)[:, 1]
        rf_probs = self.rf_model.predict_proba(X_scaled)[:, 1]
        return (0.6 * xgb_probs) + (0.4 * rf_probs)

    def predict_latest(self, df: pd.DataFrame) -> float:
        if not self.is_trained:
            return 0.50
        df_feats = self.calculate_indicators(df)
        if len(df_feats) == 0:
            return 0.50
        
        feature_cols = [col for col in df_feats.columns if 'lag' in col or col in 
                        ['rsi_14', 'rvol', 'dist_sma50', 'dist_sma200', 'natr']]
        
        latest_row = df_feats[feature_cols].tail(1)
        latest_scaled = self.scaler.transform(latest_row)
        prob = self.predict_prob_scaled(latest_scaled)[0]
        return float(prob)

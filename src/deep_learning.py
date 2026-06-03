import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import TensorDataset, DataLoader
import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import StandardScaler

from src.database import get_watchlist_tickers, get_prices
from src.ml_model import engineer_features

# Global cache for LSTM model and scaler
_LSTM_MODEL = None
_LSTM_SCALER_DATA = None


class PriceLSTM(nn.Module):
    """
    LSTM Neural Network for Price/Trend forecasting.
    Takes sequenced multi-feature inputs and outputs the probability of success.
    """
    def __init__(self, input_dim, hidden_dim=64, num_layers=2, dropout=0.2):
        super(PriceLSTM, self).__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_dim, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x, return_logits=False):
        # x shape: (batch_size, sequence_length, input_dim)
        lstm_out, _ = self.lstm(x)
        # Take the output of the last sequence step
        last_out = lstm_out[:, -1, :]
        last_out = self.dropout(last_out)
        logits = self.fc(last_out)
        if return_logits:
            return logits
        return self.sigmoid(logits)


def train_lstm_model(epochs=20, lr=0.001, seq_length=10, hidden_dim=64, num_layers=2, dropout=0.2, batch_size=32):
    """
    Fetches watchlist prices, engineers features, scales inputs,
    sequences data using sliding window, trains an LSTM model, and saves weights/scaler.
    """
    tickers = get_watchlist_tickers()
    if not tickers:
        print("No tickers found in watchlist database. Training aborted.")
        return
        
    all_dfs = []
    
    # 1. Fetch prices and engineer features
    for ticker in tickers:
        df = get_prices(ticker)
        if df is None or df.empty:
            continue
        
        df_feat = engineer_features(df)
        if df_feat is None or df_feat.empty:
            continue
            
        df_feat['ticker'] = ticker
        all_dfs.append(df_feat)
        
    if not all_dfs:
        print("No data available for training.")
        return
        
    # Combine to extract the dynamic feature columns list
    master_df = pd.concat(all_dfs, ignore_index=True)
    cols_to_drop = ['target_3pct_5d', 'date', 'ticker', 'symbol']
    feature_cols = [c for c in master_df.columns if c not in cols_to_drop]
    
    # Preprocess and clean individual dataframes per ticker to prevent leakage/cross-over
    cleaned_dfs = []
    for df_feat in all_dfs:
        cols_to_check = feature_cols + ['target_3pct_5d']
        df_clean = df_feat.dropna(subset=cols_to_check).copy()
        if len(df_clean) >= seq_length:
            cleaned_dfs.append(df_clean)
            
    if not cleaned_dfs:
        print("No tickers have sufficient history for the sequence length.")
        return
        
    # Fit the scaler on the combined training set features
    all_features_df = pd.concat([df[feature_cols] for df in cleaned_dfs], ignore_index=True)
    scaler = StandardScaler()
    scaler.fit(all_features_df)
    
    # Create sequences per ticker to avoid crossover leaks between tickers
    X_list = []
    y_list = []
    
    for df in cleaned_dfs:
        scaled_features = scaler.transform(df[feature_cols])
        y_vals = df['target_3pct_5d'].values
        
        for i in range(seq_length - 1, len(df)):
            X_list.append(scaled_features[i - seq_length + 1 : i + 1])
            y_list.append(y_vals[i])
            
    if not X_list:
        print("No sequence data could be generated.")
        return
        
    X_train = np.array(X_list, dtype=np.float32)
    y_train = np.array(y_list, dtype=np.float32).reshape(-1, 1)
    
    print(f"Dataset sequenced. X shape: {X_train.shape}, y shape: {y_train.shape}")
    
    input_dim = len(feature_cols)
    model = PriceLSTM(input_dim=input_dim, hidden_dim=hidden_dim, num_layers=num_layers, dropout=dropout)
    
    # Using BCEWithLogitsLoss for numerical stability during training
    criterion = nn.BCEWithLogitsLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)
    
    dataset = TensorDataset(torch.tensor(X_train), torch.tensor(y_train))
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
    
    model.train()
    print("Starting LSTM training pipeline...")
    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch_X, batch_y in dataloader:
            optimizer.zero_grad()
            logits = model(batch_X, return_logits=True)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * batch_X.size(0)
            
        epoch_loss /= len(dataset)
        print(f"Epoch {epoch+1:02d}/{epochs:02d} | Train Loss: {epoch_loss:.6f}")
        
    # Save model and metadata scaler pack
    os.makedirs('models', exist_ok=True)
    torch.save(model.state_dict(), 'models/lstm_model.pth')
    
    scaler_pack = {
        'scaler': scaler,
        'feature_cols': feature_cols,
        'seq_length': seq_length,
        'input_dim': input_dim,
        'hidden_dim': hidden_dim,
        'num_layers': num_layers,
        'dropout': dropout
    }
    joblib.dump(scaler_pack, 'models/lstm_scaler.joblib')
    print("Successfully saved weights to 'models/lstm_model.pth'")
    print("Successfully saved scaler and configuration metadata to 'models/lstm_scaler.joblib'")


def load_lstm_resources():
    """Loads and caches LSTM model weights and scaler from disk."""
    global _LSTM_MODEL, _LSTM_SCALER_DATA
    if _LSTM_MODEL is not None and _LSTM_SCALER_DATA is not None:
        return _LSTM_MODEL, _LSTM_SCALER_DATA
        
    model_path = 'models/lstm_model.pth'
    scaler_path = 'models/lstm_scaler.joblib'
    
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        raise FileNotFoundError("LSTM model files do not exist. Please train the model first.")
        
    scaler_pack = joblib.load(scaler_path)
    
    input_dim = scaler_pack['input_dim']
    hidden_dim = scaler_pack.get('hidden_dim', 64)
    num_layers = scaler_pack.get('num_layers', 2)
    dropout = scaler_pack.get('dropout', 0.2)
    
    model = PriceLSTM(input_dim=input_dim, hidden_dim=hidden_dim, num_layers=num_layers, dropout=dropout)
    model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
    model.eval()
    
    _LSTM_MODEL = model
    _LSTM_SCALER_DATA = scaler_pack
    return _LSTM_MODEL, _LSTM_SCALER_DATA


def predict_lstm_probability(ticker_df):
    """
    Predicts the probability of success for the latest window of the ticker dataframe.
    """
    if ticker_df is None or ticker_df.empty:
        raise ValueError("DataFrame is empty or None.")
        
    model, scaler_pack = load_lstm_resources()
    
    # Extract feature columns and sequence parameters
    feature_cols = scaler_pack['feature_cols']
    seq_length = scaler_pack['seq_length']
    
    # Calculate features on the input DataFrame
    df_feat = engineer_features(ticker_df)
    if df_feat is None or df_feat.empty:
        raise ValueError("Failed to engineer features for the provided ticker data.")
        
    # Drop rows that have NaN values in our active feature list
    df_clean = df_feat.dropna(subset=feature_cols).copy()
    if len(df_clean) < seq_length:
        raise ValueError(
            f"Not enough data history available after feature calculation. "
            f"Requires at least {seq_length} rows of non-NaN values, but got {len(df_clean)}."
        )
        
    # Take the latest sequence window
    latest_seq_df = df_clean.iloc[-seq_length:]
    
    # Scale features using the saved scaler
    scaled_features = scaler_pack['scaler'].transform(latest_seq_df[feature_cols])
    
    # Format shape to PyTorch sequence tensor (batch_size=1, sequence_length, input_dim)
    input_tensor = torch.tensor(scaled_features, dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        prob = model(input_tensor, return_logits=False)
        
    return float(prob.squeeze().item())

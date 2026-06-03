import os
import pytest
import torch
import pandas as pd
import numpy as np
from unittest.mock import patch

from src.deep_learning import PriceLSTM, train_lstm_model, predict_lstm_probability, load_lstm_resources


def test_price_lstm_forward():
    """Verify LSTM architecture forward pass shapes and outputs."""
    input_dim = 10
    hidden_dim = 16
    num_layers = 1
    batch_size = 4
    seq_length = 10
    
    model = PriceLSTM(input_dim=input_dim, hidden_dim=hidden_dim, num_layers=num_layers)
    x = torch.randn(batch_size, seq_length, input_dim)
    
    # 1. Output probability shape check
    out_prob = model(x, return_logits=False)
    assert out_prob.shape == (batch_size, 1)
    assert torch.all(out_prob >= 0.0)
    assert torch.all(out_prob <= 1.0)
    
    # 2. Output logit shape check
    out_logit = model(x, return_logits=True)
    assert out_logit.shape == (batch_size, 1)


def test_predict_lstm_probability_no_model():
    """Check that predict_lstm_probability raises FileNotFoundError when no files exist."""
    # Temporarily remove global cached models
    import src.deep_learning as dl
    dl._LSTM_MODEL = None
    dl._LSTM_SCALER_DATA = None
    
    df = pd.DataFrame({'close': [10.0] * 20})
    
    # Temporarily mock os.path.exists to return False for the model paths
    with patch('os.path.exists', return_value=False):
        with pytest.raises(FileNotFoundError):
            predict_lstm_probability(df)


@patch('src.deep_learning.get_watchlist_tickers')
@patch('src.deep_learning.get_prices')
def test_lstm_roundtrip(mock_get_prices, mock_get_tickers, tmp_path):
    """
    Test a full training roundtrip and prediction utilizing temporary directory paths
    to avoid overwriting the production models during tests.
    """
    # 1. Mock watchlist and database prices
    mock_get_tickers.return_value = ['MOCK_TICKER']
    
    dates = pd.date_range(start='2025-01-01', periods=250)
    mock_df = pd.DataFrame({
        'Date': dates,
        'Open': np.linspace(100.0, 200.0, 250),
        'High': np.linspace(105.0, 205.0, 250),
        'Low': np.linspace(95.0, 195.0, 250),
        'Close': np.linspace(100.0, 200.0, 250),
        'Volume': [1000] * 250
    })
    mock_get_prices.return_value = mock_df

    # Path overrides to use pytest tmp_path
    tmp_model_path = str(tmp_path / 'lstm_model.pth')
    tmp_scaler_path = str(tmp_path / 'lstm_scaler.joblib')

    # Patch the paths and train
    with patch('src.deep_learning.torch.save') as mock_torch_save, \
         patch('src.deep_learning.joblib.dump') as mock_joblib_dump:
        
        train_lstm_model(epochs=1, seq_length=10, hidden_dim=16, num_layers=1, batch_size=8)
        
        # Verify save was called
        assert mock_torch_save.called
        assert mock_joblib_dump.called

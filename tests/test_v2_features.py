# tests/test_v2_features.py
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from src.constants import is_nse_holiday
from api.server import serve_setup, detect_chat_id, setup_test_message, TelegramSetupBody

def test_is_nse_holiday():
    sat = datetime(2026, 6, 6) # Saturday
    sun = datetime(2026, 6, 7) # Sunday
    mon = datetime(2026, 6, 8) # Monday
    
    assert is_nse_holiday(sat) is True
    assert is_nse_holiday(sun) is True
    assert is_nse_holiday(mon) is False
    
    new_years = datetime(2026, 1, 26) # Republic Day
    christmas = datetime(2026, 12, 25) # Christmas
    assert is_nse_holiday(new_years) is True
    assert is_nse_holiday(christmas) is True

@pytest.mark.anyio
async def test_serve_setup():
    res = await serve_setup()
    # Should return a FileResponse or JSONResponse depending on setup.html existence
    assert res is not None

@pytest.mark.anyio
@patch("requests.get")
async def test_detect_chat_id_success(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {
                "message": {
                    "chat": {
                        "id": 123456789
                    }
                }
            }
        ]
    }
    mock_get.return_value = mock_resp
    
    res = await detect_chat_id("fake_token")
    assert res["success"] is True
    assert res["chat_id"] == "123456789"

@pytest.mark.anyio
@patch("requests.get")
async def test_detect_chat_id_failure(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "ok": False,
        "description": "Unauthorized"
    }
    mock_get.return_value = mock_resp
    
    res = await detect_chat_id("fake_token")
    assert res["success"] is False
    assert "error" in res

@pytest.mark.anyio
@patch("requests.post")
async def test_setup_test_message_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_post.return_value = mock_resp
    
    body = TelegramSetupBody(token="fake_token", chat_id="123456789")
    res = await setup_test_message(body)
    assert res["success"] is True

@pytest.mark.anyio
@patch("requests.post")
async def test_setup_test_message_failure(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    mock_post.return_value = mock_resp
    
    body = TelegramSetupBody(token="fake_token", chat_id="123456789")
    res = await setup_test_message(body)
    assert res["success"] is False
    assert "error" in res

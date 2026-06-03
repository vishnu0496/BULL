import json
import os
import threading
import time
import urllib.request
import urllib.error

GEMINI_SENTIMENT_ENABLE_ENV = "BULL_ENABLE_GEMINI_SENTIMENT"
GEMINI_SENTIMENT_MAX_CALLS_ENV = "BULL_GEMINI_SENTIMENT_MAX_CALLS"
GEMINI_SENTIMENT_DEFAULT_MAX_CALLS = 20
GEMINI_SENTIMENT_WINDOW_SECONDS = 24 * 60 * 60

_gemini_credit_lock = threading.Lock()
_gemini_credit_window_started = time.time()
_gemini_credit_calls = 0

# Dictionary of financial keywords and their weights
POSITIVE_WORDS = {
    "profit", "growth", "surpasses", "exceeds", "rise", "gain", "dividend", 
    "acquisition", "partnership", "success", "orders", "beat", "upgrade", 
    "bullish", "jump", "record", "highest", "advances", "rally", "positive",
    "favorable", "strong", "recovery", "expansion", "deal", "breakout", "surged"
}

NEGATIVE_WORDS = {
    "loss", "decrease", "fall", "decline", "drop", "lawsuit", "investigation", 
    "fine", "penalty", "deficit", "scam", "debt", "slumps", "downgrade", 
    "bearish", "investigate", "plunges", "crashes", "weak", "deficit", "dispute",
    "regulatory", "concerns", "alert", "cautions", "warns", "drop", "probe"
}

def _env_truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def _gemini_sentiment_enabled() -> bool:
    return _env_truthy(os.getenv(GEMINI_SENTIMENT_ENABLE_ENV))

def _gemini_credit_allowed() -> bool:
    """
    Conservative process-local governor. Gemini is local-only by default and,
    when explicitly enabled, capped to a small daily call budget.
    """
    if not _gemini_sentiment_enabled():
        return False

    try:
        max_calls = int(os.getenv(GEMINI_SENTIMENT_MAX_CALLS_ENV, GEMINI_SENTIMENT_DEFAULT_MAX_CALLS))
    except ValueError:
        max_calls = GEMINI_SENTIMENT_DEFAULT_MAX_CALLS

    if max_calls <= 0:
        return False

    global _gemini_credit_window_started, _gemini_credit_calls
    now = time.time()
    with _gemini_credit_lock:
        if now - _gemini_credit_window_started >= GEMINI_SENTIMENT_WINDOW_SECONDS:
            _gemini_credit_window_started = now
            _gemini_credit_calls = 0

        if _gemini_credit_calls >= max_calls:
            return False

        _gemini_credit_calls += 1
        return True

def analyze_sentiment_local(text: str) -> tuple[float, str]:
    """
    Determine sentiment score and label using a fast local financial dictionary.
    Returns:
        tuple[float, str]: (sentiment_score, sentiment_label)
        - score: float between -1.0 (very bearish) and +1.0 (very bullish)
        - label: 'BULLISH', 'BEARISH', or 'NEUTRAL'
    """
    words = text.lower().split()
    pos_count = 0
    neg_count = 0
    
    for word in words:
        # Strip punctuation
        w = word.strip(".,;:?!'\"()[]{}")
        if w in POSITIVE_WORDS:
            pos_count += 1
        elif w in NEGATIVE_WORDS:
            neg_count += 1
            
    total = pos_count + neg_count
    if total == 0:
        return 0.0, "NEUTRAL"
        
    score = (pos_count - neg_count) / total
    
    if score >= 0.15:
        label = "BULLISH"
    elif score <= -0.15:
        label = "BEARISH"
    else:
        label = "NEUTRAL"
        
    return round(score, 2), label

def analyze_sentiment_gemini(text: str, api_key: str) -> tuple[float, str]:
    """
    Determine sentiment score and label using Google Gemini 1.5 Flash.
    Returns:
        tuple[float, str]: (sentiment_score, sentiment_label)
    """
    if not api_key or not api_key.strip() or not _gemini_credit_allowed():
        return analyze_sentiment_local(text)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = (
        "You are a professional financial news analyst. "
        "Analyze the financial sentiment of this stock market headline. "
        "Provide your answer in strict JSON format with two keys:\n"
        "- 'verdict': must be either 'BULLISH', 'BEARISH', or 'NEUTRAL'\n"
        "- 'score': a decimal score from -1.0 (very bearish) to 1.0 (very bullish) explaining the intensity.\n\n"
        f"Headline: \"{text}\"\n\n"
        "Return ONLY the raw JSON object, no markdown, no ```json, no explanation."
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            res_data = response.read().decode("utf-8")
            res_json = json.loads(res_data)
            
            # Extract generated text
            candidates = res_json.get('candidates', [])
            if not candidates:
                raise ValueError("No candidates found in Gemini response")
            parts = candidates[0].get('content', {}).get('parts', [])
            if not parts:
                raise ValueError("No content parts found in Gemini response")
            text_response = parts[0].get('text', '').strip()
            
            clean_text = text_response
            if clean_text.startswith("```"):
                lines = clean_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_text = "\n".join(lines).strip()
                
            parsed = json.loads(clean_text)
            score = float(parsed.get('score', 0.0))
            label = str(parsed.get('verdict', 'NEUTRAL')).upper().strip()
            
            if label not in ['BULLISH', 'BEARISH', 'NEUTRAL']:
                label = 'NEUTRAL'
                
            return round(score, 2), label
            
    except Exception:
        # Fallback to local dictionary analysis if API fails
        return analyze_sentiment_local(text)

def get_text_sentiment(text: str, api_key: str = None) -> tuple[float, str]:
    """
    Analyzes financial sentiment. Uses local dictionary analysis by default.
    Gemini requires BULL_ENABLE_GEMINI_SENTIMENT=true and is capped by
    BULL_GEMINI_SENTIMENT_MAX_CALLS per process-day.
    """
    if api_key and api_key.strip() and _gemini_sentiment_enabled():
        try:
            return analyze_sentiment_gemini(text, api_key)
        except Exception:
            return analyze_sentiment_local(text)
    return analyze_sentiment_local(text)

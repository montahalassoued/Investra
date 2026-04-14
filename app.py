from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
from typing import List
import logging
import sys
import os
import json
import re
from threading import Lock

from litellm import completion

# Add src directory to Python path so Investra module can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from Investra.agents import (
    analyze_stocks_with_timing,
    get_market_analysis,
    get_company_info,
    get_all_company_analyses,
    get_news_and_sentiment,
)
from Investra.cache import clear_history, get_conversation_history
from Investra.cache.redis_client import redis_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SymbolsRequest(BaseModel):
    symbols: List[str]


class HistoryRequest(BaseModel):
    symbols: List[str] | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str


CHAT_HISTORY_LIMIT = int(os.getenv("CHAT_HISTORY_LIMIT", "10"))
CHAT_HISTORY_TTL = int(os.getenv("CHAT_HISTORY_TTL", "3600"))
INVESTMENT_KEYWORDS = ("invest", "buy", "stock", "portfolio")

_memory_lock = Lock()
_in_memory_chat_store: dict[str, list[dict[str, str]]] = {}


def _chat_key(session_id: str) -> str:
    return f"chat:session:{session_id}"


def _normalize_message(content: str) -> str:
    return content.strip()


def _save_chat_message(session_id: str, role: str, content: str) -> None:
    message = {"role": role, "content": _normalize_message(content)}
    key = _chat_key(session_id)

    try:
        redis_client.rpush(key, json.dumps(message))
        redis_client.ltrim(key, -CHAT_HISTORY_LIMIT, -1)
        redis_client.expire(key, CHAT_HISTORY_TTL)
        return
    except Exception:
        pass

    with _memory_lock:
        items = _in_memory_chat_store.setdefault(session_id, [])
        items.append(message)
        if len(items) > CHAT_HISTORY_LIMIT:
            _in_memory_chat_store[session_id] = items[-CHAT_HISTORY_LIMIT:]


def _load_chat_history(session_id: str) -> list[dict[str, str]]:
    key = _chat_key(session_id)

    try:
        raw_items = redis_client.lrange(key, -CHAT_HISTORY_LIMIT, -1)
        parsed: list[dict[str, str]] = []
        for item in raw_items:
            try:
                payload = json.loads(item)
            except Exception:
                continue

            role = payload.get("role")
            content = payload.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                parsed.append({"role": role, "content": content})

        if parsed:
            return parsed
    except Exception:
        pass

    with _memory_lock:
        return list(_in_memory_chat_store.get(session_id, []))


def _is_investment_intent(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in INVESTMENT_KEYWORDS)


def _has_decision_context(message: str, history: list[dict[str, str]]) -> bool:
    combined = " ".join(
        [item.get("content", "") for item in history if item.get("role") == "user"] + [message]
    ).lower()

    risk_signals = ("low risk", "medium risk", "high risk", "risk tolerance")
    horizon_signals = (
        "short term",
        "long term",
        "1 year",
        "3 years",
        "5 years",
        "horizon",
    )

    has_risk = any(signal in combined for signal in risk_signals)
    has_horizon = any(signal in combined for signal in horizon_signals)
    return has_risk and has_horizon


def _extract_symbols(message: str) -> list[str]:
    aliases = {
        "APPLE": "AAPL",
        "MICROSOFT": "MSFT",
        "NVIDIA": "NVDA",
        "TESLA": "TSLA",
        "AMAZON": "AMZN",
        "GOOGLE": "GOOGL",
        "META": "META",
    }

    upper_message = message.upper()
    found: list[str] = []

    for company, ticker in aliases.items():
        if company in upper_message:
            found.append(ticker)

    tokens = re.findall(r"\b[A-Z]{1,5}\b", upper_message)
    skip = {
        "I", "A", "AN", "THE", "AND", "OR", "TO", "FOR", "IN", "ON",
        "BUY", "SELL", "WITH", "RISK", "LOW", "HIGH", "LONG", "TERM",
    }
    for token in tokens:
        if token not in skip:
            found.append(token)

    deduped: list[str] = []
    for symbol in found:
        if symbol not in deduped:
            deduped.append(symbol)

    return deduped[:5]


def _build_conversation_prompt(history: list[dict[str, str]], user_message: str):
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI investment advisor in a conversational chat. "
                "Be concise and practical. Ask follow-up questions when key details "
                "are missing (risk tolerance, timeline, goals, budget constraints). "
                "Do not always generate a full report. Provide progressive guidance."
            ),
        }
    ]

    for item in history[-CHAT_HISTORY_LIMIT:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})
    return messages


def _answer_with_conversation_llm(history: list[dict[str, str]], user_message: str) -> str:
    messages = _build_conversation_prompt(history, user_message)
    model = os.getenv("GROQ_MODEL", "groq/llama-3.3-70b-versatile")

    response = completion(
        model=model,
        messages=messages,
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.3,
    )

    content = response.choices[0].message.content if response.choices else ""
    if not isinstance(content, str) or not content.strip():
        return "Can you share a bit more context so I can guide you better?"
    return content.strip()


def _handle_chat_message(message: str, history: list[dict[str, str]]) -> str:
    if _is_investment_intent(message):
        symbols = _extract_symbols(message)
        if not symbols:
            return (
                "I can help with that investment decision. Which stock or ticker are you "
                "considering, and what is your risk tolerance and investment horizon?"
            )

        if not _has_decision_context(message, history):
            return (
                "Before I give a full recommendation, what is your risk tolerance "
                "(low/medium/high) and investment horizon (short-term or long-term)?"
            )

        return analyze_stocks_with_timing(symbols)

    return _answer_with_conversation_llm(history, message)


@app.post("/analyze")
def analyze(payload: SymbolsRequest):
    try:
        symbols = [s.upper().strip() for s in payload.symbols]
        return get_market_analysis(symbols)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/company/{symbol}")
def company(symbol: str):
    try:
        return get_company_info(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/company-analysis")
def company_analysis(payload: SymbolsRequest):
    try:
        symbols = [s.upper().strip() for s in payload.symbols]
        return get_all_company_analyses(symbols)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/news-sentiment")
def news_sentiment(payload: SymbolsRequest):
    try:
        symbols = [s.upper().strip() for s in payload.symbols]
        return get_news_and_sentiment(symbols)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    try:
        # Simple health check to ensure the app is running
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.post("/history")
def history(payload: HistoryRequest):
    try:
        symbols = [s.upper().strip() for s in payload.symbols] if payload.symbols else None
        return get_conversation_history(symbols)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/history")
def delete_history(payload: HistoryRequest):
    try:
        symbols = [s.upper().strip() for s in payload.symbols] if payload.symbols else None
        return {"deleted": clear_history(symbols)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
def chat(payload: ChatRequest):
    try:
        message = payload.message.strip()
        session_id = payload.session_id.strip()

        if not message:
            raise HTTPException(status_code=400, detail="message is required")
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id is required")

        history = _load_chat_history(session_id)
        _save_chat_message(session_id, "user", message)

        reply = _handle_chat_message(message, history)
        _save_chat_message(session_id, "assistant", reply)

        return {"response": reply}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat endpoint failed: {e}")
        raise HTTPException(status_code=500, detail="Chat processing failed")
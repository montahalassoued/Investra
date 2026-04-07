from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
from typing import List
import logging
from Investra.agents import (
    get_market_analysis,
    get_company_info,
    get_all_company_analyses,
    get_news_and_sentiment,
)
from Investra.cache import clear_history, get_conversation_history

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
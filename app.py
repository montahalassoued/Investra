from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
from typing import List
import logging
from stockify.agents import get_market_analysis, get_company_info, get_company_analysis, get_news_and_sentiment

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
        return get_company_analysis(symbols)
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
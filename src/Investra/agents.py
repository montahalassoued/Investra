import concurrent.futures
import logging
import os
import time
from threading import Lock
import yfinance as yf
from crewai import Agent, LLM
import pandas as pd
from .cache import get_cache, save_conversation, set_cache


# Threading & Logging

data_lock = Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# LLM

if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("GROQ_API_KEY is missing. Please set it in environment variables.")


llama_llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
)

# Helper — safe agent content extraction


def _extract(response) -> str:
    """Return text from an agent response regardless of its type."""
    if response is None:
        return ""
    if hasattr(response, "content"):
        return str(response.content)
    return str(response)


# MARKET ANALYST

market_analyst = Agent(
    role="Market Analyst",
    llm=llama_llm,
    goal="Analyze stock performance and compare stocks over time",
    backstory="Expert in financial markets and quantitative analysis",
    verbose=True,
)

def compare_stocks(symbols: list[str]) -> pd.DataFrame:
    try:
        cache_key = f"stocks:{'-'.join(symbols)}"

        cached = get_cache(cache_key)
        if cached:
            logger.info("[CACHE HIT] compare_stocks")
            return pd.DataFrame(cached)

        logger.info("[CACHE MISS] Fetching stock data")

        data = yf.download(symbols, period="6mo", group_by="ticker", auto_adjust=True)
        result = []

        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    close_prices = data["Close"].dropna()
                else:
                    close_prices = data[(symbol, "Close")].dropna()

                if close_prices.empty or len(close_prices) < 2:
                    continue

                pct = close_prices.pct_change().dropna()

                result.append({
                    "Symbol": symbol,
                    "Initial % Change": round(pct.iloc[0] * 100, 2),
                    "6-Month % Change": round((close_prices.iloc[-1] / close_prices.iloc[0] - 1) * 100, 2),
                    "Volatility (std %)": round(pct.std() * 100, 2),
                    "Max Drawdown %": round(((close_prices / close_prices.cummax()) - 1).min() * 100, 2),
                })

            except Exception as e:
                logger.error(f"{symbol}: {e}")

        df = pd.DataFrame(result).set_index("Symbol")

        # convert to dict before caching
        set_cache(cache_key, df.to_dict(), ttl=3600)

        return df

    except Exception as e:
        logger.error(e)
        return pd.DataFrame()

def get_market_analysis(symbols: list[str]) -> str:
    """Run market analyst agent with Redis caching."""
    try:
        cache_key = f"market_analysis:{'-'.join(symbols)}"

        #  check cache
        cached = get_cache(cache_key)
        if cached:
            logger.info(f"[CACHE HIT] market_analysis {symbols}")
            return cached

        logger.info(f"[CACHE MISS] Starting market analysis for: {symbols}")

        performance_data = compare_stocks(symbols)

        if performance_data.empty:
            return "No valid stock data found for the given symbols."

        formatted_table = performance_data.to_markdown()
        logger.info(f"Performance data:\n{formatted_table}")

        prompt = (
            "You are a professional equity analyst.\n\n"
            f"Stock Performance Data (6-month period):\n{formatted_table}\n\n"
            "Tasks:\n"
            "1. Compare and rank these stocks from best to worst performing.\n"
            "2. Reference the specific percentage numbers in your analysis.\n"
            "3. Comment on volatility and drawdown where relevant.\n"
            "4. Explain your ranking rationale clearly.\n"
            "Keep your response concise and data-driven."
        )

        analysis = market_analyst.kickoff(prompt)
        result = _extract(analysis)

        #  cache result
        set_cache(cache_key, result, ttl=3600)

        return result

    except Exception as e:
        logger.error(f"Error in market analysis: {e}")
        return f"Error in market analysis: {e}"

# COMPANY RESEARCHER

company_researcher = Agent(
    role="Company Researcher",
    llm=llama_llm,
    goal="Research company fundamentals and business profiles",
    backstory="Financial researcher specialised in company profiling and fundamental analysis",
    verbose=True,
)


def get_company_info(symbol: str) -> dict:
    """Fetch key fundamentals from Yahoo Finance."""
    try:
        cache_key = f"company:{symbol}"
        #check cache
        cached = get_cache(cache_key)
        if cached:
            return cached
        #fetch from API(only if cache miss)
        logger.info(f"Fetching company info for {symbol}")
        stock = yf.Ticker(symbol)
        info = stock.get_info()

        summary = info.get("longBusinessSummary", "N/A")
        if summary and summary != " N/A":
            summary = summary[:600] + "..."

        result={
            "symbol": symbol,
            "name": info.get("longName", "N/A"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap", "N/A"),
            "pe_ratio": info.get("trailingPE", "N/A"),
            "eps": info.get("trailingEps", "N/A"),
            "dividend_yield": info.get("dividendYield", "N/A"),
            "52w_high": info.get("fiftyTwoWeekHigh", "N/A"),
            "52w_low": info.get("fiftyTwoWeekLow", "N/A"),
            "summary": summary,
        }
        #store in cache 

        set_cache(cache_key, result, ttl=86400)

        return result

    except Exception as e:
        logger.error(f"Error fetching company info for {symbol}: {e}")
        return {k: "N/A" for k in [
            "symbol", "name", "sector", "industry", "market_cap",
            "pe_ratio", "eps", "dividend_yield", "52w_high", "52w_low", "summary"
        ]} | {"symbol": symbol}


def get_all_company_analyses(symbols: list[str]) -> dict[str, str]:
    """Fetch and summarise company information for each symbol."""
    analyses: dict[str, str] = {}
    for symbol in symbols:
        try:
            info = get_company_info(symbol)
            prompt = (
                f"Analyse this company profile for **{symbol}** and provide a concise fundamental summary.\n\n"
                f"Name:          {info['name']}\n"
                f"Sector:        {info['sector']}\n"
                f"Industry:      {info['industry']}\n"
                f"Market Cap:    {info['market_cap']}\n"
                f"P/E Ratio:     {info['pe_ratio']}\n"
                f"EPS:           {info['eps']}\n"
                f"Dividend Yield:{info['dividend_yield']}\n"
                f"52w High/Low:  {info['52w_high']} / {info['52w_low']}\n"
                f"Description:   {info['summary']}\n\n"
                "Provide a 3–4 sentence summary covering: business model, financial health, competitive positioning."
            )
            result = company_researcher.kickoff(prompt)
            analyses[symbol] = _extract(result)
        except Exception as e:
            logger.error(f"Error in company analysis for {symbol}: {e}")
            analyses[symbol] = f"Error analysing {symbol}: {e}"
    return analyses



# NEWS & SENTIMENT ANALYST  (new agent)


news_sentiment_analyst = Agent(
    role="News & Sentiment Analyst",
    llm=llama_llm,
    goal=(
        "Retrieve recent news headlines for each stock, score market sentiment "
        "(Bullish / Neutral / Bearish), identify key catalysts, and forecast "
        "the likely short-term market mood."
    ),
    backstory=(
        "Financial journalist and quantitative sentiment researcher with 15 years "
        "of experience reading market signals from news flows, earnings calls, "
        "analyst upgrades/downgrades, and macro events. You have a sharp instinct "
        "for separating noise from genuine market-moving catalysts."
    ),
    verbose=True,
)


def get_recent_news(symbol: str, max_items: int = 10) -> list[dict]:
    """
    Pull recent news items from Yahoo Finance with Redis cache.
    """
    try:
        cache_key = f"news:{symbol}:{max_items}"

        # check cache
        cached = get_cache(cache_key)
        if cached:
            logger.info(f"[CACHE HIT] news {symbol}")
            return cached

        logger.info(f"[CACHE MISS] Fetching news for {symbol}")

        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []

        items = []
        for article in raw_news[:max_items]:
            content = article.get("content", {})

            title = content.get("title", article.get("title", "N/A"))
            publisher = (
                content.get("provider", {}).get("displayName")
                or article.get("publisher", "N/A")
            )
            pub_time = content.get("pubDate") or article.get("providerPublishTime", "N/A")
            link = (
                content.get("canonicalUrl", {}).get("url")
                or article.get("link", "N/A")
            )

            items.append({
                "title": title,
                "publisher": publisher,
                "link": link,
                "publish_time": pub_time
            })

        set_cache(cache_key, items, ttl=3600)

        logger.info(f"Fetched {len(items)} news items for {symbol}")
        return items

    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []


def _format_headlines(symbol: str, news_items: list[dict]) -> str:
    if not news_items:
        return f"No recent news found for {symbol}."
    lines = [f"Recent headlines for **{symbol}**:"]
    for i, item in enumerate(news_items, 1):
        lines.append(f"  {i}. [{item['title']}] — {item['publisher']} ({item['publish_time']})")
    return "\n".join(lines)


def get_news_and_sentiment(symbols: list[str]) -> dict[str, str]:
    """
    Cached sentiment analysis per symbol.
    """
    results: dict[str, str] = {}

    for symbol in symbols:
        try:
            cache_key = f"sentiment:{symbol}"

            #  check cache
            cached = get_cache(cache_key)
            if cached:
                logger.info(f"[CACHE HIT] sentiment {symbol}")
                results[symbol] = cached
                continue

            logger.info(f"[CACHE MISS] Sentiment analysis for {symbol}")

            news_items = get_recent_news(symbol)
            headlines_block = _format_headlines(symbol, news_items)

            prompt = (
                "You are a professional news and market-sentiment analyst.\n\n"
                f"{headlines_block}\n\n"
                "Based on these headlines, provide:\n"
                "1. **Sentiment Score**: Bullish  / Neutral  / Bearish  with confidence.\n"
                "2. **Key Catalysts**: 2–3 important headlines and why they matter.\n"
                "3. **Market Mood Forecast**: 2–3 sentences.\n"
                "4. **Risk Flags**.\n"
            )

            response = news_sentiment_analyst.kickoff(prompt)
            result = _extract(response)

            # cache sentiment (TTL: 1 hour or more)
            set_cache(cache_key, result, ttl=3600)

            results[symbol] = result
            logger.info(f"Sentiment analysis completed for {symbol}")

        except Exception as e:
            logger.error(f"Error in news/sentiment for {symbol}: {e}")
            results[symbol] = f"Error analysing news for {symbol}: {e}"

    return results


def get_aggregated_market_sentiment(symbols: list[str], individual_sentiments: dict[str, str]) -> str:
    """
    After per-stock sentiment is collected, ask the agent for a macro-level
    market mood summary across all analysed stocks.
    """
    try:
        combined = "\n\n".join(
            f"### {sym}\n{sentiment}"
            for sym, sentiment in individual_sentiments.items()
        )

        prompt = (
            "You are a senior market strategist reviewing sentiment signals across a portfolio.\n\n"
            f"Per-stock sentiment reports:\n{combined}\n\n"
            "Provide a **Market Mood Synthesis** (5–7 sentences) covering:\n"
            "- Overall sentiment across the portfolio (Bullish / Mixed / Bearish)\n"
            "- Common macro themes or sector-wide risks appearing across stocks\n"
            "- Which stocks carry the strongest positive/negative sentiment momentum\n"
            "- One contrarian signal worth monitoring\n"
            "Keep it strategic and actionable."
        )

        response = news_sentiment_analyst.kickoff(prompt)
        return _extract(response)

    except Exception as e:
        logger.error(f"Error in aggregated sentiment: {e}")
        return f"Error generating market mood synthesis: {e}"



# STOCK STRATEGIST


stock_strategist = Agent(
    role="Stock Strategist",
    llm=llama_llm,
    goal="Provide data-driven investment recommendations based on multi-source analysis",
    backstory="Senior portfolio manager with expertise in blending quantitative data, "
              "fundamentals, and sentiment to make investment decisions",
    verbose=True,
)

# alias kept for backward compatibility
strategy_agent = stock_strategist


def get_stock_recommendations(
    symbols: list[str],
    market_analysis: str | None = None,
    company_data: dict | None = None,
    sentiment_data: dict | None = None,
) -> str:
    """Generate investment recommendations integrating all analyses."""
    try:
        logger.info(f"Generating stock recommendations for {symbols}")

        if market_analysis is None:
            market_analysis = get_market_analysis(symbols)
        if company_data is None:
            company_data = get_all_company_analyses(symbols)
        if sentiment_data is None:
            sentiment_data = get_news_and_sentiment(symbols)

        # Build prompt
        prompt = (
            f"Based on the following multi-source analysis, provide investment "
            f"recommendations for: {', '.join(symbols)}\n\n"
            f"─── Market Performance Analysis ───\n{market_analysis[:1200]}\n\n"
            f"─── Company Fundamentals ───\n"
        )
        for sym, analysis in company_data.items():
            prompt += f"**{sym}**: {analysis[:350]}\n\n"

        prompt += "─── News & Sentiment ───\n"
        for sym, sentiment in sentiment_data.items():
            prompt += f"**{sym}**: {sentiment[:350]}\n\n"

        prompt += (
            "Provide:\n"
            "1. **Individual Recommendation** for each stock (Buy / Hold / Sell) with brief rationale.\n"
            "2. **Risk Assessment** per stock (Low / Medium / High).\n"
            "3. **Portfolio Allocation Suggestion** if investing across all stocks.\n"
            "4. **Top Pick** — your single best idea with a clear thesis.\n"
            "Keep the response concise, structured, and actionable."
        )

        response = stock_strategist.kickoff(prompt)
        result = _extract(response)
        logger.info("Stock recommendations completed")
        return result

    except Exception as e:
        logger.error(f"Error in stock recommendations: {e}")
        return f"Error generating recommendations: {e}"



#TEAM LEAD


team_lead = Agent(
    role="Team Lead",
    llm=llama_llm,
    goal="Aggregate all analyses into a single, coherent, actionable investment report",
    backstory=(
        "Chief Investment Officer who synthesises quantitative data, fundamental research, "
        "news sentiment, and strategic recommendations into polished, investor-grade reports."
    ),
    verbose=True,
)


def get_final_investment_report(symbols: list[str]) -> str:
    """
    Orchestrate all agents (in parallel where possible) and produce a
    unified investment report via the Team Lead.
    """
    try:
        logger.info(f"Starting final report for {symbols}")
        parallel_results = run_agents_in_parallel(symbols)

        market_analysis      = parallel_results["market_analysis"]
        company_data         = parallel_results["company_data"]
        sentiment_data       = parallel_results["sentiment_data"]
        market_mood          = parallel_results["market_mood"]
        stock_recommendations = parallel_results["stock_recommendations"]

        # Format company block
        company_block = "\n".join(
            f"**{sym}**: {analysis}" for sym, analysis in company_data.items()
        )

        # Format sentiment block
        sentiment_block = "\n\n".join(
            f"**{sym}**:\n{sentiment}" for sym, sentiment in sentiment_data.items()
        )

        synthesis_prompt = (
            f"You are the Chief Investment Officer. Compile a professional investment report "
            f"for the following stocks: {', '.join(symbols)}.\n\n"
            f"Use this structure:\n"
            f"# Investment Report — {', '.join(symbols)}\n\n"
            f"## 1. Executive Summary\n"
            f"(3–4 sentences on the overall investment opportunity)\n\n"
            f"## 2. Market Performance Analysis\n"
            f"{market_analysis[:1000]}\n\n"
            f"## 3. Company Profiles\n"
            f"{company_block[:1200]}\n\n"
            f"## 4. News & Sentiment Analysis\n"
            f"{sentiment_block[:1200]}\n\n"
            f"## 5. Market Mood Outlook\n"
            f"{market_mood[:600]}\n\n"
            f"## 6. Investment Recommendations\n"
            f"{stock_recommendations[:1000]}\n\n"
            f"## 7. Conclusion & Action Points\n"
            f"(Bullet list of 3–5 concrete actions for an investor)\n\n"
            f"Keep the tone professional, concise, and data-backed. "
            f"This report is for a sophisticated retail investor."
        )

        final = team_lead.kickoff(synthesis_prompt)
        logger.info("Final report generation completed")
        return _extract(final)

    except Exception as e:
        logger.error(f"Error in final report generation: {e}")
        return f"Error generating final report: {e}"



#  PARALLEL EXECUTION ENGINE


def run_agents_in_parallel(symbols: list[str]) -> dict:
    """
    Execution plan
    ─────────────
    Stage 1 (parallel):  Market Analysis + Company Research + News Sentiment
    Stage 2 (parallel):  Market Mood Synthesis + Stock Recommendations
                         (both depend on Stage 1 outputs)
    """
    try:
        logger.info(f"Starting parallel execution for {symbols}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # ── Stage 1 ──
            f_market    = executor.submit(get_market_analysis, symbols)
            f_company   = executor.submit(get_all_company_analyses, symbols)
            f_sentiment = executor.submit(get_news_and_sentiment, symbols)

            market_analysis = f_market.result(timeout=120)
            company_data    = f_company.result(timeout=180)
            sentiment_data  = f_sentiment.result(timeout=120)

            logger.info("Stage 1 complete — launching Stage 2")

            # ── Stage 2 ──
            f_mood  = executor.submit(get_aggregated_market_sentiment, symbols, sentiment_data)
            f_recs  = executor.submit(
                get_stock_recommendations,
                symbols,
                market_analysis,
                company_data,
                sentiment_data,
            )

            market_mood           = f_mood.result(timeout=120)
            stock_recommendations = f_recs.result(timeout=120)

        logger.info("Parallel execution completed successfully")
        return {
            "market_analysis":      market_analysis,
            "company_data":         company_data,
            "sentiment_data":       sentiment_data,
            "market_mood":          market_mood,
            "stock_recommendations": stock_recommendations,
        }

    except concurrent.futures.TimeoutError:
        logger.error("Timeout during parallel execution")
        return {
            "market_analysis":       "Timeout error in market analysis",
            "company_data":          {s: f"Timeout for {s}" for s in symbols},
            "sentiment_data":        {s: f"Timeout for {s}" for s in symbols},
            "market_mood":           "Timeout error in market mood synthesis",
            "stock_recommendations": "Timeout error in stock recommendations",
        }
    except Exception as e:
        logger.error(f"Error in parallel execution: {e}")
        return {
            "market_analysis":       f"Error: {e}",
            "company_data":          {s: f"Error: {e}" for s in symbols},
            "sentiment_data":        {s: f"Error: {e}" for s in symbols},
            "market_mood":           f"Error: {e}",
            "stock_recommendations": f"Error: {e}",
        }



# PUBLIC ENTRY POINT


def analyze_stocks_with_timing(symbols: list[str]) -> str:
    """
    Main entry point.
    Runs the full multi-agent pipeline and returns the report with execution time.
    """
    start = time.time()
    logger.info(f"Starting stock analysis for: {symbols}")
    logger.info("=" * 60)

    try:
        report = get_final_investment_report(symbols)
        elapsed = round(time.time() - start, 2)
        save_conversation(
            symbols=symbols,
            analysis_type="final_report",
            result={"report": report, "execution_time_seconds": elapsed},
        )
        logger.info("=" * 60)
        logger.info(f"Analysis completed in {elapsed}s")
        return f"{report}\n\n---\n**⏱ Execution Time:** {elapsed}s (parallel processing)"

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        logger.error(f"Error in analyze_stocks_with_timing: {e}")
        save_conversation(
            symbols=symbols,
            analysis_type="final_report_failed",
            result={"error": str(e), "execution_time_seconds": elapsed},
        )
        return f"Error during analysis: {e}\n\n---\n** Execution Time:** {elapsed}s"
from collections.abc import Iterable

from .agents import analyze_stocks_with_timing


def run_crew(symbols: Iterable[str]) -> str:
    cleaned = [s.strip().upper() for s in symbols if s and s.strip()]
    if not cleaned:
        return "No symbols provided."
    return analyze_stocks_with_timing(cleaned)

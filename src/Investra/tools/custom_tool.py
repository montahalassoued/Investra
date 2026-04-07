from collections.abc import Iterable


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    return [s.strip().upper() for s in symbols if s and s.strip()]

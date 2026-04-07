import json
from datetime import datetime

from .redis_client import redis_client


def get_cache(key: str):
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception:
        return None


def set_cache(key: str, value, ttl: int = 3600):
    try:
        redis_client.set(key, json.dumps(value), ex=ttl)
        return True
    except Exception:
        return False


def _symbols_key(symbols: list[str]) -> str:
    cleaned = sorted({s.strip().upper() for s in symbols if s and s.strip()})
    return "-".join(cleaned)


def save_conversation(symbols: list[str], analysis_type: str, result, ttl: int = 2592000):
    try:
        symbols_key = _symbols_key(symbols)
        timestamp = datetime.utcnow().isoformat()
        payload = {
            "symbols": sorted({s.strip().upper() for s in symbols if s and s.strip()}),
            "analysis_type": analysis_type,
            "result": result,
            "timestamp": timestamp,
        }

        redis_client.setex(
            f"history:latest:{analysis_type}:{symbols_key}",
            ttl,
            json.dumps(payload),
        )
        redis_client.rpush(
            f"history:list:{symbols_key}",
            json.dumps(payload),
        )
        redis_client.expire(f"history:list:{symbols_key}", ttl)
        return True
    except Exception:
        return False


def get_conversation_history(symbols: list[str] | None = None, limit: int = 10):
    try:
        if symbols:
            key = f"history:list:{_symbols_key(symbols)}"
            items = redis_client.lrange(key, -limit, -1)
        else:
            keys = redis_client.keys("history:list:*")
            items = []
            for key in keys:
                items.extend(redis_client.lrange(key, -limit, -1))

        history = []
        for item in items:
            try:
                history.append(json.loads(item))
            except Exception:
                continue
        return history
    except Exception:
        return []


def clear_history(symbols: list[str] | None = None):
    try:
        if symbols:
            symbols_key = _symbols_key(symbols)
            keys = redis_client.keys(f"history:*:{symbols_key}")
        else:
            keys = redis_client.keys("history:*")
        if keys:
            return redis_client.delete(*keys)
        return 0
    except Exception:
        return 0
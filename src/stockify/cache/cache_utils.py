import json
from .redis_client import redis_client


def get_cache(key: str):
    data = redis_client.get(key)
    if data:
        print(f"[CACHE HIT] {key}")
        return json.loads(data)
    print(f"[CACHE MISS] {key}")
    return None


def set_cache(key: str, value, ttl: int = 3600):
    redis_client.set(key, json.dumps(value), ex=ttl)
import os
import time

_cache = {}


def _ttl():
    # Read at call time, so .env is already loaded by main.py.
    return float(os.getenv("ALOKASI_CACHE_TTL", "300"))


def cache_get(key):
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[1]:
        return hit[0]
    return None


def cache_set(key, value):
    _cache[key] = (value, time.monotonic() + _ttl())
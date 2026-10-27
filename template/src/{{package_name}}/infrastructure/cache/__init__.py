"""Valkey cache: the client and the generic `ValkeyCache` adapter (`valkey.py`).

Feature caches that implement domain ports live here too and wrap `ValkeyCache`; nothing
else in the service uses redis-py.
"""

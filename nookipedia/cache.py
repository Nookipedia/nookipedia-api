from flask_caching import Cache
from pylibmc import Client as PylibmcClient

_mc_client = PylibmcClient(["127.0.0.1"])
_mc_client.behaviors = {
    "connect_timeout": 1000,    # ms: give up if Memcached is unreachable
    "send_timeout": 1000000,    # μs (1s): don't block on writes
    "receive_timeout": 1000000, # μs (1s): don't block on reads
    "remove_failed": 1,         # pull server from pool after first failure
    "retry_timeout": 30,        # s: wait before retrying a removed server
    "dead_timeout": 30,         # s: time until a dead server is retried
}

cache = Cache(
    config={"CACHE_TYPE": "memcached", "CACHE_MEMCACHED_SERVERS": _mc_client}
)

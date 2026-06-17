from flask_caching import Cache
from pylibmc import Client as PylibmcClient

mc_client = PylibmcClient(["127.0.0.1"])
mc_client.behaviors = {
    "connect_timeout": 1000, # ms
    "send_timeout": 1000000, # μs (1s)
    "receive_timeout": 1000000, # μs (1s)
    "remove_failed": 1, # pull server from pool after failure
    "retry_timeout": 30, # 30s
    "dead_timeout": 30, # 30s
}

cache = Cache(config={"CACHE_TYPE": "memcached", "CACHE_MEMCACHED_SERVERS": mc_client})

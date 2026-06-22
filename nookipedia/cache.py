import threading

from flask_caching import Cache
from pylibmc import Client as PylibmcClient

SERVERS = ["127.0.0.1"]
BEHAVIORS = {
    "connect_timeout": 1000,  # ms
    "send_timeout": 1000000,  # μs (1s)
    "receive_timeout": 1000000,  # μs (1s)
    "remove_failed": 1,  # pull server from pool after failure
    "retry_timeout": 30,  # 30s
    "dead_timeout": 30,  # 30s
}


def build_client():
    client = PylibmcClient(SERVERS)
    client.behaviors = BEHAVIORS
    return client


class ThreadLocalClient:
    # One pylibmc client per thread.

    def __init__(self):
        self.local = threading.local()

    @property
    def client(self):
        if getattr(self.local, "client", None) is None:
            self.local.client = build_client()
        return self.local.client

    def __getattr__(self, name):
        return getattr(self.client, name)

    def disconnect_all(self):
        # Reset this thread's connections after a fork.
        if getattr(self.local, "client", None) is not None:
            self.local.client.disconnect_all()


mc_client = ThreadLocalClient()

cache = Cache(config={"CACHE_TYPE": "memcached", "CACHE_MEMCACHED_SERVERS": mc_client})

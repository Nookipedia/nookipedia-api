from flask_caching import Cache
from pylibmc import Client as PylibmcClient

cache = Cache(config={
    'CACHE_TYPE': 'memcached',
    'CACHE_MEMCACHED_SERVERS': PylibmcClient(['127.0.0.1'])
})

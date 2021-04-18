import configparser


config = configparser.ConfigParser()
config.read('config.ini')

BASE_URL_WIKI = config.get('APP', 'BASE_URL_WIKI')
BASE_URL_API = config.get('APP', 'BASE_URL_API')
BOT_USERNAME = config.get('AUTH', 'BOT_USERNAME')
BOT_PASS = config.get('AUTH', 'BOT_PASS')
DATABASE = config.get('DB', 'DATABASE')
DB_KEYS = config.get('DB', 'DB_KEYS')
DB_ADMIN_KEYS = config.get('DB', 'DB_ADMIN_KEYS')
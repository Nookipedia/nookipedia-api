import configparser


config = configparser.ConfigParser()
config.read("config.ini")

BASE_URL_WIKI = config.get("APP", "BASE_URL_WIKI")
BASE_URL_API = config.get("APP", "BASE_URL_API")
BOT_USERNAME = config.get("AUTH", "BOT_USERNAME")
BOT_PASS = config.get("AUTH", "BOT_PASS")
DATABASE = config.get("DB", "DATABASE")
DB_KEYS = config.get("DB", "DB_KEYS")
DB_ADMIN_KEYS = config.get("DB", "DB_ADMIN_KEYS")

limits = configparser.ConfigParser()
limits.read("limits.ini")

ART_LIMIT = limits.get("CARGO", "ART")
BUG_LIMIT = limits.get("CARGO", "BUG")
CLOTHING_LIMIT = limits.get("CARGO", "CLOTHING")
CLOTHING_VARIATION_LIMIT = limits.get("CARGO", "CLOTHING_VARIATION")
EVENT_LIMIT = limits.get("CARGO", "EVENT")
FISH_LIMIT = limits.get("CARGO", "FISH")
FOSSIL_GROUP_LIMIT = limits.get("CARGO", "FOSSIL_GROUP")
FOSSIL_INDIVIDUAL_LIMIT = limits.get("CARGO", "FOSSIL_INDIVIDUAL")
FURNITURE_LIMIT = limits.get("CARGO", "FURNITURE")
FURNITURE_VARIATION_LIMIT = limits.get("CARGO", "FURNITURE_VARIATION")
GYROID_LIMIT = limits.get("CARGO", "GYROID")
GYROID_VARIATION_LIMIT = limits.get("CARGO", "GYROID_VARIATION")
INTERIOR_LIMIT = limits.get("CARGO", "INTERIOR")
ITEMS_LIMIT = limits.get("CARGO", "ITEMS")
PHOTO_LIMIT = limits.get("CARGO", "PHOTO")
PHOTO_VARIATION_LIMIT = limits.get("CARGO", "PHOTO_VARIATION")
RECIPE_LIMIT = limits.get("CARGO", "RECIPE")
SEA_LIMIT = limits.get("CARGO", "SEA")
TOOL_LIMIT = limits.get("CARGO", "TOOL")
TOOL_VARIATION_LIMIT = limits.get("CARGO", "TOOL_VARIATION")
VILLAGER_LIMIT = limits.get("CARGO", "VILLAGER")

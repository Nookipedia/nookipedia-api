import sqlite3
from flask import g
from nookipedia.config import DATABASE


# Connect to the database:
def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


# Close database connection at end of request:
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


# Query database:
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


# Insert into database:
def insert_db(query, args=()):
    cur = get_db().execute(query, args)
    get_db().commit()
    cur.close()

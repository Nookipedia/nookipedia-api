from flask import request
import flask_monitoringdashboard as dashboard
from nookipedia import db
from nookipedia.config import config, DB_KEYS

DASHBOARD_CONFIGS = config.get("APP", "DASHBOARD_CONFIGS")


def configure_dashboard(app):
    def group_by_user():
        # Grab UUID from header or query param
        if request.headers.get("X-API-KEY"):
            request_uuid = request.headers.get("X-API-KEY")
        elif request.args.get("api_key"):
            request_uuid = request.args.get("api_key")

        # Check db for project details:
        row = db.query_db(
            "SELECT key, email, project FROM " + DB_KEYS + " WHERE key = ?",
            [request_uuid],
            one=True,
        )
        # If project details exist, use that as group_by; else, just use UUID
        if row[2]:
            return str(row[2] + " (" + row[0] + ")")
        else:
            return row[0]

    dashboard.config.group_by = group_by_user
    dashboard.config.init_from(file=DASHBOARD_CONFIGS)
    dashboard.bind(app)

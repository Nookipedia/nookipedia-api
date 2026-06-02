from flask import request
import flask_monitoringdashboard as dashboard
from nookipedia import db
from nookipedia.config import config, DB_KEYS

DASHBOARD_CONFIGS = config.get("APP", "DASHBOARD_CONFIGS")


def configure_dashboard(app):
    def group_by_user():
        # Grab UUID from header or query param
        request_uuid = request.headers.get("X-API-KEY") or request.args.get("api_key")
        if not request_uuid:
            return "unauthenticated"

        # Check db for project details:
        row = db.query_db(
            "SELECT key, email, project FROM " + DB_KEYS + " WHERE key = ?",
            [request_uuid],
            one=True,
        )
        
        # If project details exist, use that as group_by; else, just use UUID
        if row and row[2]:
            return str(row[2] + " (" + row[0] + ")")
        elif row:
            return row[0]
        else:
            return request_uuid

    dashboard.config.group_by = group_by_user
    dashboard.config.init_from(file=DASHBOARD_CONFIGS)
    dashboard.bind(app)

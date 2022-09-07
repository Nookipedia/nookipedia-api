from flask import request, Blueprint

from nookipedia.config import DB_KEYS, EVENT_LIMIT
from nookipedia.middlewares import authorize
from nookipedia.cargo import get_event_list
from nookipedia.utility import generate_fields


router = Blueprint("events", __name__)


@router.route("/nh/events", methods=["GET"])
def get_nh_event_all():
    authorize(DB_KEYS, request)

    limit = EVENT_LIMIT
    tables = "nh_calendar"
    fields = generate_fields("event", "date", "type", "link=url")
    orderby = "date"

    return get_event_list(limit, tables, fields, orderby)

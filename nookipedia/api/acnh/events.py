from flask import request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import get_event_list


router = Blueprint("events", __name__)


@router.route("/nh/events", methods=["GET"])
def get_nh_event_all():
    authorize(DB_KEYS, request)

    limit = "1200"
    tables = "nh_calendar"
    fields = "event,date,type,link=url"
    orderby = "date"

    return get_event_list(limit, tables, fields, orderby)

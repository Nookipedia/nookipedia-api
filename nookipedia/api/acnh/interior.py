import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_interior_list
from nookipedia.errors import error_response
from nookipedia.models import format_interior


router = Blueprint("interior", __name__)


@router.route("/nh/interior/<string:interior>", methods=["GET"])
def get_nh_interior(interior):
    authorize(DB_KEYS, request)

    interior = requests.utils.unquote(interior).replace("_", " ")
    limit = "1"
    tables = "nh_interior"
    fields = "_pageName=url,en_name=name,image_url,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,grid_size,color1,color2,version_added,unlocked,notes"
    where = f'en_name="{interior}"'
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "where": where,
        "limit": limit,
    }

    cargo_results = call_cargo(params, request.args)
    if len(cargo_results) == 0:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}",
            ),
        )
    else:
        return jsonify(format_interior(cargo_results[0]))


@router.route("/nh/interior", methods=["GET"])
def get_nh_interior_all():
    authorize(DB_KEYS, request)

    limit = "650"
    tables = "nh_interior"
    fields = "_pageName=url,en_name=name,image_url,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,grid_size,color1,color2,version_added,unlocked,notes"

    return get_interior_list(limit, tables, fields)

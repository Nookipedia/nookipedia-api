import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_other_item_list
from nookipedia.errors import error_response
from nookipedia.models import format_other_item
from nookipedia.utility import generate_fields


router = Blueprint("items", __name__)


@router.route("/nh/items/<string:item>", methods=["GET"])
def get_nh_item(item):
    authorize(DB_KEYS, request)

    item = requests.utils.unquote(item).replace("_", " ")
    limit = "1"
    tables = "nh_item"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "stack",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "sell",
        "is_fence",
        "material_type",
        "material_seasonality",
        "material_sort",
        "material_name_sort",
        "material_seasonality_sort",
        "edible",
        "plant_type",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "availability3",
        "availability3_note",
        "version_added",
        "unlocked",
        "notes",
    )
    where = f'en_name="{item}"'
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
        return jsonify(format_other_item(cargo_results[0]))


@router.route("/nh/items", methods=["GET"])
def get_nh_item_all():
    authorize(DB_KEYS, request)

    limit = "400"
    tables = "nh_item"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "stack",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "sell",
        "is_fence",
        "material_type",
        "material_seasonality",
        "material_sort",
        "material_name_sort",
        "material_seasonality_sort",
        "edible",
        "plant_type",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "availability3",
        "availability3_note",
        "version_added",
        "unlocked",
        "notes",
    )

    return get_other_item_list(limit, tables, fields)

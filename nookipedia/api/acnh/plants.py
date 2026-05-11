import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS, PLANT_LIMIT
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_plants_list
from nookipedia.errors import error_response
from nookipedia.models import format_plant
from nookipedia.utility import generate_fields


router = Blueprint("items", __name__)


@router.route("/nh/plants/<string:item>", methods=["GET"])
def get_nh_plant(plant):
    authorize(DB_KEYS, request)

    plant = requests.utils.unquote(plant).replace("_", " ")
    limit = "1"
    tables = "nh_plants"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "sell",
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
    where = f'en_name="{plant}"'
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
        return jsonify(format_plant(cargo_results[0]))


@router.route("/nh/plants", methods=["GET"])
def get_nh_plants_all():
    authorize(DB_KEYS, request)

    limit = ITEMS_LIMIT
    tables = "nh_item"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "sell",
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

    return get_plants_list(limit, tables, fields)

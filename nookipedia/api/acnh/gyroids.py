import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS, GYROID_LIMIT, GYROID_VARIATION_LIMIT
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_gyroid_list, get_variation_list
from nookipedia.errors import error_response
from nookipedia.models import format_gyroid, stitch_variation, stitch_variation_list
from nookipedia.utility import generate_fields


router = Blueprint("gyroids", __name__)


@router.route("/nh/gyroids/<string:gyroid>", methods=["GET"])
def get_nh_gyroid(gyroid):
    authorize(DB_KEYS, request)

    gyroid = requests.utils.unquote(gyroid).replace("_", " ")
    gyroid_limit = "1"
    gyroid_tables = "nh_gyroid"
    gyroid_fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "buy1_wikitext",
        "buy2_price",
        "buy2_currency",
        "buy2_wikitext",
        "sell",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "availability3",
        "availability3_note",
        "variation_total",
        "customizable",
        "custom_kits",
        "custom_kit_type",
        "custom_body_part",
        "cyrus_price",
        "grid_size",
        "sound",
        "version_added",
        "unlocked",
        "notes",
    )
    gyroid_where = f'en_name = "{gyroid}"'
    gyroid_params = {
        "action": "cargoquery",
        "format": "json",
        "tables": gyroid_tables,
        "fields": gyroid_fields,
        "where": gyroid_where,
        "limit": gyroid_limit,
    }
    variation_limit = "10"
    variation_tables = "nh_gyroid_variation"
    variation_fields = generate_fields("en_name=name", "variation", "image_url", "color1", "color2")
    variation_where = f'en_name = "{gyroid}"'
    variation_orderby = "variation_number"
    variation_params = {
        "action": "cargoquery",
        "format": "json",
        "tables": variation_tables,
        "fields": variation_fields,
        "where": variation_where,
        "order_by": variation_orderby,
        "limit": variation_limit,
    }

    cargo_results = call_cargo(gyroid_params, request.args)
    if len(cargo_results) == 0:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {gyroid_params}",
            ),
        )
    else:
        piece = format_gyroid(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))


@router.route("/nh/gyroids", methods=["GET"])
def get_nh_gyroid_all():
    authorize(DB_KEYS, request)

    if "thumbsize" in request.args:
        abort(
            400,
            description=error_response(
                "Invalid arguments", "Cannot have thumbsize in a group item request"
            ),
        )

    gyroid_limit = GYROID_LIMIT
    gyroid_tables = "nh_gyroid"
    gyroid_fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "buy1_wikitext",
        "buy2_price",
        "buy2_currency",
        "buy2_wikitext",
        "sell",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "availability3",
        "availability3_note",
        "variation_total",
        "customizable",
        "custom_kits",
        "custom_kit_type",
        "custom_body_part",
        "cyrus_price",
        "grid_size",
        "sound",
        "version_added",
        "unlocked",
        "notes",
    )
    variation_limit = GYROID_VARIATION_LIMIT
    variation_tables = "nh_gyroid_variation"
    variation_fields = generate_fields("en_name=name", "variation", "image_url", "color1", "color2")
    variation_orderby = "variation_number"

    gyroid_list = get_gyroid_list(gyroid_limit, gyroid_tables, gyroid_fields)
    variation_list = get_variation_list(
        variation_limit, variation_tables, variation_fields, variation_orderby
    )
    stitched = stitch_variation_list(gyroid_list, variation_list)

    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in stitched])
    else:
        return jsonify(stitched)

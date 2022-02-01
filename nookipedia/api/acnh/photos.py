import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_variation_list, get_photo_list
from nookipedia.errors import error_response
from nookipedia.models import format_photo, stitch_variation, stitch_variation_list
from nookipedia.utility import generate_fields


router = Blueprint("photos", __name__)


@router.route("/nh/photos/<string:photo>", methods=["GET"])
def get_nh_photo(photo):
    authorize(DB_KEYS, request)

    photo = requests.utils.unquote(photo).replace("_", " ")
    photo_limit = "1"
    photo_tables = "nh_photo"
    photo_fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "category",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "buy2_price",
        "buy2_currency",
        "sell",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "customizable",
        "custom_kits",
        "custom_body_part",
        "grid_size",
        "interactable",
        "version_added",
        "unlocked",
    )
    photo_where = f'en_name = "{photo}"'
    photo_params = {
        "action": "cargoquery",
        "format": "json",
        "tables": photo_tables,
        "fields": photo_fields,
        "where": photo_where,
        "limit": photo_limit,
    }
    variation_limit = "10"
    variation_tables = "nh_photo_variation"
    variation_fields = generate_fields("en_name=name", "variation", "image_url", "color1", "color2")
    variation_where = f'en_name = "{photo}"'
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

    cargo_results = call_cargo(photo_params, request.args)
    if len(cargo_results) == 0:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {photo_params}",
            ),
        )
    else:
        piece = format_photo(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))


@router.route("/nh/photos", methods=["GET"])
def get_nh_photo_all():
    authorize(DB_KEYS, request)

    if "thumbsize" in request.args:
        abort(
            400,
            description=error_response(
                "Invalid arguments", "Cannot have thumbsize in a group item request"
            ),
        )

    photo_limit = "1000"
    photo_tables = "nh_photo"
    photo_fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "category",
        "hha_base",
        "buy1_price",
        "buy1_currency",
        "buy2_price",
        "buy2_currency",
        "sell",
        "availability1",
        "availability1_note",
        "availability2",
        "availability2_note",
        "customizable",
        "custom_kits",
        "custom_body_part",
        "grid_size",
        "interactable",
        "version_added",
        "unlocked",
    )
    variation_limit = "4500"
    variation_tables = "nh_photo_variation"
    variation_fields = generate_fields("en_name=name", "variation", "image_url", "color1", "color2")
    variation_orderby = "variation_number"

    photo_list = get_photo_list(photo_limit, photo_tables, photo_fields)
    variation_list = get_variation_list(
        variation_limit, variation_tables, variation_fields, variation_orderby
    )
    stitched = stitch_variation_list(photo_list, variation_list)

    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in stitched])
    else:
        return jsonify(stitched)

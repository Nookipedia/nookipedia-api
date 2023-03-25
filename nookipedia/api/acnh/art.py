import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS, ART_LIMIT
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_art_list
from nookipedia.errors import error_response
from nookipedia.models import format_art
from nookipedia.utility import generate_fields

router = Blueprint("art", __name__)


@router.route("/nh/art/<string:art>", methods=["GET"])
def get_nh_art(art):
    authorize(DB_KEYS, request)

    art = requests.utils.unquote(art).replace("_", " ")
    limit = "1"
    tables = "nh_art"
    fields = generate_fields(
        "name",
        "_pageName=url",
        "image_url",
        "has_fake",
        "fake_image_url",
        "texture_url",
        "fake_texture_url",
        "art_name",
        "art_type",
        "author",
        "year",
        "art_style",
        "description",
        "buy_price=buy",
        "sell",
        "availability",
        "authenticity",
        "width",
        "length",
    )
    where = f'name="{art}"'
    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "where": where,
        "limit": limit,
    }

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}",
            ),
        )
    else:
        return jsonify(format_art(cargo_results[0]))


@router.route("/nh/art", methods=["GET"])
def get_nh_art_all():
    authorize(DB_KEYS, request)

    limit = ART_LIMIT
    tables = "nh_art"
    if request.args.get("excludedetails") == "true":
        fields = "name"
    else:
        fields = generate_fields(
            "name",
            "_pageName=url",
            "image_url",
            "has_fake",
            "fake_image_url",
            "texture_url",
            "fake_texture_url",
            "art_name",
            "art_type",
            "author",
            "year",
            "art_style",
            "description",
            "buy_price=buy",
            "sell",
            "availability",
            "authenticity",
            "width",
            "length",
        )

    return get_art_list(limit, tables, fields)

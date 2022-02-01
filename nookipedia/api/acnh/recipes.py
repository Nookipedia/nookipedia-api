from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_recipe_list
from nookipedia.errors import error_response
from nookipedia.models import format_recipe
from nookipedia.utility import generate_fields


router = Blueprint("recipes", __name__)


@router.route("/nh/recipes/<string:recipe>", methods=["GET"])
def get_nh_recipe(recipe):
    authorize(DB_KEYS, request)

    recipe = recipe.replace("_", " ")
    limit = "1"
    tables = "nh_recipe"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "serial_id",
        "buy1_price",
        "buy1_currency",
        "buy2_price",
        "buy2_currency",
        "sell",
        "recipes_to_unlock",
        "diy_availability1",
        "diy_availability1_note",
        "diy_availability2",
        "diy_availability2_note",
        "material1",
        "material1_num",
        "material2",
        "material2_num",
        "material3",
        "material3_num",
        "material4",
        "material4_num",
        "material5",
        "material5_num",
        "material6",
        "material6_num",
    )
    where = f'en_name="{recipe}"'
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
        return jsonify(format_recipe(cargo_results[0]))


@router.route("/nh/recipes", methods=["GET"])
def get_nh_recipe_all():
    authorize(DB_KEYS, request)

    limit = "1000"
    tables = "nh_recipe"
    fields = generate_fields(
        "_pageName=url",
        "en_name=name",
        "image_url",
        "serial_id",
        "buy1_price",
        "buy1_currency",
        "buy2_price",
        "buy2_currency",
        "sell",
        "recipes_to_unlock",
        "diy_availability1",
        "diy_availability1_note",
        "diy_availability2",
        "diy_availability2_note",
        "material1",
        "material1_num",
        "material2",
        "material2_num",
        "material3",
        "material3_num",
        "material4",
        "material4_num",
        "material5",
        "material5_num",
        "material6",
        "material6_num",
    )

    return get_recipe_list(limit, tables, fields)

from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_variation_list, get_tool_list
from nookipedia.errors import error_response
from nookipedia.models import format_tool, stitch_variation, stitch_variation_list


router = Blueprint("tools", __name__)


@router.route("/nh/tools/<string:tool>", methods=["GET"])
def get_nh_tool(tool):
    authorize(DB_KEYS, request)

    tool = requests.utils.unquote(tool).replace("_", " ")
    tool_limit = "1"
    tool_tables = "nh_tool"
    tool_fields = "_pageName=url,en_name=name,uses,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,customizable,custom_kits,custom_body_part,version_added,unlocked,notes"
    tool_where = f'en_name = "{tool}"'
    tool_params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tool_tables,
        "fields": tool_fields,
        "where": tool_where,
        "limit": tool_limit,
    }
    variation_limit = "10"
    variation_tables = "nh_tool_variation"
    variation_fields = "en_name=name,variation,image_url"
    variation_where = f'en_name = "{tool}"'
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

    cargo_results = call_cargo(tool_params, request.args)
    if len(cargo_results) == 0:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {tool_params}",
            ),
        )
    else:
        piece = format_tool(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))


@router.route("/nh/tools", methods=["GET"])
def get_nh_tool_all():
    authorize(DB_KEYS, request)

    if "thumbsize" in request.args:
        abort(
            400,
            description=error_response(
                "Invalid arguments", "Cannot have thumbsize in a group item request"
            ),
        )

    tool_limit = "100"
    tool_tables = "nh_tool"
    tool_fields = "_pageName=url,en_name=name,uses,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,customizable,custom_kits,custom_body_part,version_added,unlocked,notes"
    variation_limit = "300"
    variation_tables = "nh_tool_variation"
    variation_fields = "en_name=name,variation,image_url"
    variation_orderby = "variation_number"

    tool_list = get_tool_list(tool_limit, tool_tables, tool_fields)
    variation_list = get_variation_list(
        variation_limit, variation_tables, variation_fields, variation_orderby
    )
    stitched = stitch_variation_list(tool_list, variation_list)

    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in stitched])
    else:
        return jsonify(stitched)

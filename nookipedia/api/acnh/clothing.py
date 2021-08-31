from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_clothing_list, get_variation_list
from nookipedia.errors import error_response
from nookipedia.models import format_clothing, stitch_variation, stitch_variation_list


router = Blueprint("clothing", __name__)


@router.route("/nh/clothing/<string:clothing>", methods=["GET"])
def get_nh_clothing(clothing):
    authorize(DB_KEYS, request)

    clothing = requests.utils.unquote(clothing).replace("_", " ")
    clothing_limit = "1"
    clothing_tables = "nh_clothing"
    clothing_fields = "_pageName=url,en_name=name,category,style1,style2,label1,label2,label3,label4,label5,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,variation_total,vill_equip,seasonality,version_added,unlocked,notes"
    clothing_where = f'en_name = "{clothing}"'
    clothing_params = {
        "action": "cargoquery",
        "format": "json",
        "tables": clothing_tables,
        "fields": clothing_fields,
        "where": clothing_where,
        "limit": clothing_limit,
    }
    variation_limit = "10"
    variation_tables = "nh_clothing_variation"
    variation_fields = "en_name=name,variation,image_url,color1,color2"
    variation_where = f'en_name = "{clothing}"'
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

    cargo_results = call_cargo(clothing_params, request.args)
    if len(cargo_results) == 0:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {clothing_params}",
            ),
        )
    else:
        piece = format_clothing(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))


@router.route("/nh/clothing", methods=["GET"])
def get_nh_clothing_all():
    authorize(DB_KEYS, request)

    if "thumbsize" in request.args:
        abort(
            400,
            description=error_response(
                "Invalid arguments", "Cannot have thumbsize in a group item request"
            ),
        )

    clothing_limit = "1350"
    clothing_tables = "nh_clothing"
    clothing_fields = "_pageName=url,en_name=name,category,style1,style2,label1,label2,label3,label4,label5,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,variation_total,vill_equip,seasonality,version_added,unlocked,notes"
    variation_limit = "5000"
    variation_tables = "nh_clothing_variation"
    variation_fields = "en_name=name,variation,image_url,color1,color2"
    variation_orderby = "variation_number"

    clothing_list = get_clothing_list(clothing_limit, clothing_tables, clothing_fields)
    variation_list = get_variation_list(
        variation_limit, variation_tables, variation_fields, variation_orderby
    )
    stitched = stitch_variation_list(clothing_list, variation_list)

    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in stitched])
    else:
        return jsonify(stitched)

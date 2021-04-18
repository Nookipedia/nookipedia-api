from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_furniture_list, get_furniture_variation_list
from nookipedia.errors import error_response
from nookipedia.models import format_furniture, stitch_variation, stitch_variation_list


router = Blueprint("furniture", __name__)


@router.route('/nh/furniture/<string:furniture>', methods=['GET'])
def get_nh_furniture(furniture):
    authorize(DB_KEYS, request)

    furniture = furniture.replace('_',' ')
    furniture_limit = '1'
    furniture_tables = 'nh_furniture'
    furniture_fields = 'identifier,_pageName=url,en_name=name,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,lucky,lucky_season,function1,function2,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,variation_total,pattern_total,customizable,custom_kits,custom_kit_type,custom_body_part,custom_pattern_part,grid_size,height,door_decor,version_added,unlocked,notes'#'
    furniture_where = f'en_name = "{furniture}"'
    furniture_params = { 'action': 'cargoquery', 'format': 'json', 'tables': furniture_tables, 'fields': furniture_fields, 'where': furniture_where, 'limit': furniture_limit }
    variation_limit = '70'
    variation_tables = 'nh_furniture_variation'
    variation_fields = 'identifier,variation,pattern,image_url,color1,color2'
    variation_where = f'en_name = "{furniture}"'
    variation_orderby = 'variation_number,pattern_number'
    variation_params = { 'action': 'cargoquery', 'format': 'json', 'tables': variation_tables, 'fields': variation_fields, 'where': variation_where, 'order_by': variation_orderby, 'limit': variation_limit }

    cargo_results = call_cargo(furniture_params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {furniture_params}"))
    else:
        piece = format_furniture(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))


@router.route('/nh/furniture', methods=['GET'])
def get_nh_furniture_all():
    authorize(DB_KEYS, request)

    if 'thumbsize' in request.args:
        abort(400, description=error_response('Invalid arguments','Cannot have thumbsize in a group item request'))

    furniture_limit = '1200'
    furniture_tables = 'nh_furniture'
    furniture_fields = 'identifier,_pageName=url,en_name=name,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,lucky,lucky_season,function1,function2,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,variation_total,pattern_total,customizable,custom_kits,custom_kit_type,custom_body_part,custom_pattern_part,grid_size,height,door_decor,version_added,unlocked,notes'#'
    variation_limit = '5350'
    variation_tables = 'nh_furniture_variation'
    variation_fields = 'identifier,variation,pattern,image_url,color1,color2'
    variation_orderby = 'variation_number,pattern_number'

    furniture_list = get_furniture_list(furniture_limit, furniture_tables, furniture_fields)
    variation_list = get_furniture_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(furniture_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['name'] for _ in stitched])
    else:
        return jsonify(stitched)
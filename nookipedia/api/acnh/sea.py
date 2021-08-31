import requests
from flask import abort, jsonify, request, Blueprint

from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import call_cargo, get_critter_list
from nookipedia.errors import error_response
from nookipedia.models import exact_version, months_to_array, format_critters


router = Blueprint("sea", __name__)


# All New Horizons sea creatures
@router.route("/nh/sea", methods=["GET"])
def get_nh_sea_all():
    authorize(DB_KEYS, request)

    limit = "100"
    tables = "nh_sea_creature"
    if request.args.get("excludedetails") == "true":
        fields = "name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12"
    else:
        fields = "name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time"

    return get_critter_list(limit, tables, fields)


# Specific New Horizons sea creature
@router.route("/nh/sea/<string:sea>", methods=["GET"])
def get_nh_sea(sea):
    authorize(DB_KEYS, request)

    sea = requests.utils.unquote(sea).replace("_", " ")
    limit = "1"
    tables = "nh_sea_creature"
    fields = "name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time"
    where = 'name="' + sea + '"'
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
                "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(
                    params
                ),
            ),
        )
    else:
        if exact_version("1.0"):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])

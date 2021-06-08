from flask import abort, jsonify, request, Blueprint

import requests
from nookipedia.config import DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.cargo import (
    call_cargo,
    get_fossil_group_list,
    get_fossil_list,
)
from nookipedia.errors import error_response
from nookipedia.models import (
    format_fossil,
    format_fossil_group,
    stitch_fossil_group_list,
)

router = Blueprint("fossils", __name__, url_prefix="/nh/fossils")


@router.route("/groups", methods=["GET"])
def get_nh_fossil_group_all():
    authorize(DB_KEYS, request)

    limit = "50"
    tables = "nh_fossil_group"
    fields = "name,_pageName=url,room,description"

    ret = get_fossil_group_list(limit, tables, fields)
    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in ret])
    else:
        return jsonify(ret)


@router.route("/individuals", methods=["GET"])
def get_nh_fossil_individual_all():
    authorize(DB_KEYS, request)

    limit = "100"
    tables = "nh_fossil"
    fields = "name,_pageName=url,image_url,fossil_group,interactable,sell,color1,color2,hha_base,width,length"

    ret = get_fossil_list(limit, tables, fields)
    if request.args.get("excludedetails") == "true":
        return jsonify([_["name"] for _ in ret])
    else:
        return jsonify(ret)


@router.route("/all", methods=["GET"])
def get_nh_fossil_all_all():  # What a good name
    authorize(DB_KEYS, request)

    group_limit = "50"
    group_tables = "nh_fossil_group"
    group_fields = "name,_pageName=url,room,description"
    fossil_limit = "100"
    fossil_tables = "nh_fossil"
    fossil_fields = "name,_pageName=url,image_url,fossil_group,interactable,sell,color1,color2,hha_base,width,length"

    groups = get_fossil_group_list(group_limit, group_tables, group_fields)
    fossils = get_fossil_list(fossil_limit, fossil_tables, fossil_fields)

    stitched = stitch_fossil_group_list(groups, fossils)

    if request.args.get("excludedetails") == "true":
        ret = []
        for group in stitched:
            obj = {"group": group["name"], "fossils": [_["name"] for _ in group["fossils"]]}
            ret.append(obj)
        return jsonify(ret)
    else:
        return jsonify(stitched)


@router.route("/groups/<string:name>", methods=["GET"])
def get_nh_fossil_group(name):
    authorize(DB_KEYS, request)

    limit = "1"
    tables = "nh_fossil_group"
    fields = "name,_pageName=url,room,description"
    where = f'name = "{name}"'

    params = {
        "action": "cargoquery",
        "format": "json",
        "limit": limit,
        "tables": tables,
        "fields": fields,
        "where": where,
    }

    cargo_results = call_cargo(params, request.args)

    if not cargo_results:
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
        return format_fossil_group(cargo_results[0])


@router.route("/individuals/<string:name>", methods=["GET"])
def get_nh_fossil_individual(name):
    authorize(DB_KEYS, request)

    name = requests.utils.unquote(name).replace("_", " ")
    limit = "1"
    tables = "nh_fossil"
    fields = "name,_pageName=url,image_url,fossil_group,interactable,sell,color1,color2,hha_base,width,length"
    where = f'name = "{name}"'

    params = {
        "action": "cargoquery",
        "format": "json",
        "limit": limit,
        "tables": tables,
        "fields": fields,
        "where": where,
    }

    cargo_results = call_cargo(params, request.args)

    if not cargo_results:
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
        return format_fossil(cargo_results[0])


@router.route("/all/<string:name>", methods=["GET"])
def get_nh_fossil_all(name):
    authorize(DB_KEYS, request)

    name = requests.utils.unquote(name).replace("_", " ")

    group_limit = "1"
    group_tables = "nh_fossil_group"
    group_fields = "name,_pageName=url,room,description"

    # fossil_fields = "name,_pageName=url,image_url,fossil_group,interactable,sell,color1,color2,hha_base,width,length"

    fossil_params = {
        "action": "cargoquery",
        "format": "json",
        "limit": "1",
        "tables": "nh_fossil",
        "fields": "name,fossil_group",
        "where": f'name = "{name}"',
    }

    group_params = {
        "action": "cargoquery",
        "format": "json",
        "limit": "1",
        "tables": "nh_fossil_group",
        "fields": "name,_pageName=url,room,description",
    }

    fossil_check = call_cargo(fossil_params, request.args)
    if fossil_check:
        fossil_check = fossil_check[0]
        group_params["where"] = f'name = "{fossil_check["fossil_group"]}"'
        matched = {"type": "individual", "name": fossil_check["name"]}
    else:
        fossil_check = None
        group_params["where"] = f'name = "{name}"'
        matched = {"type": "group"}

    group = call_cargo(group_params, request.args)
    if group:
        group = format_fossil_group(group[0])
        if not fossil_check:
            matched["name"] = group["name"]
        group["matched"] = matched
    else:
        abort(
            404,
            description=error_response(
                "No data was found for the given query.",
                "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(
                    group_params
                ),
            ),
        )

    fossil_params["where"] = f'fossil_group = "{group["name"]}"'
    fossil_params["limit"] = "10"
    fossil_params[
        "fields"
    ] = "name,_pageName=url,image_url,fossil_group,interactable,sell,color1,color2,hha_base,width,length"
    #          Technically don't need this ^^^ but it syncs the /all and /all/name caches
    fossils = call_cargo(fossil_params, request.args)
    group["fossils"] = [format_fossil(_) for _ in fossils]
    for fossil in group["fossils"]:
        del fossil["fossil_group"]

    return jsonify(group)

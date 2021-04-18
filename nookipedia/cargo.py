from datetime import datetime
from dateutil import parser
from flask import abort, jsonify, request
import requests
from nookipedia.cache import cache
from nookipedia.utility import deep_unescape, params_where, month_to_string, month_to_int
from nookipedia.config import BASE_URL_API, BASE_URL_WIKI, BOT_USERNAME, BOT_PASS
from nookipedia.errors import error_response
from nookipedia.models import (
    format_villager,
    months_to_array,
    format_critters,
    format_art,
    format_recipe,
    format_furniture,
    format_clothing,
    format_photo,
    format_tool,
    format_interior,
    format_other_item,
)


# Login to MediaWiki as a bot account:
def mw_login():
    try:
        params = {"action": "query", "meta": "tokens", "type": "login", "format": "json"}
        r = requests.get(url=BASE_URL_API, params=params)
        try:
            login_token = r.json()["query"]["tokens"]["logintoken"]
        except:
            print("Failed to login to MediaWiki (could not retrieve login token).")
            return False

        if login_token:
            data = {
                "action": "login",
                "lgname": BOT_USERNAME,
                "lgpassword": BOT_PASS,
                "lgtoken": login_token,
                "format": "json",
            }
            r = requests.post(
                url=BASE_URL_API, data=data, cookies=requests.utils.dict_from_cookiejar(r.cookies)
            )
            rJson = r.json()

            if "login" not in rJson:
                print("Failed to login to MediaWiki (POST to login failed): " + str(rJson))
                return False
            if "result" not in rJson["login"]:
                print("Failed to login to MediaWiki (POST to login failed): " + str(rJson))
                return False
            if rJson["login"]["result"] == "Success":
                print("Successfully logged into MediaWiki API.")
                cache.set(
                    "session", {"token": login_token, "cookie": r.cookies}, 2592000
                )  # Expiration set to max of 30 days
                return True
            else:
                print("Failed to login to MediaWiki (POST to login failed): " + str(rJson))
                return False
        else:
            print("Failed to login to MediaWiki (could not retrieve login token).")
            return False
    except:
        print("Failed to login to MediaWiki.")
        return False


@cache.memoize(43200)
def call_cargo(parameters, request_args):  # Request args are passed in just for the sake of caching
    # cargoquery holds all queried items
    cargoquery = []

    # Default query size limit is 50 but can be changed by incoming params:
    cargolimit = int(parameters.get("limit", "50"))

    # Copy the passed-in parameters:
    nestedparameters = parameters.copy()

    try:
        while True:
            # Subtract number of queried items from limit:
            nestedparameters["limit"] = str(cargolimit - len(cargoquery))

            # If no items are left to query, break
            if nestedparameters["limit"] == "0":
                break

            # Set offset to number of items queried so far:
            nestedparameters["offset"] = str(len(cargoquery))

            # Check if we should authenticate to the wiki (500 is limit for unauthenticated queries):
            if BOT_USERNAME and int(parameters.get("limit", "50")) > 500:
                nestedparameters["assert"] = "bot"
                session = cache.get("session")  # Get session from memcache

                # Session may be null from startup or cache explusion:
                if not session:
                    mw_login()
                    session = cache.get("session")

                # Make authorized request:
                r = requests.get(
                    url=BASE_URL_API,
                    params=nestedparameters,
                    headers={"Authorization": "Bearer " + session["token"]},
                    cookies=session["cookie"],
                )
                if "error" in r.json():
                    # Error may be due to invalid token; re-try login:
                    if mw_login():
                        session = cache.get("session")
                        r = requests.get(
                            url=BASE_URL_API,
                            params=nestedparameters,
                            headers={"Authorization": "Bearer " + session["token"]},
                            cookies=session["cookie"],
                        )

                        # If it errors again, make request without auth:
                        if "error" in r.json():
                            del nestedparameters["assert"]
                            r = requests.get(url=BASE_URL_API, params=nestedparameters)
                    else:
                        del nestedparameters["assert"]
                        r = requests.get(url=BASE_URL_API, params=nestedparameters)
            else:
                r = requests.get(url=BASE_URL_API, params=nestedparameters)

            cargochunk = r.json()["cargoquery"]
            if len(cargochunk) == 0:  # If nothing was returned, break
                break

            cargoquery.extend(cargochunk)

            # If queried items are < limit and there are no warnings, we've received everything:
            if ("warnings" not in r.json()) and (len(cargochunk) < cargolimit):
                break
        print("Return: {}".format(str(r)))
    except:
        print("Return: {}".format(str(r)))
        abort(
            500,
            description=error_response(
                "Error while calling Nookipedia's Cargo API.",
                "MediaWiki Cargo request failed for parameters: {}".format(parameters),
            ),
        )

    if not cargoquery:
        return []

    try:
        data = []
        # Check if user requested specific image size and modify accordingly:
        for obj in cargoquery:
            item = {}

            # Replace all spaces in keys with underscores
            for key in obj["title"]:
                item[key.replace(" ", "_")] = obj["title"][key]

            item = deep_unescape(item)

            # Create url to page
            if "url" in item:
                item["url"] = "https://nookipedia.com/wiki/" + item["url"].replace(" ", "_")

            if request.args.get("thumbsize"):
                # If image, fetch the CDN thumbnail URL:
                try:
                    # Only fetch the image if this object actually has an image to fetch
                    if "image_url" in item:
                        r = requests.get(
                            BASE_URL_WIKI
                            + "Special:FilePath/"
                            + item["image_url"].rsplit("/", 1)[-1]
                            + "?width="
                            + request.args.get("thumbsize")
                        )
                        item["image_url"] = r.url

                    # If this is a painting that has a fake, fetch that too
                    if item.get("has_fake", "0") == "1":
                        r = requests.get(
                            BASE_URL_WIKI
                            + "Special:FilePath/"
                            + item["fake_image_url"].rsplit("/", 1)[-1]
                            + "?width="
                            + request.args.get("thumbsize")
                        )
                        item["fake_image_url"] = r.url

                    # Same goes for the renders
                    if "render_url" in item:
                        r = requests.get(
                            BASE_URL_WIKI
                            + "Special:FilePath/"
                            + item["render_url"].rsplit("/", 1)[-1]
                            + "?width="
                            + request.args.get("thumbsize")
                        )
                        item["render_url"] = r.url
                except:
                    abort(
                        500,
                        description=error_response(
                            "Error while getting image CDN thumbnail URL.",
                            "Failure occured with the following parameters: {}.".format(parameters),
                        ),
                    )

            data.append(item)

        return data
    except:
        abort(
            500,
            description=error_response(
                "Error while formatting Cargo response.",
                "Iterating over cargoquery array in response object failed for the parameters: {}.".format(
                    parameters
                ),
            ),
        )


def get_villager_list(limit, tables, join, fields):
    where = []

    # Filter by name:
    if request.args.get("name"):
        villager = request.args.get("name").replace("_", " ").capitalize()
        where.append('villager.name = "' + villager + '"')

    # Filter by birth month:
    if request.args.get("birthmonth"):
        month = month_to_string(request.args.get("birthmonth"))
        where.append('villager.birthday_month = "' + month + '"')

    # Filter by birth day:
    if request.args.get("birthday"):
        day = request.args.get("birthday")
        where.append('villager.birthday_day = "' + day + '"')

    # Filter by personality:
    if request.args.get("personality"):
        personality_list = [
            "lazy",
            "jock",
            "cranky",
            "smug",
            "normal",
            "peppy",
            "snooty",
            "sisterly",
            "big sister",
        ]
        personality = request.args.get("personality").lower()
        if personality not in personality_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided personality.",
                    "Ensure personality is either lazy, jock, cranky, smug, normal, peppy, snooty, or sisterly/big sister.",
                ),
            )

        if personality == "sisterly":
            personality = "big sister"

        where.append('villager.personality = "' + personality + '"')

    # Filter by species:
    if request.args.get("species"):
        species_list = [
            "alligator",
            "anteater",
            "bear",
            "bear cub",
            "bird",
            "bull",
            "cat",
            "cub",
            "chicken",
            "cow",
            "deer",
            "dog",
            "duck",
            "eagle",
            "elephant",
            "frog",
            "goat",
            "gorilla",
            "hamster",
            "hippo",
            "horse",
            "koala",
            "kangaroo",
            "lion",
            "monkey",
            "mouse",
            "octopus",
            "ostrich",
            "penguin",
            "pig",
            "rabbit",
            "rhino",
            "rhinoceros",
            "sheep",
            "squirrel",
            "tiger",
            "wolf",
        ]
        species = request.args.get("species").lower()
        if species not in species_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided species.", "Ensure provided species is valid."
                ),
            )

        if species == "cub":
            species = "bear cub"
        elif species == "rhino":
            species = "rhinoceros"

        where.append('villager.species = "' + species + '"')

    # Filter by game:
    if request.args.get("game"):
        games = request.args.getlist("game")
        for game in games:
            game = game.replace("_", " ")
            where.append("villager." + game + ' = "1"')

    params = {
        "action": "cargoquery",
        "format": "json",
        "limit": limit,
        "tables": tables,
        "join_on": join,
        "fields": fields,
    }
    params_where(params, where)

    print(str(params))
    if request.args.get("excludedetails") == "true":
        cargo_results = call_cargo(params, request.args)
        results_array = []
        for villager in cargo_results:
            results_array.append(villager["name"])
        return jsonify(results_array)
    else:
        return jsonify(format_villager(call_cargo(params, request.args)))


def get_critter_list(limit, tables, fields):
    # If client requests specific month:
    if request.args.get("month"):
        calculated_month = month_to_int(request.args.get("month"))
        if not calculated_month:
            abort(
                400,
                description=error_response(
                    "Failed to identify the provided month filter.",
                    "Provided month filter {} was not recognized as a valid month.".format(
                        request.args.get("month")
                    ),
                ),
            )

        paramsNorth = {
            "action": "cargoquery",
            "format": "json",
            "limit": limit,
            "tables": tables,
            "fields": fields,
            "where": "n_m" + calculated_month + '="1"',
        }
        paramsSouth = {
            "action": "cargoquery",
            "format": "json",
            "limit": limit,
            "tables": tables,
            "fields": fields,
            "where": "s_m" + calculated_month + '="1"',
        }

        # If client doesn't want all details:
        if request.args.get("excludedetails") == "true":
            n_hemi = months_to_array(call_cargo(paramsNorth, request.args))
            s_hemi = months_to_array(call_cargo(paramsSouth, request.args))

            if n_hemi and s_hemi:
                try:
                    n_hemi_array = []
                    for critter in n_hemi:
                        n_hemi_array.append(critter["name"])
                    s_hemi_array = []
                    for critter in s_hemi:
                        s_hemi_array.append(critter["name"])
                    return jsonify(
                        {"month": calculated_month, "north": n_hemi_array, "south": s_hemi_array}
                    )
                except:
                    abort(
                        400,
                        description=error_response(
                            "Failed to identify the provided month filter.",
                            "Provided month filter {} was not recognized as a valid month.".format(
                                request.args.get("month")
                            ),
                        ),
                    )
            else:
                abort(
                    400,
                    description=error_response(
                        "Failed to identify the provided month filter.",
                        "Provided month filter {} was not recognized as a valid month.".format(
                            request.args.get("month")
                        ),
                    ),
                )
        # If client wants full details:
        else:
            n_hemi = months_to_array(format_critters(call_cargo(paramsNorth, request.args)))
            s_hemi = months_to_array(format_critters(call_cargo(paramsSouth, request.args)))

            if n_hemi and s_hemi:
                try:
                    return jsonify({"month": calculated_month, "north": n_hemi, "south": s_hemi})
                except:
                    abort(
                        400,
                        description=error_response(
                            "Failed to identify the provided month filter.",
                            "Provided month filter {} was not recognized as a valid month.".format(
                                request.args.get("month")
                            ),
                        ),
                    )
            else:
                abort(
                    400,
                    description=error_response(
                        "Failed to identify the provided month filter.",
                        "Provided month filter {} was not recognized as a valid month.".format(
                            request.args.get("month")
                        ),
                    ),
                )
    # If client doesn't specify specific month:
    else:
        params = {
            "action": "cargoquery",
            "format": "json",
            "limit": limit,
            "tables": tables,
            "fields": fields,
        }
        if request.args.get("excludedetails") == "true":
            cargo_results = call_cargo(params, request.args)
            results_array = []
            for critter in cargo_results:
                results_array.append(critter["name"])
            return jsonify(results_array)
        else:
            return jsonify(months_to_array(format_critters(call_cargo(params, request.args))))


def get_art_list(limit, tables, fields):
    where = []

    if request.args.get("hasfake"):
        fake = request.args.get("hasfake").lower()
        if fake == "true":
            where.append("has_fake = true")
        elif fake == "false":
            where.append("has_fake = false")

    params = {
        "action": "cargoquery",
        "format": "json",
        "limit": limit,
        "tables": tables,
        "fields": fields,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get("excludedetails") == "true":
        for art in cargo_results:
            results_array.append(art["name"])
    else:
        for art in cargo_results:
            results_array.append(format_art(art))
    return jsonify(results_array)


def get_recipe_list(limit, tables, fields):
    where = []

    if "material" in request.args:
        materials = request.args.getlist("material")
        if len(materials) > 6:
            abort(
                400,
                description=error_response(
                    "Invalid arguments", "Cannot have more than six materials"
                ),
            )
        for m in materials:
            m.replace("_", " ")
            where.append(
                '(material1 = "{0}" or material2 = "{0}" or material3 = "{0}" or material4 = "{0}" or material5 = "{0}" or material6 = "{0}")'.format(
                    m
                )
            )

    params = {
        "action": "cargoquery",
        "format": "json",
        "limit": limit,
        "tables": tables,
        "fields": fields,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get("excludedetails") == "true":
        for recipe in cargo_results:
            results_array.append(recipe["name"])
    else:
        for recipe in cargo_results:
            results_array.append(format_recipe(recipe))
    return jsonify(results_array)


def get_event_list(limit, tables, fields, orderby):
    where = []

    # Filter by date:
    if request.args.get("date"):
        date = request.args.get("date")
        today = datetime.today()
        if date == "today":
            where.append(
                "YEAR(date) = "
                + today.strftime("%Y")
                + " AND MONTH(date) = "
                + today.strftime("%m")
                + " AND DAYOFMONTH(date) = "
                + today.strftime("%d")
            )
        else:
            try:
                parsed_date = parser.parse(date)
            except:
                abort(
                    400,
                    description=error_response(
                        "Could not recognize provided date.",
                        "Ensure date is of a valid date format, or 'today'.",
                    ),
                )
            if parsed_date.strftime("%Y") not in [str(today.year), str(today.year + 1)]:
                abort(
                    404,
                    description=error_response(
                        "No data was found for the given query.",
                        "You must request events from either the current or next year.",
                    ),
                )
            else:
                where.append(
                    "YEAR(date) = "
                    + parsed_date.strftime("%Y")
                    + " AND MONTH(date) = "
                    + parsed_date.strftime("%m")
                    + " AND DAYOFMONTH(date) = "
                    + parsed_date.strftime("%d")
                )

    # Filter by year:
    if request.args.get("year"):
        year = request.args.get("year")
        where.append('YEAR(date) = "' + year + '"')

    # Filter by month:
    if request.args.get("month"):
        month = month_to_int(request.args.get("month"))
        where.append('MONTH(date) = "' + month + '"')

    # Filter by day:
    if request.args.get("day"):
        day = request.args.get("day")
        where.append('DAYOFMONTH(date) = "' + day + '"')

    # Filter by event:
    if request.args.get("event"):
        event = request.args.get("event")
        where.append('event = "' + event + '"')

    # Filter by type:
    if request.args.get("type"):
        type = request.args.get("type")
        if type not in ["Event", "Nook Shopping", "Birthday", "Recipes"]:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided type.",
                    "Ensure type is either Event, Nook Shopping, Birthday, or Recipes.",
                ),
            )
        where.append('type = "' + type + '"')

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "order_by": orderby,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)

    for event in cargo_results:
        del event["date__precision"]

    return jsonify(cargo_results)


def get_furniture_list(limit, tables, fields):
    where = []

    if "category" in request.args:
        categories_list = ["housewares", "miscellaneous", "wall-mounted"]
        category = request.args.get("category").lower()
        if category not in categories_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided category.",
                    "Ensure category is either housewares, miscellaneous, or wall-mounted.",
                ),
            )
        where.append('category = "{0}"'.format(category))

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    ret = [format_furniture(_) for _ in cargo_results]
    return ret


def get_furniture_variation_list(limit, tables, fields, orderby):
    where = []

    if "color" in request.args:
        colors_list = [
            "aqua",
            "beige",
            "black",
            "blue",
            "brown",
            "colorful",
            "gray",
            "green",
            "orange",
            "pink",
            "purple",
            "red",
            "white",
            "yellow",
        ]
        colors = [color.lower() for color in request.args.getlist("color")]
        for color in colors:
            if color not in colors_list:
                abort(
                    400,
                    description=error_response(
                        "Could not recognize provided color.",
                        "Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.",
                    ),
                )
        if len(colors) == 1:  # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2:  # If they filtered both colors
            where.append(
                '((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(
                    colors[0], colors[1]
                )
            )
        else:
            abort(
                400,
                description=error_response("Invalid arguments", "Cannot have more than two colors"),
            )

    if "pattern" in request.args:
        pattern = request.args["pattern"]
        where.append(f'pattern = "{pattern}"')

    if "variation" in request.args:
        variation = request.args["variation"]
        where.append(f'variation = "{variation}"')

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "order_by": orderby,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    return cargo_results


def get_clothing_list(limit, tables, fields):
    where = []

    if "category" in request.args:
        categories_list = [
            "tops",
            "bottoms",
            "dress-up",
            "headware",
            "accessories",
            "socks",
            "shoes",
            "bags",
            "umbrellas",
        ]
        category = request.args.get("category").lower()
        if category not in categories_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided category.",
                    "Ensure category is either tops, bottoms, dress-up, headware, accessories, socks, shoes, bags, or umbrellas.",
                ),
            )
        where.append('category = "{0}"'.format(category))

    if "style" in request.args:
        styles_list = ["active", "cool", "cute", "elegant", "gorgeous", "simple"]
        styles = [style.lower() for style in request.args.getlist("style")]
        for style in styles:
            if style not in styles_list:
                abort(
                    400,
                    description=error_response(
                        "Could not recognize provided style.",
                        "Ensure style is either active, cool, cute, elegant, gorgeous, or simple.",
                    ),
                )
        if len(styles) == 1:  # If they only filtered one style
            where.append('(style1 = "{0}" OR style2 = "{0}")'.format(styles[0]))
        elif len(styles) == 2:  # If they filtered both styles
            where.append(
                '((style1 = "{0}" AND style2 = "{1}") OR (style1 = "{1}" AND style2 = "{0}"))'.format(
                    styles[0], styles[1]
                )
            )
        else:
            abort(
                400,
                description=error_response("Invalid arguments", "Cannot have more than two styles"),
            )

    if "label" in request.args:
        label_list = [
            "comfy",
            "everyday",
            "fairy tale",
            "formal",
            "goth",
            "outdoorsy",
            "party",
            "sporty",
            "theatrical",
            "vacation",
            "work",
        ]
        label = request.args.get("label").lower()
        if label not in label_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided Label theme.",
                    "Ensure Label theme is either comfy, everyday, fairy tale, formal, goth, outdoorsy, party, sporty, theatrical, vacation, or work.",
                ),
            )
        where.append(
            '(label1 = "{0}" OR label2 = "{0}" OR label3 = "{0}" OR label4 = "{0}" OR label5 = "{0}")'.format(
                label
            )
        )

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    ret = [format_clothing(_) for _ in cargo_results]
    return ret


def get_variation_list(limit, tables, fields, orderby):
    where = []

    if "color" in request.args:
        colors_list = [
            "aqua",
            "beige",
            "black",
            "blue",
            "brown",
            "colorful",
            "gray",
            "green",
            "orange",
            "pink",
            "purple",
            "red",
            "white",
            "yellow",
        ]
        colors = [color.lower() for color in request.args.getlist("color")]
        for color in colors:
            if color not in colors_list:
                abort(
                    400,
                    description=error_response(
                        "Could not recognize provided color.",
                        "Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.",
                    ),
                )
        if len(colors) == 1:  # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2:  # If they filtered both colors
            where.append(
                '((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(
                    colors[0], colors[1]
                )
            )
        else:
            abort(
                400,
                description=error_response("Invalid arguments", "Cannot have more than two colors"),
            )

    if "variation" in request.args:
        variation = request.args["variation"]
        where.append(f'variation = "{variation}"')

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "order_by": orderby,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    return cargo_results


def get_photo_list(limit, tables, fields):
    where = []

    if "category" in request.args:
        categories_list = ["photos", "posters"]
        category = request.args.get("category").lower()
        if category not in categories_list:
            abort(
                400,
                description=error_response(
                    "Could not recognize provided category.",
                    "Ensure category is either photos or posters.",
                ),
            )
        where.append('category = "{0}"'.format(category))

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    ret = [format_photo(_) for _ in cargo_results]
    return ret


def get_tool_list(limit, tables, fields):
    where = []

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    ret = [format_tool(_) for _ in cargo_results]
    return ret


def get_interior_list(limit, tables, fields):
    where = []

    if "color" in request.args:
        colors_list = [
            "aqua",
            "beige",
            "black",
            "blue",
            "brown",
            "colorful",
            "gray",
            "green",
            "orange",
            "pink",
            "purple",
            "red",
            "white",
            "yellow",
        ]
        colors = [color.lower() for color in request.args.getlist("color")]
        for color in colors:
            if color not in colors_list:
                abort(
                    400,
                    description=error_response(
                        "Could not recognize provided color.",
                        "Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.",
                    ),
                )
        if len(colors) == 1:  # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2:  # If they filtered both colors
            where.append(
                '((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(
                    colors[0], colors[1]
                )
            )
        else:
            abort(
                400,
                description=error_response("Invalid arguments", "Cannot have more than two colors"),
            )

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get("excludedetails") == "true":
        for interior in cargo_results:
            results_array.append(interior["name"])
    else:
        for interior in cargo_results:
            results_array.append(format_interior(interior))
    return jsonify(results_array)


def get_other_item_list(limit, tables, fields):
    where = []

    params = {
        "action": "cargoquery",
        "format": "json",
        "tables": tables,
        "fields": fields,
        "limit": limit,
    }
    params_where(params, where)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get("excludedetails") == "true":
        for item in cargo_results:
            results_array.append(item["name"])
    else:
        for item in cargo_results:
            results_array.append(format_other_item(item))
    return jsonify(results_array)

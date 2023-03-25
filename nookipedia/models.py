from flask import request

from nookipedia.utility import (
    minimum_version,
    maximum_version,
    exact_version,
    format_as_type,
    separate_grid_sizes,
    as_bool,
    as_float,
    as_int,
    coalesce_fields_as_list,
    coalesce_fields_as_object_list,
    format_coalesced_object_list,
)


def format_villager(data):
    games = ["dnm", "ac", "e_plus", "ww", "cf", "nl", "wa", "nh", "film", "hhd", "pc"]

    for obj in data:
        if maximum_version("1.3"):
            if obj["personality"] == "Big sister":
                obj["personality"] = "Sisterly"
            if obj["species"] == "Bear cub":
                obj["species"] = "Cub"
            if obj["species"] == "Rhinoceros":
                obj["species"] = "Rhino"

        # Set islander to Boolean:
        format_as_type(obj, as_bool, "islander")

        # Capitalize and standardize debut:
        game_switcher = {
            "DNME+": "E_PLUS",
            "ACGC": "AC",
            "ACWW": "WW",
            "ACCF": "CF",
            "ACNL": "NL",
            "ACNLA": "WA",
            "ACNH": "NH",
            "ACHHD": "HHD",
            "ACPC": "PC",
        }
        if game_switcher.get(obj["debut"].upper()):
            obj["debut"] = game_switcher.get(obj["debut"].upper())
        else:
            obj["debut"] = obj["debut"].upper()

        # Place prev_phrases in array:
        prev_phrases_array = []
        if obj["prev_phrase"] != "":
            prev_phrases_array.append(obj["prev_phrase"])
            if obj["prev_phrase2"]:
                prev_phrases_array.append(obj["prev_phrase2"])
        obj["prev_phrases"] = prev_phrases_array
        del obj["prev_phrase"]
        del obj["prev_phrase2"]

        # Place NH details in object, if applicable:
        if request.args.get("nhdetails") == "true":
            if obj["nh"] == "0":
                obj["nh_details"] = None
            else:
                obj["nh_details"] = {
                    "image_url": obj["nh_image_url"],
                    "photo_url": obj["nh_photo_url"],
                    "icon_url": obj["nh_icon_url"],
                    "quote": obj["nh_quote"],
                    "sub-personality": obj["nh_sub-personality"],
                    "catchphrase": obj["nh_catchphrase"],
                    "clothing": obj["nh_clothing"],
                    "clothing_variation": obj["nh_clothing_variation"],
                    "fav_styles": [],
                    "fav_colors": [],
                    "hobby": obj["nh_hobby"],
                    "house_interior_url": obj["nh_house_interior_url"],
                    "house_exterior_url": obj["nh_house_exterior_url"],
                    "house_wallpaper": obj["nh_wallpaper"],
                    "house_flooring": obj["nh_flooring"],
                    "house_music": obj["nh_music"],
                    "house_music_note": obj["nh_music_note"],
                    "umbrella": obj["nh_umbrella"],
                }
                if obj["nh_fav_style1"]:
                    obj["nh_details"]["fav_styles"].append(obj["nh_fav_style1"])
                    if obj["nh_fav_style2"]:
                        obj["nh_details"]["fav_styles"].append(obj["nh_fav_style2"])
                if obj["nh_fav_color1"]:
                    obj["nh_details"]["fav_colors"].append(obj["nh_fav_color1"])
                    if obj["nh_fav_color2"]:
                        obj["nh_details"]["fav_colors"].append(obj["nh_fav_color2"])
            del obj["nh_image_url"]
            del obj["nh_photo_url"]
            del obj["nh_icon_url"]
            del obj["nh_quote"]
            del obj["nh_sub-personality"]
            del obj["nh_catchphrase"]
            del obj["nh_clothing"]
            del obj["nh_clothing_variation"]
            del obj["nh_fav_style1"]
            del obj["nh_fav_style2"]
            del obj["nh_fav_color1"]
            del obj["nh_fav_color2"]
            del obj["nh_hobby"]
            del obj["nh_house_interior_url"]
            del obj["nh_house_exterior_url"]
            del obj["nh_wallpaper"]
            del obj["nh_flooring"]
            del obj["nh_music"]
            del obj["nh_music_note"]
            del obj["nh_umbrella"]

        # Place game appearances in array:
        games_array = []
        for i in games:
            if obj[i] == "1":
                games_array.append(i.upper())
            del obj[i]
        obj["appearances"] = games_array

    return data


def months_to_array(data):
    n_months_array = []
    s_months_array = []
    for obj in data:
        for key in obj:
            if "n_m" in key:
                if obj[key] == "1":
                    if minimum_version("1.2"):
                        n_months_array.append(int(key.replace("n_m", "")))
                    else:
                        n_months_array.append(key.replace("n_m", ""))
            if "s_m" in key:
                if obj[key] == "1":
                    if minimum_version("1.2"):
                        s_months_array.append(int(key.replace("s_m", "")))
                    else:
                        s_months_array.append(key.replace("s_m", ""))
        for i in range(1, 13):
            del obj["n_m" + str(i)]
            del obj["s_m" + str(i)]

        if maximum_version("1.1"):
            obj["n_availability_array"] = n_months_array
            obj["s_availability_array"] = s_months_array
        elif exact_version("1.2"):
            if "n_availability" in obj:
                obj["months_north"] = obj["n_availability"]
                del obj["n_availability"]
                obj["months_south"] = obj["s_availability"]
                del obj["s_availability"]
                obj["months_north_array"] = n_months_array
                obj["months_south_array"] = s_months_array
        else:
            if "n_availability" in obj:
                obj["north"]["months"] = obj["n_availability"]
                del obj["n_availability"]
                obj["south"]["months"] = obj["s_availability"]
                del obj["s_availability"]
                obj["north"]["months_array"] = n_months_array
                obj["south"]["months_array"] = s_months_array

        n_months_array = []
        s_months_array = []

    return data


def format_critters(data):
    # Create arrays that hold times by month per hemisphere:
    for obj in data:
        if minimum_version("1.2"):
            # Convert tank width/length to floats:
            format_as_type(obj, as_float, "tank_width", "tank_length")

            # Convert some fields to int:
            format_as_type(
                obj, as_int, "number", "sell_nook", "sell_cj", "sell_flick", "total_catch"
            )

        # Merge catchphrases into an array:
        catchphrase_array = [obj["catchphrase"]]
        if obj["catchphrase2"]:
            catchphrase_array.append(obj["catchphrase2"])
            if "catchphrase3" in obj and obj["catchphrase3"]:
                catchphrase_array.append(obj["catchphrase3"])

        obj["catchphrases"] = catchphrase_array

        # Remove individual catchphrase fields:
        if minimum_version("1.2"):
            del obj["catchphrase"]
            if "catchphrase2" in obj:
                del obj["catchphrase2"]
            if "catchphrase3" in obj:
                del obj["catchphrase3"]

        # Create array of times and corresponding months for those times:
        if maximum_version("1.2"):
            availability_array_north = [{"months": obj["time_n_months"], "time": obj["time"]}]
            availability_array_south = [{"months": obj["time_s_months"], "time": obj["time"]}]
            if len(obj["time2"]) > 0:
                availability_array_north.append(
                    {"months": obj["time2_n_months"], "time": obj["time2"]}
                )
                availability_array_south.append(
                    {"months": obj["time2_s_months"], "time": obj["time2"]}
                )
            obj["availability_north"] = availability_array_north
            obj["availability_south"] = availability_array_south

            # Create arrays for times by month:
            obj["times_by_month_north"] = {
                "1": obj["n_m1_time"],
                "2": obj["n_m2_time"],
                "3": obj["n_m3_time"],
                "4": obj["n_m4_time"],
                "5": obj["n_m5_time"],
                "6": obj["n_m6_time"],
                "7": obj["n_m7_time"],
                "8": obj["n_m8_time"],
                "9": obj["n_m9_time"],
                "10": obj["n_m10_time"],
                "11": obj["n_m11_time"],
                "12": obj["n_m12_time"],
            }
            obj["times_by_month_south"] = {
                "1": obj["s_m1_time"],
                "2": obj["s_m2_time"],
                "3": obj["s_m3_time"],
                "4": obj["s_m4_time"],
                "5": obj["s_m5_time"],
                "6": obj["s_m6_time"],
                "7": obj["s_m7_time"],
                "8": obj["s_m8_time"],
                "9": obj["s_m9_time"],
                "10": obj["s_m10_time"],
                "11": obj["s_m11_time"],
                "12": obj["s_m12_time"],
            }
        else:
            # North and south JSON to separate data by hemisphere
            north = {}
            south = {}

            north["availability_array"] = [{"months": obj["time_n_months"], "time": obj["time"]}]
            south["availability_array"] = [{"months": obj["time_s_months"], "time": obj["time"]}]
            if len(obj["time2"]) > 0:
                north["availability_array"].append(
                    {"months": obj["time2_n_months"], "time": obj["time2"]}
                )
                south["availability_array"].append(
                    {"months": obj["time2_s_months"], "time": obj["time2"]}
                )

            # Create arrays for times by month:
            north["times_by_month"] = {
                "1": obj["n_m1_time"],
                "2": obj["n_m2_time"],
                "3": obj["n_m3_time"],
                "4": obj["n_m4_time"],
                "5": obj["n_m5_time"],
                "6": obj["n_m6_time"],
                "7": obj["n_m7_time"],
                "8": obj["n_m8_time"],
                "9": obj["n_m9_time"],
                "10": obj["n_m10_time"],
                "11": obj["n_m11_time"],
                "12": obj["n_m12_time"],
            }
            south["times_by_month"] = {
                "1": obj["s_m1_time"],
                "2": obj["s_m2_time"],
                "3": obj["s_m3_time"],
                "4": obj["s_m4_time"],
                "5": obj["s_m5_time"],
                "6": obj["s_m6_time"],
                "7": obj["s_m7_time"],
                "8": obj["s_m8_time"],
                "9": obj["s_m9_time"],
                "10": obj["s_m10_time"],
                "11": obj["s_m11_time"],
                "12": obj["s_m12_time"],
            }

            obj["north"] = north
            obj["south"] = south

        # Remove fields that were added to above objects:
        for i in range(1, 13):
            del obj["n_m" + str(i) + "_time"]
            del obj["s_m" + str(i) + "_time"]

        # Remove unneeded time fields:
        if minimum_version("1.2"):
            del obj["time"]
        del obj["time2"]
        del obj["time_n_months"]
        del obj["time_s_months"]
        del obj["time2_n_months"]
        del obj["time2_s_months"]

    return data


def format_art(data):
    # Correct some datatypes

    # Booleans
    format_as_type(data, as_bool, "has_fake")

    # Integers
    format_as_type(data, as_int, "buy", "sell")

    # Floats
    format_as_type(data, as_float, "width", "length")

    if minimum_version("1.6"):
        data["real_info"] = {
            "image_url": data["image_url"],
            "texture_url": data["texture_url"],
            "description": data["description"],
        }
        if data["has_fake"]:
            data["fake_info"] = {
                "image_url": data["fake_image_url"],
                "texture_url": data["fake_texture_url"],
                "description": data["authenticity"],
            }
        else:
            data["fake_info"] = None
        del data["image_url"]
        del data["texture_url"]
        del data["description"]
        del data["fake_image_url"]
        del data["fake_texture_url"]
        del data["authenticity"]
    return data


def format_recipe(data):
    # Correct some datatypes

    # Integers
    format_as_type(data, as_int, "serial_id", "recipes_to_unlock")
    # This can't be included in the format_as_type because of  \/ that condition
    data["sell"] = int("0" + data["sell"]) if data["sell"] != "NA" else 0

    # Change the material# and material#_num columns to be one materials column
    coalesce_fields_as_object_list(
        data, 6, "materials", ("name", "material{}"), ("count", "material{}_num")
    )
    format_coalesced_object_list(data, as_int, "materials", "count")

    coalesce_fields_as_object_list(
        data, 2, "availability", ("from", "diy_availability{}"), ("note", "diy_availability{}_note")
    )

    # Do the same for buy#_price and buy#_currency columns
    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_furniture(data):
    # Integers
    format_as_type(
        data, as_int, "hha_base", "sell", "variation_total", "pattern_total", "custom_kits"
    )

    # Booleans
    format_as_type(data, as_bool, "customizable", "lucky", "door_decor", "unlocked")
    # if data['outdoor'] == '0':
    #     data['outdoor'] = False
    # elif data['outdoor'] == '1':
    #     data['outdoor'] = True
    # if data['sound'] == '0':
    #     data['sound'] = False
    # elif data['sound'] == '1':
    #     data['sound'] = True
    # if data['interactable'] == '0':
    #     data['interactable'] = False
    # elif data['interactable'] == '1':
    #     data['interactable'] = True
    # if data['animated'] == '0':
    #     data['animated'] = False
    # elif data['animated'] == '1':
    #     data['animated'] = True
    # if data['music'] == '0':
    #     data['music'] = False
    # elif data['music'] == '1':
    #     data['music'] = True
    # if data['lighting'] == '0':
    #     data['lighting'] = False
    # elif data['lighting'] == '1':
    #     data['lighting'] = True

    separate_grid_sizes(data)

    coalesce_fields_as_list(data, 2, "themes", "theme{}")

    coalesce_fields_as_list(data, 2, "functions", "function{}")

    coalesce_fields_as_object_list(
        data, 3, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_clothing(data):
    # Integers
    format_as_type(data, as_int, "sell", "variation_total")

    # Booleans
    format_as_type(data, as_bool, "vill_equip", "unlocked")

    # Turn label[1-5] into a list called label_themes
    coalesce_fields_as_list(data, 5, "label_themes", "label{}")

    coalesce_fields_as_list(data, 2, "styles", "style{}")

    coalesce_fields_as_object_list(
        data, 2, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data
    
def format_gyroid(data):
    # Integers
    format_as_type(data, as_int, "hha_base", "sell", "variation_total", "custom_kits", "cyrus_price")

    # Booleans
    format_as_type(data, as_bool, "customizable", "unlocked")

    separate_grid_sizes(data)

    coalesce_fields_as_object_list(
        data, 2, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_photo(data):
    # Integers
    format_as_type(data, as_int, "hha_base", "sell", "custom_kits")

    # Booleans
    format_as_type(data, as_bool, "customizable", "interactable", "unlocked")

    separate_grid_sizes(data)

    coalesce_fields_as_object_list(
        data, 2, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_interior(data):
    # Integers
    format_as_type(data, as_int, "hha_base", "sell")

    # Booleans
    format_as_type(data, as_bool, "unlocked")

    separate_grid_sizes(data)

    coalesce_fields_as_list(data, 2, "themes", "theme{}")

    coalesce_fields_as_list(data, 2, "colors", "color{}")

    coalesce_fields_as_object_list(
        data, 2, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_tool(data):
    # Integers
    format_as_type(data, as_int, "sell", "custom_kits", "hha_base")

    # Booleans
    format_as_type(data, as_bool, "customizable", "unlocked")

    coalesce_fields_as_object_list(
        data, 3, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 2, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_other_item(data):
    # Integers
    format_as_type(
        data,
        as_int,
        "stack",
        "hha_base",
        "sell",
        "material_sort",
        "material_name_sort",
        "material_seasonality_sort",
    )

    # Booleans
    format_as_type(data, as_bool, "is_fence", "edible", "unlocked")

    coalesce_fields_as_object_list(
        data, 3, "availability", ("from", "availability{}"), ("note", "availability{}_note")
    )

    coalesce_fields_as_object_list(
        data, 1, "buy", ("price", "buy{}_price"), ("currency", "buy{}_currency")
    )
    format_coalesced_object_list(data, as_int, "buy", "price")

    return data


def format_variation(data):
    if "color1" in data:
        coalesce_fields_as_list(data, 2, "colors", "color{}")
        data["colors"] = set(data["colors"])
        data["colors"].discard("None")
        data["colors"] = list(data["colors"])
    return data


def stitch_variation_list(items, variations):
    ret = {
        _["name"]: _ for _ in items
    }  # Turn the list of items into a dictionary with the name as the key
    for name in ret:
        ret[name]["variations"] = []  # Initialize every variations list
    for variation in variations:
        if variation["name"] in ret:
            ret[variation["name"]]["variations"].append(format_variation(variation))
            del variation["name"]

    # Drop the keys, basically undo what we did at the start
    ret = list(ret.values())
    # Sort the variations, and remove some fields used for formatting
    processed = []
    for piece in ret:
        if len(piece["variations"]) == 0:  # If we filtered out all the variations, skip this piece
            continue
        processed.append(piece)
    return processed


def stitch_variation(item, variations):
    item["variations"] = []
    for variation in variations:
        item["variations"].append(format_variation(variation))
    return item


def format_fossil_group(data):
    format_as_type(data, as_int, "room")
    return data


def format_fossil(data):
    format_as_type(data, as_bool, "interactable")
    format_as_type(data, as_int, "sell", "hha_base")
    format_as_type(data, as_float, "width", "length")

    coalesce_fields_as_list(data, 2, "colors", "color{}")
    data["colors"] = set(data["colors"])
    data["colors"].discard("None")
    data["colors"] = list(data["colors"])

    return data


def stitch_fossil_group_list(groups, fossils):
    ret = {_["name"]: _ for _ in groups}

    for key in ret:
        ret[key]["fossils"] = []

    for fossil in fossils:
        if fossil["fossil_group"] in ret:
            ret[fossil["fossil_group"]]["fossils"].append(fossil)
            del fossil["fossil_group"]

    ret = [_ for _ in ret.values() if _["fossils"]]
    return ret

import html
import re
from datetime import datetime
from flask import abort, request

from nookipedia.errors import error_response


# Unescape HTML from all field values:
def deep_unescape(data):
    if isinstance(data, str):
        return html.unescape(data)
    elif isinstance(data, (tuple, list)):
        return [deep_unescape(e) for e in data]
    elif isinstance(data, dict):
        return {k: deep_unescape(v) for k, v in data.items()}
    else:
        return data


# Convert month query parameter input into integer:
# Acceptable input: 'current', '1', '01', 'jan', 'january'
def month_to_int(month):
    month = month.lower()
    try:
        if month.isdigit():
            month = month.lstrip("0")
            if month in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
                return str(month)
            else:
                return None
        elif month == "current":
            return datetime.now().strftime("%m").lstrip("0")
        else:
            switcher = {
                "jan": "1",
                "feb": "2",
                "mar": "3",
                "apr": "4",
                "may": "5",
                "jun": "6",
                "jul": "7",
                "aug": "8",
                "sep": "9",
                "oct": "10",
                "nov": "11",
                "dec": "12",
            }

            return switcher.get(month.lower()[0:3], None)
    except:
        return None


# Convert month query parameter input into string name:
# Acceptable input: '1', '01', 'jan', 'january'
def month_to_string(month):
    month = month.lower()
    try:
        if month.isdigit():
            month = month.lstrip("0")
            if month in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
                switcher = {
                    "1": "January",
                    "2": "February",
                    "3": "March",
                    "4": "April",
                    "5": "May",
                    "6": "June",
                    "7": "July",
                    "8": "August",
                    "9": "September",
                    "10": "October",
                    "11": "November",
                    "12": "December",
                }

                return switcher.get(month.lower()[0:3], None)
            else:
                return None
        else:
            switcher = {
                "jan": "January",
                "feb": "February",
                "mar": "March",
                "apr": "April",
                "may": "May",
                "jun": "June",
                "jul": "July",
                "aug": "August",
                "sep": "September",
                "oct": "October",
                "nov": "November",
                "dec": "December",
            }

            return switcher.get(month.lower()[0:3], None)
    except:
        return None


def as_bool(value):
    if value == "0":
        return False
    elif value == "1":
        return True
    else:
        return value


def as_int(value):
    return int("0" + value)


def as_float(value):
    return float("0" + value)


def format_as_type(data, formatter, *args):
    for field in args:
        if field in data:
            data[field] = formatter(data[field])


def format_coalesced_object_list(data, formatter, name, *fields):
    for obj in data[name]:
        for field in fields:
            if field in obj:
                obj[field] = formatter(obj[field])


def format_coalesced_list(data, formatter, name):
    data[name] = [formatter(_) for _ in data[name]]


def separate_grid_sizes(data):
    if data["grid_size"]:
        grid_width, grid_length = data["grid_size"].split(
            "\u00d7"
        )  # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
        data["grid_width"] = float(grid_width)
        data["grid_length"] = float(grid_length)
    else:
        data["grid_width"] = ""
        data["grid_length"] = ""
    del data["grid_size"]


def coalesce_fields_as_object_list(data, elements, output_name, *fields):
    names = [_[0] for _ in fields]
    keys = [tuple(_[1].format(i) for _ in fields) for i in range(1, elements + 1)]
    data[output_name] = []
    # Go through and create a JSON object list
    for key_group in keys:
        if len(data[key_group[0]]) == 0:
            break
        obj = {names[i]: data[key] for i, key in enumerate(key_group)}
        data[output_name].append(obj)
    # Delete the elements afterwards
    for key_group in keys:
        for key in key_group:
            del data[key]


def coalesce_fields_as_list(data, elements, name, field_format):
    data[name] = []
    keys = [field_format.format(_) for _ in range(1, elements + 1)]
    for key in keys:
        if (len(data[key])) == 0:
            break
        data[name].append(data[key])
    for key in keys:
        del data[key]


def minimum_version(version):
    return between_version(version, None)


def maximum_version(version):
    return between_version(None, version)


def exact_version(version):
    return between_version(version, version)


def between_version(minimum, maximum):
    version = request.headers.get("Accept-Version", "latest")
    if version == "latest":
        return maximum is None
    pattern = r"^(\d+)(?:\.(\d+)(?:\.(\d+))?)?$"
    version_match = re.match(pattern, version)
    minimum_match = re.match(pattern, minimum or "")
    maximum_match = re.match(pattern, maximum or "")
    if version_match is None:
        abort(
            400,
            description=error_response(
                "Invalid header arguments",
                "Accept-Version must be `#`, `#.#`, `#.#.#`, or latest. (defaults to latest, if not supplied)",
            ),
        )
    elif minimum is not None and minimum_match is None:
        abort(
            500,
            description=error_response(
                "Error while checking Accept-Version",
                "Minimum version must be `#`, `#.#`, or `#.#.#`",
            ),
        )
    elif maximum is not None and maximum_match is None:
        abort(
            500,
            description=error_response(
                "Error while checking Accept-Version",
                "Maximum version must be `#`, `#.#`, or `#.#.#`",
            ),
        )
    else:
        version_numbers = version_match.groups()
        minimum_numbers = minimum_match.groups() if minimum is not None else (None, None, None)
        maximum_numbers = maximum_match.groups() if maximum is not None else (None, None, None)
        for val, min_val, max_val in zip(version_numbers, minimum_numbers, maximum_numbers):
            if val is None:
                return True
            v = int(val)
            if max_val is not None and v > int(max_val):
                return False
            if min_val is not None and v < int(min_val):
                return False
        return True


def params_where(params, where):
    """Puts a where condition into the parameters;\n
    `params` is a dict\n
    `where` is a list of condition strings"""
    if where:
        params["where"] = " AND ".join(where)


def generate_fields(*fields):
    return ",".join(fields)

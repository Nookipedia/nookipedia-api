import requests
import sqlite3
import uuid
import json
import configparser
from datetime import datetime
from flask import Flask
from flask import abort
from flask import request
from flask import jsonify
from flask import current_app
from flask import g
from flask_cors import CORS
from flask_caching import Cache
import flask_monitoringdashboard as dashboard

#################################
# INSTANTIATE APP COMPONENTS
#################################

# GET CONFIG:
config = configparser.ConfigParser()
config.read('config.ini')

# SET CONSTANTS:
BASE_URL_WIKI = config.get('APP', 'BASE_URL_WIKI')
BASE_URL_API = config.get('APP', 'BASE_URL_API')
DATABASE = config.get('DB', 'DATABASE')
DB_KEYS = config.get('DB', 'DB_KEYS')
DB_ADMIN_KEYS = config.get('DB', 'DB_ADMIN_KEYS')

# INSTANTIATE APP:
app = Flask(__name__)
CORS(app)
app.config['JSON_SORT_KEYS'] = False  # Prevent from automatically sorting JSON alphabetically
app.config['SECRET_KEY'] = config.get('APP', 'SECRET_KEY')

# SET CACHE:
cache = Cache(config={'CACHE_TYPE': 'simple'})
cache.init_app(app)

# SET UP DASHBOARD:
DASHBOARD_CONFIGS = config.get('APP', 'DASHBOARD_CONFIGS')


def configure_dashboard(app):
    def group_by_user():
        # Grab UUID from header or query param
        if request.headers.get('X-API-KEY'):
            request_uuid = request.headers.get('X-API-KEY')
        elif request.args.get('api_key'):
            request_uuid = request.args.get('api_key')

        # Check db for project details:
        row = query_db('SELECT key, email, project FROM ' + DB_KEYS + ' WHERE key = ?', [request_uuid], one=True)
        # If project details exist, use that as group_by; else, just use UUID
        if row[2]:
            return str(row[2] + ' (' + row[0] + ')')
        else:
            return row[0]

    dashboard.config.group_by = group_by_user
    dashboard.config.init_from(file=DASHBOARD_CONFIGS)
    dashboard.bind(app)
configure_dashboard(app)

#################################
# SET ERROR HANDLERS
#################################


@app.errorhandler(400)
def error_bad_request(e):
    response = e.get_response()
    if 'title' in e.description:
        response.data = json.dumps({
            "title": e.description['title'],
            "details": e.description['details'],
        })
    else:
        response.data = json.dumps({
            "title": "Invalid input",
            "details": "Please ensure provided parameters have valid vales.",
        })
    response.content_type = "application/json"
    return response, 400


@app.errorhandler(401)
def error_resource_not_authorized(e):
    response = e.get_response()
    if 'title' in e.description:
        response.data = json.dumps({
            "title": e.description['title'],
            "details": e.description['details'],
        })
    else:
        response.data = json.dumps({
            "title": "Unauthorized.",
            "details": "Failed to authorize client for requested action.",
        })
    response.content_type = "application/json"
    return response, 401


@app.errorhandler(404)
def error_resource_not_found(e):
    response = e.get_response()
    if 'title' in e.description:
        response.data = json.dumps({
            "title": e.description['title'],
            "details": e.description['details'],
        })
    else:
        response.data = json.dumps({
            "title": "Resource not found.",
            "details": "Please ensure requested resource exists.",
        })
    response.content_type = "application/json"
    return response, 404


@app.errorhandler(405)
def error_invalid_method(e):
    response = e.get_response()
    if 'title' in e.description:
        response.data = json.dumps({
            "title": e.description['title'],
            "details": e.description['details'],
        })
    else:
        response.data = json.dumps({
            "title": "Method not allowed.",
            "details": "The method you requested (GET, POST, etc.) is not valid for this endpoint.",
        })
    response.content_type = "application/json"
    return response, 405


@app.errorhandler(500)
def error_server(e):
    response = e.get_response()
    if 'title' in e.description:
        response.data = json.dumps({
            "title": e.description['title'],
            "details": e.description['details'],
        })
    else:
        response.data = json.dumps({
            "title": "API experienced a fatal error.",
            "details": "Details unknown.",
        })
    response.content_type = "application/json"
    return response, 500


# Format and return json error response body:
def error_response(title, details):
    return {"title": title, "details": details}


#################################
# AUTHORIZATION
#################################

# Check if client's UUID is valid:
def authorize(db, request):
    if request.headers.get('X-API-KEY'):
        request_uuid = request.headers.get('X-API-KEY')
    elif request.args.get('api_key'):
        request_uuid = request.args.get('api_key')
    else:
        abort(401, description=error_response("Failed to validate UUID.", "UUID is either missing or invalid; or, unspecified server occured."))

    try:
        auth_check = query_db('SELECT * FROM ' + db + ' WHERE key = ?', [request_uuid], one=True)
        if auth_check is None:
            abort(401, description=error_response("Failed to validate UUID.", "UUID is either missing or invalid; or, unspecified server occured."))
    except Exception:
        abort(401, description=error_response("Failed to validate UUID.", "UUID is either missing or invalid; or, unspecified server occured."))


#################################
# DATABASE FUNCTIONS
#################################

# Connect to the database:
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


# Close database connection at end of request:
@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Query database:
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


# Insert into database:
def insert_db(query, args=()):
    cur = get_db().execute(query, args)
    get_db().commit()
    cur.close()


#################################
# UTILITIES
#################################

# Convert month query parameter input into integer:
# Acceptable input: 'current', '1', '01', 'jan', 'january'
def month_to_int(month):
    month = month.lower()
    try:
        if month.isdigit():
            month = month.lstrip('0')
            if month in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']:
                return str(month)
            else:
                return None
        elif month == 'current':
            return datetime.now().strftime("%m").lstrip('0')
        else:
            switcher = {
                'jan': '1',
                'feb': '2',
                'mar': '3',
                'apr': '4',
                'may': '5',
                'jun': '6',
                'jul': '7',
                'aug': '8',
                'sep': '9',
                'oct': '10',
                'nov': '11',
                'dec': '12'
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
            month = month.lstrip('0')
            if month in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12']:
                switcher = {
                    '1': 'January',
                    '2': 'February',
                    '3': 'March',
                    '4': 'April',
                    '5': 'May',
                    '6': 'June',
                    '7': 'July',
                    '8': 'August',
                    '9': 'September',
                    '10': 'October',
                    '11': 'November',
                    '12': 'December'
                }

                return switcher.get(month.lower()[0:3], None)
            else:
                return None
        else:
            switcher = {
                'jan': 'January',
                'feb': 'February',
                'mar': 'March',
                'apr': 'April',
                'may': 'May',
                'jun': 'June',
                'jul': 'July',
                'aug': 'August',
                'sep': 'September',
                'oct': 'October',
                'nov': 'November',
                'dec': 'December'
            }

            return switcher.get(month.lower()[0:3], None)
    except:
        return None


#################################
# CARGO HANDLING
#################################

# Make a call to Nookipedia's Cargo API using supplied parameters:
@cache.memoize(3600)
def call_cargo(parameters, request_args):  # Request args are passed in just for the sake of caching
    cargoquery = []
    try:
        # The default query size is 50 normally, we can actually change it here if we wanted
        cargolimit = int(parameters.get('limit', '50'))
        # Copy the current parameters, we'll be changing them a bit in the loop but we want the original still
        nestedparameters = parameters.copy()
        # Set up the offset, if our cargolimit is more than cargomax we'll end up doing more than one query with an offset
        while True:
            nestedparameters['limit'] = str(cargolimit-len(cargoquery))  # Get cargomax items or less at a time
            if nestedparameters['limit'] == '0':  # Check if we've hit the limit
                break
            nestedparameters['offset'] = str(len(cargoquery))
            r = requests.get(url=BASE_URL_API, params=nestedparameters)
            cargochunk = r.json()['cargoquery']
            if len(cargochunk) == 0:  # Check if we've hit the end
                break
            cargoquery.extend(cargochunk)
        print('Return: {}'.format(str(r)))
    except:
        print('Return: {}'.format(str(r)))
        abort(500, description=error_response("Error while calling Nookipedia's Cargo API.", "MediaWiki Cargo request failed for parameters: {}".format(parameters)))

    if not cargoquery:
        return []

    try:
        data = []
        # Check if user requested specific image size and modify accordingly:
        if request.args.get('thumbsize'):
            for obj in cargoquery:
                item = {}

                # Replace all spaces in keys with underscores
                for key in obj['title']:
                    item[key.replace(' ', '_')] = obj['title'][key]

                # Create url to page
                if 'url' in item:
                    item['url'] = 'https://nookipedia.com/wiki/' + item['url'].replace(' ', '_')

                # If image, fetch the CDN thumbnail URL:
                try:
                    print(str(obj['title']))

                    # Only fetch the image if this object actually has an image to fetch
                    if 'image_url' in item:
                        r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + item['image_url'].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        item['image_url'] = r.url

                    # If this is a painting that has a fake, fetch that too
                    if item.get('has_fake', '0') == '1':
                        r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + item['fake_image_url'].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        item['fake_image_url'] = r.url
                except:
                    abort(500, description=error_response("Error while getting image CDN thumbnail URL.", "Failure occured with the following parameters: {}.".format(parameters)))

                data.append(item)
        else:
            for obj in cargoquery:
                item = {}

                # Replace all spaces in keys with underscores
                for key in obj['title']:
                    item[key.replace(' ', '_')] = obj['title'][key]

                # Create url to page
                if 'url' in item:
                    item['url'] = 'https://nookipedia.com/wiki/' + item['url'].replace(' ', '_')

                data.append(item)

        return data
    except:
        abort(500, description=error_response("Error while formatting Cargo response.", "Iterating over cargoquery array in response object failed for the parameters: {}.".format(parameters)))


def format_villager(data):
    games = ['dnm', 'ac', 'e_plus', 'ww', 'cf', 'nl', 'wa', 'nh', 'film', 'hhd', 'pc']

    for obj in data:
        # Set islander to Boolean:
        if obj['islander'] == '0':
            obj['islander'] = False
        elif obj['islander'] == '1':
            obj['islander'] = True

        # Capitalize and standardize debut:
        game_switcher = {
            'DNME+': 'E_PLUS',
            'ACGC': 'AC',
            'ACWW': 'WW',
            'ACCF': 'CF',
            'ACNL': 'NL',
            'ACNLA': 'WA',
            'ACNH': 'NH',
            'ACHHD': 'HHD',
            'ACPC': 'PC'
        }
        if(game_switcher.get(obj['debut'].upper())):
            obj['debut'] = game_switcher.get(obj['debut'].upper())
        else:
            obj['debut'] = obj['debut'].upper()

        # Place prev_phrases in array:
        prev_phrases_array = []
        if obj['prev_phrase'] != '':
            prev_phrases_array.append(obj['prev_phrase'])
            if obj['prev_phrase2']:
                prev_phrases_array.append(obj['prev_phrase2'])
        obj['prev_phrases'] = prev_phrases_array
        del obj['prev_phrase']
        del obj['prev_phrase2']

        # Place NH details in object, if applicable:
        if request.args.get('nhdetails') and (request.args.get('nhdetails') == 'true'):
            if obj['nh'] == '0':
                obj['nh_details'] = None
            else:
                obj['nh_details'] = {
                    'image_url': obj['nh_image_url'],
                    'photo_url': obj['nh_photo_url'],
                    'icon_url': obj['nh_icon_url'],
                    'quote': obj['nh_quote'],
                    'sub-personality': obj['nh_sub-personality'],
                    'catchphrase': obj['nh_catchphrase'],
                    'clothing': obj['nh_clothing'],
                    'clothing_variation': obj['nh_clothing_variation'].replace('amp;', ''),
                    'fav_styles': [],
                    'fav_colors': [],
                    'hobby': obj['nh_hobby'],
                    'house_interior_url': obj['nh_house_interior_url'],
                    'house_exterior_url': obj['nh_house_exterior_url'],
                    'house_wallpaper': obj['nh_wallpaper'],
                    'house_flooring': obj['nh_flooring'],
                    'house_music': obj['nh_music'].replace('amp;', ''),
                    'house_music_note': obj['nh_music_note']
                }
                if obj['nh_fav_style1']:
                    obj['nh_details']['fav_styles'].append(obj['nh_fav_style1'])
                    if obj['nh_fav_style2']:
                        obj['nh_details']['fav_styles'].append(obj['nh_fav_style2'])
                if obj['nh_fav_color1']:
                    obj['nh_details']['fav_colors'].append(obj['nh_fav_color1'])
                    if obj['nh_fav_color2']:
                        obj['nh_details']['fav_colors'].append(obj['nh_fav_color2'])
            del obj['nh_image_url']
            del obj['nh_photo_url']
            del obj['nh_icon_url']
            del obj['nh_quote']
            del obj['nh_sub-personality']
            del obj['nh_catchphrase']
            del obj['nh_clothing']
            del obj['nh_clothing_variation']
            del obj['nh_fav_style1']
            del obj['nh_fav_style2']
            del obj['nh_fav_color1']
            del obj['nh_fav_color2']
            del obj['nh_hobby']
            del obj['nh_house_interior_url']
            del obj['nh_house_exterior_url']
            del obj['nh_wallpaper']
            del obj['nh_flooring']
            del obj['nh_music']
            del obj['nh_music_note']

        # Place game appearances in array:
        games_array = []
        for i in games:
            if obj[i] == '1':
                games_array.append(i.upper())
            del obj[i]
        obj['appearances'] = games_array

    return data


def get_villager_list(limit, tables, join, fields):
    where = None

    # Filter by name:
    if request.args.get('name'):
        villager = request.args.get('name').replace('_', ' ')
        if where:
            where = where + ' AND villager.name = "' + villager + '"'
        else:
            where = 'villager.name = "' + villager + '"'

    # Filter by birth month:
    if request.args.get('birthmonth'):
        month = month_to_string(request.args.get('birthmonth'))
        if where:
            where = where + ' AND villager.birthday_month = "' + month + '"'
        else:
            where = 'villager.birthday_month = "' + month + '"'

    # Filter by birth day:
    if request.args.get('birthday'):
        day = request.args.get('birthday')
        if where:
            where = where + ' AND villager.birthday_day = "' + day + '"'
        else:
            where = 'villager.birthday_day = "' + day + '"'

    # Filter by personality:
    if request.args.get('personality'):
        personality_list = ['lazy', 'jock', 'cranky', 'smug', 'normal', 'peppy', 'snooty', 'sisterly']
        personality = request.args.get('personality').lower()
        if personality not in personality_list:
            abort(400, description=error_response("Could not recognize provided personality.", "Ensure personality is either lazy, jock, cranky, smug, normal, peppy, snooty, or sisterly."))

        if where:
            where = where + ' AND villager.personality = "' + personality + '"'
        else:
            where = 'villager.personality = "' + personality + '"'

    # Filter by species:
    if request.args.get('species'):
        species_list = ['alligator', 'anteater', 'bear', 'bird', 'bull', 'cat', 'cub', 'chicken', 'cow', 'deer', 'dog', 'duck', 'eagle', 'elephant', 'frog', 'goat', 'gorilla', 'hamster', 'hippo', 'horse', 'koala', 'kangaroo', 'lion', 'monkey', 'mouse', 'octopus', 'ostrich', 'penguin', 'pig', 'rabbit', 'rhino', 'sheep', 'squirrel', 'tiger', 'wolf']
        species = request.args.get('species').lower()
        if species not in species_list:
            abort(400, description=error_response("Could not recognize provided species.", "Ensure provided species is valid."))

        if where:
            where = where + ' AND villager.species = "' + species + '"'
        else:
            where = 'villager.species = "' + species + '"'

    # Filter by game:
    if request.args.get('game'):
        games = request.args.getlist("game")
        for game in games:
            game = game.replace('_', ' ')
            if where:
                where = where + ' AND villager.' + game + ' = "1"'
            else:
                where = 'villager.' + game + ' = "1"'

    if where:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'join_on': join, 'fields': fields, 'where': where}
    else:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'join_on': join, 'fields': fields}

    print(str(params))
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        cargo_results = call_cargo(params, request.args)
        results_array = []
        for villager in cargo_results:
            results_array.append(villager['name'])
        return jsonify(results_array)
    else:
        return jsonify(format_villager(call_cargo(params, request.args)))


# For critters, convert north and south month fields into north and south arrays:
def months_to_array(data):
    n_months_array = []
    s_months_array = []
    for obj in data:
        for key in obj:
            if 'n_m' in key:
                if obj[key] == '1':
                    if not (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
                        n_months_array.append(int(key.replace('n_m', '')))
                    else:
                        n_months_array.append(key.replace('n_m', ''))
            if 's_m' in key:
                if obj[key] == '1':
                    if not (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
                        s_months_array.append(int(key.replace('s_m', '')))
                    else:
                        s_months_array.append(key.replace('s_m', ''))
        for i in range(1, 13):
            del obj['n_m' + str(i)]
            del obj['s_m' + str(i)]

        if (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
            obj['n_availability_array'] = n_months_array
            obj['s_availability_array'] = s_months_array
        elif (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.2'))):
            if 'n_availability' in obj:
                obj['months_north'] = obj['n_availability']
                del obj['n_availability']
                obj['months_south'] = obj['s_availability']
                del obj['s_availability']
            obj['months_north_array'] = n_months_array
            obj['months_south_array'] = s_months_array
        else:
            if 'n_availability' in obj:
                obj['north']['months'] = obj['n_availability']
                del obj['n_availability']
                obj['south']['months'] = obj['s_availability']
                del obj['s_availability']
            obj['north']['months_array'] = n_months_array
            obj['south']['months_array'] = s_months_array

        n_months_array = []
        s_months_array = []

    return data


def format_critters(data):
    # Create arrays that hold times by month per hemisphere:
    for obj in data:

        if not (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
            # Convert tank width/length to floats:
            obj['tank_width'] = float(obj['tank_width'])
            obj['tank_length'] = float(obj['tank_length'])

            # Convert some fields to int:
            obj['number'] = int(obj['number'])
            obj['sell_nook'] = int(obj['sell_nook'])
            if 'sell_cj' in obj:
                obj['sell_cj'] = int(obj['sell_cj'])
            if 'sell_flick' in obj:
                obj['sell_flick'] = int(obj['sell_flick'])
            obj['total_catch'] = int(obj['total_catch'])

        # Merge catchphrases into an array:
        catchphrase_array = [obj['catchphrase']]
        if obj['catchphrase2']:
            catchphrase_array.append(obj['catchphrase2'])
            if 'catchphrase3' in obj and obj['catchphrase3']:
                catchphrase_array.append(obj['catchphrase3'])

        obj['catchphrases'] = catchphrase_array

        # Remove individual catchphrase fields:
        if not (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
            del obj['catchphrase']
            if 'catchphrase2' in obj:
                del obj['catchphrase2']
            if 'catchphrase3' in obj:
                del obj['catchphrase3']

        # Create array of times and corresponding months for those times:
        if request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] in ('1.0', '1.1', '1.2'):
            availability_array_north = [{'months': obj['time_n_months'], 'time': obj['time']}]
            availability_array_south = [{'months': obj['time_s_months'], 'time': obj['time']}]
            if len(obj['time2']) > 0:
                availability_array_north.append({'months': obj['time2_n_months'], 'time': obj['time2']})
                availability_array_south.append({'months': obj['time2_s_months'], 'time': obj['time2']})
            obj['availability_north'] = availability_array_north
            obj['availability_south'] = availability_array_south

            # Create arrays for times by month:
            obj['times_by_month_north'] = {
                '1': obj['n_m1_time'],
                '2': obj['n_m2_time'],
                '3': obj['n_m3_time'],
                '4': obj['n_m4_time'],
                '5': obj['n_m5_time'],
                '6': obj['n_m6_time'],
                '7': obj['n_m7_time'],
                '8': obj['n_m8_time'],
                '9': obj['n_m9_time'],
                '10': obj['n_m10_time'],
                '11': obj['n_m11_time'],
                '12': obj['n_m12_time']
            }
            obj['times_by_month_south'] = {
                '1': obj['s_m1_time'],
                '2': obj['s_m2_time'],
                '3': obj['s_m3_time'],
                '4': obj['s_m4_time'],
                '5': obj['s_m5_time'],
                '6': obj['s_m6_time'],
                '7': obj['s_m7_time'],
                '8': obj['s_m8_time'],
                '9': obj['s_m9_time'],
                '10': obj['s_m10_time'],
                '11': obj['s_m11_time'],
                '12': obj['s_m12_time']
            }
        else:
            # North and south JSON to separate data by hemisphere
            north = {}
            south = {}

            north['availability_array'] = [{'months': obj['time_n_months'], 'time': obj['time']}]
            south['availability_array'] = [{'months': obj['time_s_months'], 'time': obj['time']}]
            if len(obj['time2']) > 0:
                north['availability_array'].append({'months': obj['time2_n_months'], 'time': obj['time2']})
                south['availability_array'].append({'months': obj['time2_s_months'], 'time': obj['time2']})

            # Create arrays for times by month:
            north['times_by_month'] = {
                '1': obj['n_m1_time'],
                '2': obj['n_m2_time'],
                '3': obj['n_m3_time'],
                '4': obj['n_m4_time'],
                '5': obj['n_m5_time'],
                '6': obj['n_m6_time'],
                '7': obj['n_m7_time'],
                '8': obj['n_m8_time'],
                '9': obj['n_m9_time'],
                '10': obj['n_m10_time'],
                '11': obj['n_m11_time'],
                '12': obj['n_m12_time']
            }
            south['times_by_month'] = {
                '1': obj['s_m1_time'],
                '2': obj['s_m2_time'],
                '3': obj['s_m3_time'],
                '4': obj['s_m4_time'],
                '5': obj['s_m5_time'],
                '6': obj['s_m6_time'],
                '7': obj['s_m7_time'],
                '8': obj['s_m8_time'],
                '9': obj['s_m9_time'],
                '10': obj['s_m10_time'],
                '11': obj['s_m11_time'],
                '12': obj['s_m12_time']
            }

            obj['north'] = north
            obj['south'] = south

        # Remove fields that were added to above objects:
        for i in range(1, 13):
            del obj['n_m' + str(i) + '_time']
            del obj['s_m' + str(i) + '_time']

        # Remove unneeded time fields:
        if not (request.headers.get('Accept-Version') and (request.headers.get('Accept-Version')[:3] in ('1.0', '1.1'))):
            del obj['time']
        del obj['time2']
        del obj['time_n_months']
        del obj['time_s_months']
        del obj['time2_n_months']
        del obj['time2_s_months']

    return data


def get_critter_list(limit, tables, fields):
    # If client requests specific month:
    if request.args.get('month'):
        calculated_month = month_to_int(request.args.get('month'))
        if not calculated_month:
                abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))

        paramsNorth = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': 'n_m' + calculated_month + '="1"'}
        paramsSouth = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': 's_m' + calculated_month + '="1"'}

        # If client doesn't want all details:
        if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
            n_hemi = months_to_array(call_cargo(paramsNorth, request.args))
            s_hemi = months_to_array(call_cargo(paramsSouth, request.args))

            if n_hemi and s_hemi:
                try:
                    n_hemi_array = []
                    for critter in n_hemi:
                        n_hemi_array.append(critter['name'])
                    s_hemi_array = []
                    for critter in s_hemi:
                        s_hemi_array.append(critter['name'])
                    return jsonify({"month": calculated_month, "north": n_hemi_array, "south": s_hemi_array})
                except:
                    abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
            else:
                abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
        # If client wants full details:
        else:
            n_hemi = months_to_array(format_critters(call_cargo(paramsNorth, request.args)))
            s_hemi = months_to_array(format_critters(call_cargo(paramsSouth, request.args)))

            if n_hemi and s_hemi:
                try:
                    return jsonify({"month": calculated_month, "north": n_hemi, "south": s_hemi})
                except:
                    abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
            else:
                abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
    # If client doesn't specify specific month:
    else:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields}
        if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
            cargo_results = call_cargo(params, request.args)
            results_array = []
            for critter in cargo_results:
                results_array.append(critter['name'])
            return jsonify(results_array)
        else:
            return jsonify(months_to_array(format_critters(call_cargo(params, request.args))))


def format_art(data):
    # Correct some datatypes

    # Booleans
    if data['has_fake'] == '1':
        data['has_fake'] = True
    elif data['has_fake'] == '0':
        data['has_fake'] = False

    # Integers
    data['buy'] = int(data['buy'])
    data['sell'] = int(data['sell'])

    # Floats
    data['width'] = float(data['width'])
    data['length'] = float(data['length'])
    return data


def get_art_list(limit, tables, fields):
    where = None

    if request.args.get('hasfake'):
        fake = request.args.get('hasfake').lower()
        if fake == 'true':
            where = 'has_fake = true'
        elif fake == 'false':
            where = 'has_fake = false'

    if where:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': where}
    else:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields}

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') and request.args.get('excludedetails') == 'true':
        for art in cargo_results:
            results_array.append(art['name'])
    else:
        for art in cargo_results:
            results_array.append(format_art(art))
    return jsonify(results_array)


def format_recipe(data):
    # Correct some datatypes

    # Integers
    data['serial_id'] = int('0' + data['serial_id'])
    data['sell'] = int('0' + data['sell']) if data['sell'] != 'NA' else 0
    data['recipes_to_unlock'] = int('0' + data['recipes_to_unlock'])

    # Change the material# and material#_num columns to be one materials column
    data['materials'] = []
    for i in range(1, 7):  # material1 to material6
        if len(data[f'material{i}']) > 0:
            data['materials'].append({
                'name': data[f'material{i}'],
                'count': int(data[f'material{i}_num'])
            })
        del data[f'material{i}']
        del data[f'material{i}_num']

    data['availability'] = []
    for i in range(1, 3):
        if len(data[f'diy_availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'diy_availability{i}'],
                'note': data[f'diy_availability{i}_note']
            })
        del data[f'diy_availability{i}']
        del data[f'diy_availability{i}_note']

    # Do the same for buy#_price and buy#_currency columns
    data['buy'] = []
    for i in range(1, 3):  # Technically overkill, but it'd be easy to add a third buy column if it ever matters
        if len(data[f'buy{i}_price']) > 0:
            data['buy'].append({
                'price': int(data[f'buy{i}_price']),
                'currency': data[f'buy{i}_currency']
            })
        del data[f'buy{i}_price']
        del data[f'buy{i}_currency']
    return data


def get_recipe_list(limit, tables, fields):
    where = None

    if 'material' in request.args:
        materials = request.args.getlist('material')
        if len(materials) > 6:
            abort(400, description=error_response('Invalid arguments', 'Cannot have more than six materials'))
        for m in materials:
            m.replace('_', ' ')
            if where is None:
                where = '(material1 = "{0}" or material2 = "{0}" or material3 = "{0}" or material4 = "{0}" or material5 = "{0}" or material6 = "{0}")'.format(m)
            else:
                where += ' AND (material1 = "{0}" or material2 = "{0}" or material3 = "{0}" or material4 = "{0}" or material5 = "{0}" or material6 = "{0}")'.format(m)

    if where is not None:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': where}
    else:
        params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields}

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') == 'true':
        for recipe in cargo_results:
            results_array.append(recipe['name'])
    else:
        for recipe in cargo_results:
            results_array.append(format_recipe(recipe))
    return jsonify(results_array)


#################################
# STATIC RENDERS
#################################
@app.route('/')
def static_index():
    return current_app.send_static_file('index.html')


@app.route('/doc')
def static_doc():
    return current_app.send_static_file('doc.html')


#################################
# ENDPOINTS
#################################

# Generate client key, admins only:
@app.route('/admin/gen_key', methods=['POST'])
def generate_key():
    authorize(DB_ADMIN_KEYS, request)

    try:
        new_uuid = str(uuid.uuid4())
        email = ''
        if 'email' in request.form:
            email = str(request.form['email'])
        project = ''
        if 'project' in request.form:
            project = str(request.form['project'])
        insert_db('INSERT INTO ' + DB_KEYS + ' VALUES("' + new_uuid + '","' + email + '","' + project + '")')
        return jsonify({'uuid': new_uuid, 'email': email, 'project': project})
    except:
        abort(500, description=error_response("Failed to create new client UUID.", "UUID generation, or UUID insertion into keys table, failed."))


# Villagers
@app.route('/villagers', methods=['GET'])
def get_villager_all():
    authorize(DB_KEYS, request)

    limit = '500'
    tables = 'villager'
    join = ''
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name'
    elif request.args.get('nhdetails') and (request.args.get('nhdetails') == 'true'):
        tables = 'villager,nh_villager,nh_house'
        join = 'villager._pageName=nh_villager._pageName,villager._pageName=nh_house._pageName'
        fields = 'villager.name,villager._pageName=url,villager.name,villager.alt_name,villager.title_color,villager.text_color,villager.id,villager.image_url,villager.species,villager.personality,villager.gender,villager.birthday_month,villager.birthday_day,villager.sign,villager.quote,villager.phrase,villager.prev_phrase,villager.prev_phrase2,villager.clothing,villager.islander,villager.debut,villager.dnm,villager.ac,villager.e_plus,villager.ww,villager.cf,villager.nl,villager.wa,villager.nh,villager.film,villager.hhd,villager.pc,nh_villager.image_url=nh_image_url,nh_villager.photo_url=nh_photo_url,nh_villager.icon_url=nh_icon_url,nh_villager.quote=nh_quote,nh_villager.sub_personality=nh_sub-personality,nh_villager.catchphrase=nh_catchphrase,nh_villager.clothing=nh_clothing,nh_villager.clothing_variation=nh_clothing_variation,nh_villager.fav_style1=nh_fav_style1,nh_villager.fav_style2=nh_fav_style2,nh_villager.fav_color1=nh_fav_color1,nh_villager.fav_color2=nh_fav_color2,nh_villager.hobby=nh_hobby,nh_house.interior_image_url=nh_house_interior_url,nh_house.exterior_image_url=nh_house_exterior_url,nh_house.wallpaper=nh_wallpaper,nh_house.flooring=nh_flooring,nh_house.music=nh_music,nh_house.music_note=nh_music_note'
    else:
        fields = 'name,_pageName=url,alt_name,title_color,text_color,id,image_url,species,personality,gender,birthday_month,birthday_day,sign,quote,phrase,prev_phrase,prev_phrase2,clothing,islander,debut,dnm,ac,e_plus,ww,cf,nl,wa,nh,film,hhd,pc'

    return get_villager_list(limit, tables, join, fields)


# All New Horizons fish
@app.route('/nh/fish', methods=['GET'])
def get_nh_fish_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_fish'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,catchphrase3,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons fish
@app.route('/nh/fish/<string:fish>', methods=['GET'])
def get_nh_fish(fish):
    authorize(DB_KEYS, request)
    fish = fish.replace('_', ' ')
    limit = '1'
    tables = 'nh_fish'
    fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,catchphrase3,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + fish + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])


# All New Horizons bugs
@app.route('/nh/bugs', methods=['GET'])
def get_nh_bug_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_bug'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons bug
@app.route('/nh/bugs/<string:bug>', methods=['GET'])
def get_nh_bug(bug):
    authorize(DB_KEYS, request)

    bug = bug.replace('_', ' ')
    limit = '1'
    tables = 'nh_bug'
    fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + bug + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])


# All New Horizons sea creatures
@app.route('/nh/sea', methods=['GET'])
def get_nh_sea_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_sea_creature'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons sea creature
@app.route('/nh/sea/<string:sea>', methods=['GET'])
def get_nh_sea(sea):
    authorize(DB_KEYS, request)

    sea = sea.replace('_', ' ')
    limit = '1'
    tables = 'nh_sea_creature'
    fields = 'name,_pageName=url,number,image_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + sea + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])


@app.route('/nh/art/<string:art>', methods=['GET'])
def get_nh_art(art):
    authorize(DB_KEYS, request)

    art = art.replace('_', ' ')
    limit = '1'
    tables = 'nh_art'
    fields = 'name,_pageName=url,image_url,has_fake,fake_image_url,art_name,author,year,art_style,description,buy_price=buy,sell,availability,authenticity,width,length'
    where = f'name="{art}"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}"))
    else:
        return jsonify(format_art(cargo_results[0]))


@app.route('/nh/art', methods=['GET'])
def get_nh_art_all():
    authorize(DB_KEYS, request)

    limit = '50'
    tables = 'nh_art'
    if request.args.get('excludedetails', 'false') == 'true':
        fields = 'name'
    else:
        fields = 'name,_pageName=url,image_url,has_fake,fake_image_url,art_name,author,year,art_style,description,buy_price=buy,sell,availability,authenticity,width,length'

    return get_art_list(limit, tables, fields)


@app.route('/nh/recipe/<string:recipe>', methods=['GET'])
def get_nh_recipe(recipe):
    authorize(DB_KEYS, request)

    recipe = recipe.replace('_', ' ')
    limit = '1'
    tables = 'nh_recipe'
    fields = '_pageName=url,en_name=name,image_url,serial_id,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,recipes_to_unlock,diy_availability1,diy_availability1_note,diy_availability2,diy_availability2_note,material1,material1_num,material2,material2_num,material3,material3_num,material4,material4_num,material5,material5_num,material6,material6_num'
    where = f'en_name="{recipe}"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}"))
    else:
        return jsonify(format_recipe(cargo_results[0]))


@app.route('/nh/recipe', methods=['GET'])
def get_nh_recipe_all():
    authorize(DB_KEYS, request)

    limit = '600'
    tables = 'nh_recipe'
    fields = '_pageName=url,en_name=name,image_url,serial_id,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,recipes_to_unlock,diy_availability1,diy_availability1_note,diy_availability2,diy_availability2_note,material1,material1_num,material2,material2_num,material3,material3_num,material4,material4_num,material5,material5_num,material6,material6_num'

    return get_recipe_list(limit, tables, fields)

if __name__ == '__main__':
    app.run(host='127.0.0.1')

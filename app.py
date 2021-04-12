import requests
import sqlite3
import uuid
import json
import html
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

# Unescape HTML from all field values:
def deep_unescape(data):
    if isinstance(data, str):
        return html.unescape(data)
    elif isinstance(data, (tuple, list)):
        return [deep_unescape(e) for e in data]
    elif isinstance(data, dict):
        return {k:deep_unescape(v) for k,v in data.items()}
    else: 
        return data

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
@cache.memoize(43200)
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
        for obj in cargoquery:
            item = {}

            # Replace all spaces in keys with underscores
            for key in obj['title']:
                item[key.replace(' ', '_')] = obj['title'][key]

            item = deep_unescape(item)

            # Create url to page
            if 'url' in item:
                item['url'] = 'https://nookipedia.com/wiki/' + item['url'].replace(' ', '_')

            if request.args.get('thumbsize'):
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

        return data
    except:
        abort(500, description=error_response("Error while formatting Cargo response.", "Iterating over cargoquery array in response object failed for the parameters: {}.".format(parameters)))


def format_villager(data):
    games = ['dnm', 'ac', 'e_plus', 'ww', 'cf', 'nl', 'wa', 'nh', 'film', 'hhd', 'pc']

    for obj in data:
        if request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] in ('1.0', '1.1', '1.2', '1.3'):
            if obj['personality'] == 'Big sister':
                obj['personality'] = 'Sisterly'
            if obj['species'] == 'Bear cub':
                obj['species'] = 'Cub'
            if obj['species'] == 'Rhinoceros':
                obj['species'] = 'Rhino'

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
                    'clothing_variation': obj['nh_clothing_variation'],
                    'fav_styles': [],
                    'fav_colors': [],
                    'hobby': obj['nh_hobby'],
                    'house_interior_url': obj['nh_house_interior_url'],
                    'house_exterior_url': obj['nh_house_exterior_url'],
                    'house_wallpaper': obj['nh_wallpaper'],
                    'house_flooring': obj['nh_flooring'],
                    'house_music': obj['nh_music'],
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
        villager = request.args.get('name').replace('_', ' ').capitalize()
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
        personality_list = ['lazy', 'jock', 'cranky', 'smug', 'normal', 'peppy', 'snooty', 'sisterly', 'big sister']
        personality = request.args.get('personality').lower()
        if personality not in personality_list:
            abort(400, description=error_response("Could not recognize provided personality.", "Ensure personality is either lazy, jock, cranky, smug, normal, peppy, snooty, or sisterly/big sister."))

        if personality == 'sisterly':
            personality = 'big sister'

        if where:
            where = where + ' AND villager.personality = "' + personality + '"'
        else:
            where = 'villager.personality = "' + personality + '"'

    # Filter by species:
    if request.args.get('species'):
        species_list = ['alligator', 'anteater', 'bear', 'bear cub', 'bird', 'bull', 'cat', 'cub', 'chicken', 'cow', 'deer', 'dog', 'duck', 'eagle', 'elephant', 'frog', 'goat', 'gorilla', 'hamster', 'hippo', 'horse', 'koala', 'kangaroo', 'lion', 'monkey', 'mouse', 'octopus', 'ostrich', 'penguin', 'pig', 'rabbit', 'rhino', 'rhinoceros', 'sheep', 'squirrel', 'tiger', 'wolf']
        species = request.args.get('species').lower()
        if species not in species_list:
            abort(400, description=error_response("Could not recognize provided species.", "Ensure provided species is valid."))

        if species == 'cub':
            species = 'bear cub'
        elif species == 'rhino':
            species = 'rhinoceros'

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

def format_furniture(data):
    #Integers
    data['hha_base'] = int('0' + data['hha_base'])
    data['sell'] = int('0' + data['sell'])
    data['variation_total'] = int('0' + data['variation_total'])
    data['pattern_total'] = int('0' + data['pattern_total'])
    data['custom_kits'] = int('0' + data['custom_kits'])

    #Booleans
    if data['customizable'] == '0':
        data['customizable'] = False
    elif data['customizable'] == '1':
        data['customizable'] = True
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
    if data['door_decor'] == '0':
        data['door_decor'] = False
    elif data['door_decor'] == '1':
        data['door_decor'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    grid_width, grid_height = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
    data['grid_width'] = float(grid_width)
    data['grid_height'] = float(grid_height)
    del data['grid_size']

    data['themes'] = []
    for i in range(1, 3):
        theme = f'theme{i}'
        if len(data[theme]) > 0:
            data['themes'].append(data[theme])
        del data[theme]

    data['functions'] = []
    for i in range(1, 3):
        function = f'function{i}'
        if len(data[function]) > 0:
            data['functions'].append(data[function])
        del data[function]

    data['availability'] = []
    for i in range(1, 4):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

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

def get_furniture_list(limit,tables,fields):
    where = []

    if 'category' in request.args:
        categories_list = ['housewares', 'miscellaneous', 'wall-mounted']
        category = request.args.get('category').lower()
        if category not in categories_list:
            abort(400, description=error_response('Could not recognize provided category.','Ensure category is either housewares, miscellaneous, or wall-mounted.'))
        where.append('category = "{0}"'.format(category))

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    ret = [format_furniture(_) for _ in cargo_results]
    return ret

def get_furniture_variation_list(limit,tables,fields,orderby):
    where = []

    if 'color' in request.args:
        colors_list = ['aqua', 'beige', 'black', 'blue', 'brown', 'colorful', 'gray', 'green', 'orange', 'pink', 'purple', 'red', 'white', 'yellow']
        colors = [color.lower() for color in request.args.getlist('color')]
        for color in colors:
            if color not in colors_list:
                abort(400, description=error_response('Could not recognize provided color.','Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.'))
        if len(colors) == 1: # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2: # If they filtered both colors
            where.append('((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(colors[0],colors[1]))
        else:
            abort(400, description=error_response('Invalid arguments','Cannot have more than two colors'))

    if 'pattern' in request.args:
        pattern = request.args['pattern']
        where.append(f'pattern = "{pattern}"')

    if 'variation' in request.args:
        variation = request.args['variation']
        where.append(f'variation = "{variation}"')

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    return cargo_results

def format_clothing(data):
    # Integers
    data['sell'] = int('0' + data['sell'])
    data['variation_total'] = int('0' + data['variation_total'])

    # Booleans
    if data['vill_equip'] == '0':
        data['vill_equip'] = False
    elif data['vill_equip'] == '1':
        data['vill_equip'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    # Turn label[1-5] into a list called label
    data['label'] = []
    for i in range(1,6):
        label = f'label{i}'
        if len(data[label]) > 0:
            data['label'].append(data[label])
        del data[label]

    data['styles'] = []
    for i in range(1,3):
        style = f'style{i}'
        if len(data[style]) > 0:
            data['styles'].append(data[style])
        del data[style]

    data['availability'] = []
    for i in range(1, 3):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

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

def get_clothing_list(limit,tables,fields):
    where = []

    if 'category' in request.args:
        categories_list = ['tops', 'bottoms', 'dress-up', 'headware', 'accessories', 'socks', 'shoes', 'bags', 'umbrellas']
        category = request.args.get('category').lower()
        if category not in categories_list:
            abort(400, description=error_response('Could not recognize provided category.','Ensure category is either tops, bottoms, dress-up, headware, accessories, socks, shoes, bags, or umbrellas.'))
        where.append('category = "{0}"'.format(category))

    if 'style' in request.args:
        styles_list = ['active', 'cool', 'cute', 'elegant', 'gorgeous', 'simple']
        styles = [style.lower() for style in request.args.getlist('style')]
        for style in styles:
            if style not in styles_list:
                abort(400, description=error_response('Could not recognize provided style.','Ensure style is either active, cool, cute, elegant, gorgeous, or simple.'))
        if len(styles) == 1: # If they only filtered one style
            where.append('(style1 = "{0}" OR style2 = "{0}")'.format(styles[0]))
        elif len(styles) == 2: # If they filtered both styles
            where.append('((style1 = "{0}" AND style2 = "{1}") OR (style1 = "{1}" AND style2 = "{0}"))'.format(styles[0],styles[1]))
        else:
            abort(400, description=error_response('Invalid arguments','Cannot have more than two styles'))

    if 'label' in request.args:
        label_list = ['comfy', 'everyday', 'fairy tale', 'formal', 'goth', 'outdoorsy', 'party', 'sporty', 'theatrical', 'vacation', 'work']
        label = request.args.get('label').lower()
        if label not in label_list:
            abort(400, description=error_response('Could not recognize provided Label theme.','Ensure Label theme is either comfy, everyday, fairy tale, formal, goth, outdoorsy, party, sporty, theatrical, vacation, or work.'))
        where.append('(label1 = "{0}" OR label2 = "{0}" OR label3 = "{0}" OR label4 = "{0}" OR label5 = "{0}")'.format(label))

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    ret = [format_clothing(_) for _ in cargo_results]
    return ret

def format_photo(data):
    # Integers
    data['hha_base'] = int('0' + data['hha_base'])
    data['sell'] = int('0' + data['sell'])
    data['custom_kits'] = int('0' + data['custom_kits'])

    # Booleans
    if data['customizable'] == '0':
        data['customizable'] = False
    elif data['customizable'] == '1':
        data['customizable'] = True
    if data['interactable'] == '0':
        data['interactable'] = False
    elif data['interactable'] == '1':
        data['interactable'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    grid_width, grid_height = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
    data['grid_width'] = float(grid_width)
    data['grid_height'] = float(grid_height)
    del data['grid_size']

    data['availability'] = []
    for i in range(1, 3):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

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

def get_photo_list(limit,tables,fields):
    where = []

    if 'category' in request.args:
        categories_list = ['photos', 'posters']
        category = request.args.get('category').lower()
        if category not in categories_list:
            abort(400, description=error_response('Could not recognize provided category.','Ensure category is either photos or posters.'))
        where.append('category = "{0}"'.format(category))

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    ret = [format_photo(_) for _ in cargo_results]
    return ret

def format_interior(data):
    # Integers
    data['hha_base'] = int('0' + data['hha_base'])
    data['sell'] = int('0' + data['sell'])

    # Booleans
    if data['vfx'] == '0':
        data['vfx'] = False
    elif data['vfx'] == '1':
        data['vfx'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    if data['grid_size']:
        grid_width, grid_height = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
        data['grid_width'] = float(grid_width)
        data['grid_height'] = float(grid_height)
    else:
        data['grid_width'] = ""
        data['grid_height'] = ""
    del data['grid_size']

    data['themes'] = []
    for i in range(1,3):
        theme = f'theme{i}'
        if len(data[theme]) > 0:
            data['themes'].append(data[theme])
        del data[theme]

    data['colors'] = []
    for i in range(1,3):
        color = f'color{i}'
        if len(data[color]) > 0:
            data['colors'].append(data[color])
        del data[color]


    data['availability'] = []
    for i in range(1, 3):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

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

def get_interior_list(limit,tables,fields):
    where = []

    if 'color' in request.args:
        colors_list = ['aqua', 'beige', 'black', 'blue', 'brown', 'colorful', 'gray', 'green', 'orange', 'pink', 'purple', 'red', 'white', 'yellow']
        colors = [color.lower() for color in request.args.getlist('color')]
        for color in colors:
            if color not in colors_list:
                abort(400, description=error_response('Could not recognize provided color.','Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.'))
        if len(colors) == 1: # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2: # If they filtered both colors
            where.append('((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(colors[0],colors[1]))
        else:
            abort(400, description=error_response('Invalid arguments','Cannot have more than two colors'))

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') == 'true':
        for interior in cargo_results:
            results_array.append(interior['name'])
    else:
        for interior in cargo_results:
            results_array.append(format_interior(interior))
    return jsonify(results_array)

def format_tool(data):
    # Integers
    data['sell'] = int('0' + data['sell'])
    data['custom_kits'] = int('0' + data['custom_kits'])
    data['hha_base'] = int('0' + data['hha_base'])

    # Booleans
    if data['customizable'] == '0':
        data['customizable'] = False
    elif data['customizable'] == '1':
        data['customizable'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    data['availability'] = []
    for i in range(1, 4):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

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

def get_tool_list(limit,tables,fields):
    where = []

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    ret = [format_tool(_) for _ in cargo_results]
    return ret

def format_other_item(data):
    # Integers
    data['stack'] = int('0' + data['stack'])
    data['hha_base'] = int('0' + data['hha_base'])
    data['sell'] = int('0' + data['sell'])
    data['material_sort'] = int('0' + data['material_sort'])
    data['material_name_sort'] = int('0' + data['material_name_sort'])
    data['material_seasonality_sort'] = int('0' + data['material_seasonality_sort'])

    # Booleans
    if data['is_fence'] == '0':
        data['is_fence'] = False
    elif data['is_fence'] == '1':
        data['is_fence'] = True
    if data['edible'] == '0':
        data['edible'] = False
    elif data['edible'] == '1':
        data['edible'] = True
    if data['unlocked'] == '0':
        data['unlocked'] = False
    elif data['unlocked'] == '1':
        data['unlocked'] = True

    data['availability'] = []
    for i in range(1, 4):
        if len(data[f'availability{i}']) > 0:
            data['availability'].append({
                'from': data[f'availability{i}'],
                'note': data[f'availability{i}_note']
            })
        del data[f'availability{i}']
        del data[f'availability{i}_note']

    data['buy'] = []
    for i in range(1, 2):  # Technically overkill, but it'd be easy to add a third buy column if it ever matters
        if len(data[f'buy{i}_price']) > 0:
            data['buy'].append({
                'price': int(data[f'buy{i}_price']),
                'currency': data[f'buy{i}_currency']
            })
        del data[f'buy{i}_price']
        del data[f'buy{i}_currency']

    return data

def get_other_item_list(limit,tables,fields):
    where = []

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') == 'true':
        for item in cargo_results:
            results_array.append(item['name'])
    else:
        for item in cargo_results:
            results_array.append(format_other_item(item))
    return jsonify(results_array)

def get_variation_list(limit,tables,fields,orderby):
    where = []

    if 'color' in request.args:
        colors_list = ['aqua', 'beige', 'black', 'blue', 'brown', 'colorful', 'gray', 'green', 'orange', 'pink', 'purple', 'red', 'white', 'yellow']
        colors = [color.lower() for color in request.args.getlist('color')]
        for color in colors:
            if color not in colors_list:
                abort(400, description=error_response('Could not recognize provided color.','Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.'))
        if len(colors) == 1: # If they only filtered one color
            where.append('(color1 = "{0}" OR color2 = "{0}")'.format(colors[0]))
        elif len(colors) == 2: # If they filtered both colors
            where.append('((color1 = "{0}" AND color2 = "{1}") OR (color1 = "{1}" AND color2 = "{0}"))'.format(colors[0],colors[1]))
        else:
            abort(400, description=error_response('Invalid arguments','Cannot have more than two colors'))

    if 'variation' in request.args:
        variation = request.args['variation']
        where.append(f'variation = "{variation}"')

    if len(where) == 0:
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit }
    else:
        where = ' AND '.join(where)
        params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit, 'where': where }

    cargo_results = call_cargo(params, request.args)
    return cargo_results

def format_variation(data):
    if 'color1' in data:
        colors = set()
        for i in range(1,3):
            color = f'color{i}'
            if len(data[color]) > 0:
                colors.add(data[color])
            del data[color]
        colors.discard('None')
        data['colors'] = list(colors)
    return data

def stitch_variation_list(items,variations):
    ret = { _['identifier']:_ for _ in items } # Turn the list of items into a dictionary with the identifier as the key
    for identifier in ret:
        ret[identifier]['variations'] = [] #Initialize every variations list
    for variation in variations:
        if variation['identifier'] in ret:
            ret[variation['identifier']]['variations'].append(format_variation(variation))
            del variation['identifier']

    # Drop the keys, basically undo what we did at the start
    ret = list(ret.values())
    # Sort the variations, and remove some fields used for formatting
    processed = []
    for piece in ret:
        if len(piece['variations']) == 0: # If we filtered out all the variations, skip this piece
            continue
        del piece['identifier']
        processed.append(piece)
    return processed

def stitch_variation(item,variations):
    item['variations'] = []
    for variation in variations:
        item['variations'].append(format_variation(variation))
        del variation['identifier']
    del item['identifier']
    return item

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


@app.route('/nh/recipes/<string:recipe>', methods=['GET'])
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


@app.route('/nh/recipes', methods=['GET'])
def get_nh_recipe_all():
    authorize(DB_KEYS, request)

    limit = '800'
    tables = 'nh_recipe'
    fields = '_pageName=url,en_name=name,image_url,serial_id,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,recipes_to_unlock,diy_availability1,diy_availability1_note,diy_availability2,diy_availability2_note,material1,material1_num,material2,material2_num,material3,material3_num,material4,material4_num,material5,material5_num,material6,material6_num'

    return get_recipe_list(limit, tables, fields)

@app.route('/nh/furniture/<string:furniture>',methods=['GET'])
def get_nh_furniture(furniture):
    authorize(DB_KEYS, request)

    furniture = furniture.replace('_',' ')
    furniture_limit = '1'
    furniture_tables = 'nh_furniture'
    furniture_fields = 'identifier,_pageName=url,en_name=name,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,lucky,lucky_season,function1,function2,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,variation_total,pattern_total,customizable,custom_kits,custom_kit_type,custom_body_part,custom_pattern_part,grid_size,length,width,height,door_decor,version_added,unlocked,notes'#'
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

@app.route('/nh/furniture',methods=['GET'])
def get_nh_furniture_all():
    authorize(DB_KEYS, request)

    if 'thumbsize' in request.args:
        abort(400, description=error_response('Invalid arguments','Cannot have thumbsize in a group item request'))

    furniture_limit = '1200'
    furniture_tables = 'nh_furniture'
    furniture_fields = 'identifier,_pageName=url,en_name=name,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,lucky,lucky_season,function1,function2,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,variation_total,pattern_total,customizable,custom_kits,custom_kit_type,custom_body_part,custom_pattern_part,grid_size,length,width,height,door_decor,version_added,unlocked,notes'#'
    variation_limit = '5350'
    variation_tables = 'nh_furniture_variation'
    variation_fields = 'identifier,variation,pattern,image_url,color1,color2'
    variation_orderby = 'variation_number,pattern_number'

    furniture_list = get_furniture_list(furniture_limit, furniture_tables, furniture_fields)
    variation_list = get_furniture_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(furniture_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['en_name'] for _ in stitched])
    else:
        return jsonify(stitched)

@app.route('/nh/clothing/<string:clothing>',methods=['GET'])
def get_nh_clothing(clothing):
    authorize(DB_KEYS, request)

    clothing = clothing.replace('_',' ')
    clothing_limit = '1'
    clothing_tables = 'nh_clothing'
    clothing_fields = 'identifier,_pageName=url,en_name=name,category,style1,style2,label1,label2,label3,label4,label5,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,variation_total,vill_equip,seasonality,version_added,unlocked,notes'
    clothing_where = f'en_name = "{clothing}"'
    clothing_params = { 'action': 'cargoquery', 'format': 'json', 'tables': clothing_tables, 'fields': clothing_fields, 'where': clothing_where, 'limit': clothing_limit }
    variation_limit = '10'
    variation_tables = 'nh_clothing_variation'
    variation_fields = 'identifier,variation,image_url,color1,color2'
    variation_where = f'en_name = "{clothing}"'
    variation_orderby = 'variation_number'
    variation_params = { 'action': 'cargoquery', 'format': 'json', 'tables': variation_tables, 'fields': variation_fields, 'where': variation_where, 'order_by': variation_orderby, 'limit': variation_limit }

    cargo_results = call_cargo(clothing_params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {clothing_params}"))
    else:
        piece = format_clothing(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))

@app.route('/nh/clothing',methods=['GET'])
def get_nh_clothing_all():
    authorize(DB_KEYS, request)

    if 'thumbsize' in request.args:
        abort(400, description=error_response('Invalid arguments','Cannot have thumbsize in a group item request'))

    clothing_limit = '1350'
    clothing_tables = 'nh_clothing'
    clothing_fields = 'identifier,_pageName=url,en_name=name,category,style1,style2,label1,label2,label3,label4,label5,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,variation_total,vill_equip,seasonality,version_added,unlocked,notes'
    variation_limit = '5000'
    variation_tables = 'nh_clothing_variation'
    variation_fields = 'identifier,variation,image_url,color1,color2'
    variation_orderby = 'variation_number'

    clothing_list = get_clothing_list(clothing_limit, clothing_tables, clothing_fields)
    variation_list = get_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(clothing_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['en_name'] for _ in stitched])
    else:
        return jsonify(stitched)

@app.route('/nh/photos/<string:photo>',methods=['GET'])
def get_nh_photo(photo):
    authorize(DB_KEYS, request)

    photo = photo.replace('_',' ')
    photo_limit = '1'
    photo_tables = 'nh_photo'
    photo_fields = 'identifier,_pageName=url,en_name=name,category,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,customizable,custom_kits,custom_body_part,grid_size,interactable,length,width,height,version_added,unlocked'
    photo_where = f'en_name = "{photo}"'
    photo_params = { 'action': 'cargoquery', 'format': 'json', 'tables': photo_tables, 'fields': photo_fields, 'where': photo_where, 'limit': photo_limit }
    variation_limit = '10'
    variation_tables = 'nh_photo_variation'
    variation_fields = 'identifier,variation,image_url,color1,color2'
    variation_where = f'en_name = "{photo}"'
    variation_orderby = 'variation_number'
    variation_params = { 'action': 'cargoquery', 'format': 'json', 'tables': variation_tables, 'fields': variation_fields, 'where': variation_where, 'order_by': variation_orderby, 'limit': variation_limit }

    cargo_results = call_cargo(photo_params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {photo_params}"))
    else:
        piece = format_photo(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))

@app.route('/nh/photos',methods=['GET'])
def get_nh_photo_all():
    authorize(DB_KEYS, request)

    if 'thumbsize' in request.args:
        abort(400, description=error_response('Invalid arguments','Cannot have thumbsize in a group item request'))

    photo_limit = '900'
    photo_tables = 'nh_photo'
    photo_fields = 'identifier,_pageName=url,en_name=name,category,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,customizable,custom_kits,custom_body_part,grid_size,interactable,length,width,height,version_added,unlocked'
    variation_limit = '3700'
    variation_tables = 'nh_photo_variation'
    variation_fields = 'identifier,variation,image_url,color1,color2'
    variation_orderby = 'variation_number'

    photo_list = get_photo_list(photo_limit, photo_tables, photo_fields)
    variation_list = get_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(photo_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['en_name'] for _ in stitched])
    else:
        return jsonify(stitched)

@app.route('/nh/tools/<string:tool>',methods=['GET'])
def get_nh_tool(tool):
    authorize(DB_KEYS, request)

    tool = tool.replace('_',' ')
    tool_limit = '1'
    tool_tables = 'nh_tool'
    tool_fields = 'identifier,_pageName=url,en_name=name,uses,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,customizable,custom_kits,custom_body_part,version_added,unlocked,notes'
    tool_where = f'en_name = "{tool}"'
    tool_params = { 'action': 'cargoquery', 'format': 'json', 'tables': tool_tables, 'fields': tool_fields, 'where': tool_where, 'limit': tool_limit }
    variation_limit = '10'
    variation_tables = 'nh_tool_variation'
    variation_fields = 'identifier,variation,image_url'
    variation_where = f'en_name = "{tool}"'
    variation_params = { 'action': 'cargoquery', 'format': 'json', 'tables': variation_tables, 'fields': variation_fields, 'where': variation_where, 'order_by': variation_orderby, 'limit': variation_limit }
    variation_orderby = 'variation_number'

    cargo_results = call_cargo(tool_params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {tool_params}"))
    else:
        piece = format_tool(cargo_results[0])
        variations = call_cargo(variation_params, request.args)
        return jsonify(stitch_variation(piece, variations))

@app.route('/nh/tools',methods=['GET'])
def get_nh_tool_all():
    authorize(DB_KEYS, request)

    if 'thumbsize' in request.args:
        abort(400, description=error_response('Invalid arguments','Cannot have thumbsize in a group item request'))

    tool_limit = '100'
    tool_tables = 'nh_tool'
    tool_fields = 'identifier,_pageName=url,en_name=name,uses,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,customizable,custom_kits,custom_body_part,version_added,unlocked,notes'
    variation_limit = '300'
    variation_tables = 'nh_tool_variation'
    variation_fields = 'identifier,variation,image_url'
    variation_orderby = 'variation_number'

    tool_list = get_tool_list(tool_limit, tool_tables, tool_fields)
    variation_list = get_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(tool_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['en_name'] for _ in stitched])
    else:
        return jsonify(stitched)

@app.route('/nh/interior/<string:interior>', methods=['GET'])
def get_nh_interior(interior):
    authorize(DB_KEYS, request)

    interior = interior.replace('_', ' ')
    limit = '1'
    tables = 'nh_interior'
    fields = '_pageName=url,en_name=name,image_url,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,grid_size,vfx,color1,color2,version_added,unlocked,notes'
    where = f'en_name="{interior}"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}"))
    else:
        return jsonify(format_interior(cargo_results[0]))

@app.route('/nh/interior', methods=['GET'])
def get_nh_interior_all():
    authorize(DB_KEYS, request)

    limit = '650'
    tables = 'nh_interior'
    fields = '_pageName=url,en_name=name,image_url,category,item_series,item_set,theme1,theme2,hha_category,tag,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,grid_size,vfx,color1,color2,version_added,unlocked,notes'

    return get_interior_list(limit, tables, fields)

@app.route('/nh/items/<string:item>', methods=['GET'])
def get_nh_item(item):
    authorize(DB_KEYS, request)

    item = item.replace('_', ' ')
    limit = '1'
    tables = 'nh_item'
    fields = '_pageName=url,en_name=name,image_url,stack,hha_base,buy1_price,buy1_currency,sell,is_fence,material_type,material_seasonality,material_sort,material_name_sort,material_seasonality_sort,edible,plant_type,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,version_added,unlocked,notes'
    where = f'en_name="{item}"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if len(cargo_results) == 0:
        abort(404, description=error_response("No data was found for the given query.", f"MediaWiki Cargo request succeeded by nothing was returned for the parameters: {params}"))
    else:
        return jsonify(format_other_item(cargo_results[0]))

@app.route('/nh/items', methods=['GET'])
def get_nh_item_all():
    authorize(DB_KEYS, request)

    limit = '400'
    tables = 'nh_item'
    fields = '_pageName=url,en_name=name,image_url,stack,hha_base,buy1_price,buy1_currency,sell,is_fence,material_type,material_seasonality,material_sort,material_name_sort,material_seasonality_sort,edible,plant_type,availability1,availability1_note,availability2,availability2_note,availability3,availability3_note,version_added,unlocked,notes'

    return get_other_item_list(limit, tables, fields)

if __name__ == '__main__':
    app.run(host='127.0.0.1')

import re
import requests
import sqlite3
import uuid
import json
import html
import configparser
from datetime import datetime
from dateutil import parser
from itertools import permutations
from itertools import combinations
from flask import Flask
from flask import abort
from flask import request
from flask import jsonify
from flask import current_app
from flask import g
from flask_cors import CORS
from flask_caching import Cache
from pylibmc import Client as PylibmcClient
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
BOT_USERNAME = config.get('AUTH', 'BOT_USERNAME')
BOT_PASS = config.get('AUTH', 'BOT_PASS')
DATABASE = config.get('DB', 'DATABASE')
DB_KEYS = config.get('DB', 'DB_KEYS')
DB_ADMIN_KEYS = config.get('DB', 'DB_ADMIN_KEYS')

# INSTANTIATE APP:
app = Flask(__name__)
CORS(app)
app.config['JSON_SORT_KEYS'] = False  # Prevent from automatically sorting JSON alphabetically
app.config['SECRET_KEY'] = config.get('APP', 'SECRET_KEY')

# SET CACHE:
cache = Cache(config={
    'CACHE_TYPE': 'memcached',
    'CACHE_MEMCACHED_SERVERS': PylibmcClient(['127.0.0.1'])
})
cache.init_app(app)

# SET COOKIE STORE FOR SESSION DATA:
cache.set('session', None)

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


# Login to MediaWiki as a bot account:
def mw_login():
    try:
        params = { 'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json' }
        r = requests.get(url=BASE_URL_API, params=params)
        try:
            login_token = r.json()['query']['tokens']['logintoken']
        except:
            print('Failed to login to MediaWiki (could not retrieve login token).')
            return False

        if login_token:
            data = { 'action': 'login', 'lgname': BOT_USERNAME, 'lgpassword': BOT_PASS, 'lgtoken': login_token, 'format': 'json' }
            r = requests.post(url=BASE_URL_API, data=data, cookies=requests.utils.dict_from_cookiejar(r.cookies))
            rJson = r.json()

            if 'login' not in rJson:
                print('Failed to login to MediaWiki (POST to login failed): ' + str(rJson))
                return False
            if 'result' not in rJson['login']:
                print('Failed to login to MediaWiki (POST to login failed): ' + str(rJson))
                return False
            if rJson['login']['result'] == 'Success':
                print('Successfully logged into MediaWiki API.')
                cache.set('session', { 'token': login_token, 'cookie': r.cookies }, 2592000) # Expiration set to max of 30 days
                return True
            else:
                print('Failed to login to MediaWiki (POST to login failed): ' + str(rJson))
                return False
        else:
            print('Failed to login to MediaWiki (could not retrieve login token).')
            return False
    except:
        print('Failed to login to MediaWiki.')
        return False

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

def as_bool(value):
    if value == '0':
        return False
    elif value == '1':
        return True
    else:
        return value

def as_int(value):
    return int('0' + value)

def as_float(value):
    return float('0' + value)

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

def coalesce_fields_as_object_list(data, elements, output_name, *fields):
    names = [_[0] for _ in fields]
    keys = [tuple([_[1].format(i) for _ in fields]) for i in range(1, elements + 1)]
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

#################################
# CARGO HANDLING
#################################

# Make a call to Nookipedia's Cargo API using supplied parameters:
@cache.memoize(43200)
def call_cargo(parameters, request_args):  # Request args are passed in just for the sake of caching
    # cargoquery holds all queried items
    cargoquery = []

    # Default query size limit is 50 but can be changed by incoming params:
    cargolimit = int(parameters.get('limit', '50'))

    # Copy the passed-in parameters:
    nestedparameters = parameters.copy()

    try:
        while True:
            # Subtract number of queried items from limit:
            nestedparameters['limit'] = str(cargolimit-len(cargoquery))

            # If no items are left to query, break
            if nestedparameters['limit'] == '0':
                break

            # Set offset to number of items queried so far:
            nestedparameters['offset'] = str(len(cargoquery))

            # Check if we should authenticate to the wiki (500 is limit for unauthenticated queries):
            if BOT_USERNAME and int(parameters.get('limit', '50')) > 500:
                nestedparameters['assert'] = 'bot'
                session = cache.get('session') # Get session from memcache

                # Session may be null from startup or cache explusion:
                if not session:
                    mw_login()
                    session = cache.get('session')

                # Make authorized request:
                r = requests.get(url=BASE_URL_API, params=nestedparameters, headers={'Authorization': 'Bearer ' + session['token']}, cookies=session['cookie'])
                if 'error' in r.json():
                    # Error may be due to invalid token; re-try login:
                    if mw_login():
                        session = cache.get('session')
                        r = requests.get(url=BASE_URL_API, params=nestedparameters, headers={'Authorization': 'Bearer ' + session['token']}, cookies=session['cookie'])

                        # If it errors again, make request without auth:
                        if 'error' in r.json():
                            del nestedparameters['assert']
                            r = requests.get(url=BASE_URL_API, params=nestedparameters)
                    else:
                        del nestedparameters['assert']
                        r = requests.get(url=BASE_URL_API, params=nestedparameters)
            else:
                r = requests.get(url=BASE_URL_API, params=nestedparameters)

            cargochunk = r.json()['cargoquery']
            if len(cargochunk) == 0:  # If nothing was returned, break
                break

            cargoquery.extend(cargochunk)

            # If queried items are < limit and there are no warnings, we've received everything:
            if ('warnings' not in r.json()) and (len(cargochunk) < cargolimit):
                break
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
                    # Only fetch the image if this object actually has an image to fetch
                    if 'image_url' in item:
                        r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + item['image_url'].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        item['image_url'] = r.url

                    # If this is a painting that has a fake, fetch that too
                    if item.get('has_fake', '0') == '1':
                        r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + item['fake_image_url'].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        item['fake_image_url'] = r.url

                    # Same goes for the renders
                    if 'render_url' in item:
                        r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + item['render_url'].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        item['render_url'] = r.url
                except:
                    abort(500, description=error_response("Error while getting image CDN thumbnail URL.", "Failure occured with the following parameters: {}.".format(parameters)))

            data.append(item)

        return data
    except:
        abort(500, description=error_response("Error while formatting Cargo response.", "Iterating over cargoquery array in response object failed for the parameters: {}.".format(parameters)))

def minimum_version(version):
    return between_version(version, None)

def maximum_version(version):
    return between_version(None, version)

def exact_version(version):
    return between_version(version, version)

def between_version(minimum, maximum):
    version = request.headers.get('Accept-Version', 'latest')
    if version == 'latest':
        return maximum is None
    version_match = re.match(r'^(\d+)(?:\.(\d+)(?:\.(\d+))?)?$', version)
    minimum_match = re.match(r'^(\d+)(?:\.(\d+)(?:\.(\d+))?)?$', minimum or '')
    maximum_match = re.match(r'^(\d+)(?:\.(\d+)(?:\.(\d+))?)?$', maximum or '')
    if version_match is None:
        abort(400, description=error_response('Invalid header arguments','Accept-Version must be `#`, `#.#`, `#.#.#`, or latest. (defaults to latest, if not supplied)'))
    elif minimum is not None and minimum_match is None:
        abort(500, description=error_response('Error while checking Accept-Version','Minimum version must be `#`, `#.#`, or `#.#.#`'))
    elif maximum is not None and maximum_match is None:
        abort(500, description=error_response('Error while checking Accept-Version','Maximum version must be `#`, `#.#`, or `#.#.#`'))
    else:
        version_numbers = version_match.groups()
        minimum_numbers = minimum_match.groups() if minimum is not None else ('0', '0', '0')
        maximum_numbers = maximum_match.groups() if maximum is not None else ('999', '999', '999')
        for version_number, minimum_number, maximum_number in zip(version_numbers, minimum_numbers, maximum_numbers):
            if maximum_number is None:
                return True
            if minimum_number is None:
                return True
            if version_number is None:
                return True
            if int(version_number) < int(minimum_number):
                return False
            if int(version_number) > int(maximum_number):
                return False
        return True

class WhereBuilder(list):
    def where(self, url_name, column_name, *, formatter = None, validate = None, post_validation_formatter = None,
                 value = None, format_column = False):
        arg = request.args.get(url_name)
        if arg is not None:
            if formatter:
                arg = formatter(arg)
            if validate:
                validate(arg)
            if post_validation_formatter:
                arg = post_validation_formatter(arg)
            if format_column:
                column_name.format(arg)
            if value:
                arg = value
            self.append(f'{column_name} = "{arg}"')
    def where_list(self, url_name, column_name, *, formatter = None, validate = None, post_validation_formatter = None,
                 value = None, format_column = False, count = None, numbered = False):
        """Used when you need to match a parameter in the list, will match something like [Tan, Tan] if color=Tan&color=Black is searched"""
        args = request.args.getlist(url_name)
        if numbered and not count:
            abort(500, description=error_response('There was an error building the cargo query', '`WHERE` statement needs a count if you have numbered'))
        if args:
            if count and len(args) > count:
                abort(400, description=error_response('Invalid arguments', f'Cannot have more than {count} of \'{url_name}\''))
            for arg in args:
                if formatter:
                    arg = formatter(arg)
                if validate:
                    validate(arg)
                if post_validation_formatter:
                    arg = post_validation_formatter(arg)
                column = column_name
                if format_column and not numbered:
                    column = column.format(arg)
                if value is not None:
                    arg = value
                if numbered:
                    self.append('(' + ' OR '.join([f'{column.format(_)} = "{arg}"' for _ in range(1, count + 1)]) + ')')
                else:
                    self.append(f'{column} = "{arg}"')
    def where_all_list(self, url_name, column_name, *, formatter = None, validate = None, post_validation_formatter = None,
                    value = None, count = None):
        """Used when you need to match every parameter in the list, so it will only match if it contains every argument"""
        args = request.args.getlist(url_name)
        if not count:
            abort(500, description=error_response('There was an error building the cargo query', '`WHERE` statement needs a count if you\'re using all_list'))
        if args:
            if count and len(args) > count:
                abort(400, description=error_response('Invalid arguments', f'Cannot have more than {count} of \'{url_name}\''))
            for i, _ in enumerate(args):
                if formatter:
                    args[i] = formatter(args[i])
                if validate:
                    validate(args[i])
                if post_validation_formatter:
                    args[i] = post_validation_formatter(args[i])
            ret = []
            perms = [_ for _ in permutations(args)]
            params = [column_name.format(i) for i in range(1, count + 1)]
            combs = [_ for _ in combinations(params, len(args))]
            for key in combs:
                for value in perms:
                    ret.append(' AND '.join([f'{_[0]} = "{_[1]}"' for _ in zip(key,value)]))
            self.append('(' + ') OR ('.join(ret) + ')')

    def where_raw(self, raw):
        """Adds `raw` as a condition without any formatting or anything, just as you would build it previously"""
        self.append(raw)
    def build(self):
        return ' AND '.join(self)
    def build_into_params(self, params):
        if self:
            where = self.build()
            params['where'] = where

def validate_personality(personality):
    personality_list = ['lazy', 'jock', 'cranky', 'smug', 'normal', 'peppy', 'snooty', 'sisterly', 'big sister']
    if personality not in personality_list:
        abort(400, description=error_response("Could not recognize provided personality.", "Ensure personality is either lazy, jock, cranky, smug, normal, peppy, snooty, or sisterly/big sister."))

def validate_species(species):
    species_list = ['alligator', 'anteater', 'bear', 'bear cub', 'bird', 'bull', 'cat', 'cub', 'chicken', 'cow', 'deer', 'dog', 'duck', 'eagle', 'elephant', 'frog', 'goat', 'gorilla', 'hamster', 'hippo', 'horse', 'koala', 'kangaroo', 'lion', 'monkey', 'mouse', 'octopus', 'ostrich', 'penguin', 'pig', 'rabbit', 'rhino', 'rhinoceros', 'sheep', 'squirrel', 'tiger', 'wolf']
    if species not in species_list:
        abort(400, description=error_response("Could not recognize provided species.", "Ensure provided species is valid."))

# Underscore is to avoid hiding the `type` builtin
def validate_type(_type):
    if _type not in ['Event', 'Nook Shopping', 'Birthday', 'Recipes']:
        abort(400, description=error_response("Could not recognize provided type.", "Ensure type is either Event, Nook Shopping, Birthday, or Recipes."))

def validate_furniture_category(category):
    categories_list = ['housewares', 'miscellaneous', 'wall-mounted']
    if category not in categories_list:
        abort(400, description=error_response('Could not recognize provided category.','Ensure category is either housewares, miscellaneous, or wall-mounted.'))

def validate_clothing_category(category):
    categories_list = ['tops', 'bottoms', 'dress-up', 'headware', 'accessories', 'socks', 'shoes', 'bags', 'umbrellas']
    if category not in categories_list:
        abort(400, description=error_response('Could not recognize provided category.','Ensure category is either tops, bottoms, dress-up, headware, accessories, socks, shoes, bags, or umbrellas.'))

def validate_clothing_style(style):
    styles_list = ['active', 'cool', 'cute', 'elegant', 'gorgeous', 'simple']
    if style not in styles_list:
        abort(400, description=error_response('Could not recognize provided style.','Ensure style is either active, cool, cute, elegant, gorgeous, or simple.'))

def validate_clothing_label(label):
    label_list = ['comfy', 'everyday', 'fairy tale', 'formal', 'goth', 'outdoorsy', 'party', 'sporty', 'theatrical', 'vacation', 'work']
    if label not in label_list:
        abort(400, description=error_response('Could not recognize provided Label theme.','Ensure Label theme is either comfy, everyday, fairy tale, formal, goth, outdoorsy, party, sporty, theatrical, vacation, or work.'))

def validate_photo_category(category):
    categories_list = ['photos', 'posters']
    if category not in categories_list:
        abort(400, description=error_response('Could not recognize provided category.','Ensure category is either photos or posters.'))

def validate_color(color):
    colors_list = ['aqua', 'beige', 'black', 'blue', 'brown', 'colorful', 'gray', 'green', 'orange', 'pink', 'purple', 'red', 'white', 'yellow']
    if color not in colors_list:
        abort(400, description=error_response('Could not recognize provided color.','Ensure style is either aqua, beige, black, blue, brown, colorful, gray, green, orange, pink, purple, red, white, or yellow.'))

def post_formatter_species(species):
    if species == 'cub':
        return 'bear cub'
    elif species == 'rhino':
        return 'rhinoceros'
    return species

def str_lower_formatter(string):
    return string.lower()

def format_villager(data):
    games = ['dnm', 'ac', 'e_plus', 'ww', 'cf', 'nl', 'wa', 'nh', 'film', 'hhd', 'pc']

    for obj in data:
        if maximum_version('1.3'):
            if obj['personality'] == 'Big sister':
                obj['personality'] = 'Sisterly'
            if obj['species'] == 'Bear cub':
                obj['species'] = 'Cub'
            if obj['species'] == 'Rhinoceros':
                obj['species'] = 'Rhino'

        # Set islander to Boolean:
        format_as_type(obj, as_bool, 'islander')

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
        if request.args.get('nhdetails') == 'true':
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
    builder = WhereBuilder()
    # Filter by name:
    builder.where('name', 'villager.name', formatter = lambda villager: villager.replace('_', ' ').capitalize())
    # Filter by birth month:
    builder.where('birthmonth', 'villgager.birth_month', formatter = lambda month: month_to_string(month))

    # Filter by birth day:
    builder.where('birthday', 'villager.birthday_day')

    # Filter by personality:
    builder.where('personality', 'villager.personality',
        formatter = str_lower_formatter,
        validate = validate_personality,
        post_validation_formatter = lambda personality: 'big sister' if personality == 'sisterly' else personality)
    
    # Filter by species:
    builder.where('species', 'villager.species',
        formatter = str_lower_formatter,
        validate = validate_species,
        post_validation_formatter = post_formatter_species)

    # Filter by game:
    builder.where_list('game','villager.{}',
        formatter = lambda game: game.replace('_', ' '),
        format_column = True,
        value = "1")

    
    params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'join_on': join, 'fields': fields}
    builder.build_into_params(params)

    print(str(params))
    if request.args.get('excludedetails') == 'true':
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
                    if minimum_version('1.2'):
                        n_months_array.append(int(key.replace('n_m', '')))
                    else:
                        n_months_array.append(key.replace('n_m', ''))
            if 's_m' in key:
                if obj[key] == '1':
                    if minimum_version('1.2'):
                        s_months_array.append(int(key.replace('s_m', '')))
                    else:
                        s_months_array.append(key.replace('s_m', ''))
        for i in range(1, 13):
            del obj['n_m' + str(i)]
            del obj['s_m' + str(i)]

        if maximum_version('1.1'):
            obj['n_availability_array'] = n_months_array
            obj['s_availability_array'] = s_months_array
        elif exact_version('1.2'):
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

        if minimum_version('1.2'):
            # Convert tank width/length to floats:
            format_as_type(obj, as_float, 'tank_width', 'tank_length')

            # Convert some fields to int:
            format_as_type(obj, as_int, 'number', 'sell_nook', 'sell_cj', 'sell_flick', 'total_catch')

        # Merge catchphrases into an array:
        catchphrase_array = [obj['catchphrase']]
        if obj['catchphrase2']:
            catchphrase_array.append(obj['catchphrase2'])
            if 'catchphrase3' in obj and obj['catchphrase3']:
                catchphrase_array.append(obj['catchphrase3'])

        obj['catchphrases'] = catchphrase_array

        # Remove individual catchphrase fields:
        if minimum_version('1.2'):
            del obj['catchphrase']
            if 'catchphrase2' in obj:
                del obj['catchphrase2']
            if 'catchphrase3' in obj:
                del obj['catchphrase3']

        # Create array of times and corresponding months for those times:
        if maximum_version('1.2'):
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
        if minimum_version('1.2'):
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
        if request.args.get('excludedetails') == 'true':
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
        if request.args.get('excludedetails') == 'true':
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
    format_as_type(data, as_bool, 'has_fake')

    # Integers
    format_as_type(data, as_int, 'buy', 'sell')

    # Floats
    format_as_type(data, as_float, 'width', 'length')
    return data


def get_art_list(limit, tables, fields):
    builder = WhereBuilder()

    builder.where('hasfake', 'has_fake', formatter = str_lower_formatter)

    params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields}
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') == 'true':
        for art in cargo_results:
            results_array.append(art['name'])
    else:
        for art in cargo_results:
            results_array.append(format_art(art))
    return jsonify(results_array)


def format_recipe(data):
    # Correct some datatypes

    # Integers
    format_as_type(data, as_int, 'serial_id', 'recipes_to_unlock')
    # This can't be included in the format_as_type because of  \/ that condition
    data['sell'] = int('0' + data['sell']) if data['sell'] != 'NA' else 0

    # Change the material# and material#_num columns to be one materials column
    coalesce_fields_as_object_list(data, 6, 'materials', ('name','material{}'), ('count','material{}_num'))
    format_coalesced_object_list(data, as_int, 'materials', 'count')

    coalesce_fields_as_object_list(data, 2, 'availability', ('from', 'diy_availability{}'), ('note', 'diy_availability{}_note'))

    # Do the same for buy#_price and buy#_currency columns
    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')
    
    return data


def get_recipe_list(limit, tables, fields):
    builder = WhereBuilder()

    builder.where_list('material', 'material{}', formatter=lambda material: material.replace('_', ' '), count = 6, numbered = True)

    params = {'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields}
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    results_array = []
    if request.args.get('excludedetails') == 'true':
        for recipe in cargo_results:
            results_array.append(recipe['name'])
    else:
        for recipe in cargo_results:
            results_array.append(format_recipe(recipe))
    return jsonify(results_array)


def get_event_list(limit, tables, fields, orderby):
    builder = WhereBuilder()

    # Filter by date:
    if request.args.get('date'):
        where = None
        date = request.args.get('date')
        today = datetime.today()
        if date == 'today':
            where = 'YEAR(date) = ' + today.strftime('%Y') + ' AND MONTH(date) = ' + today.strftime('%m') + ' AND DAYOFMONTH(date) = ' + today.strftime('%d')
        else:
            try:
                parsed_date = parser.parse(date)
            except:
                abort(400, description=error_response("Could not recognize provided date.", "Ensure date is of a valid date format, or 'today'."))
            if parsed_date.strftime('%Y') not in [str(today.year), str(today.year + 1)]:
                abort(404, description=error_response("No data was found for the given query.", "You must request events from either the current or next year."))
            else:
                where = 'YEAR(date) = ' + parsed_date.strftime('%Y') + ' AND MONTH(date) = ' + parsed_date.strftime('%m') + ' AND DAYOFMONTH(date) = ' + parsed_date.strftime('%d')
         # There's no real way to add this to the WhereBuilder without adding an entire date subsection, so we just add it raw
        builder.where_raw(where)

    # Filter by year:
    builder.where('year', 'YEAR(date)')

    # Filter by month:
    builder.where('month', 'MONTH(date)')

    # Filter by day:
    builder.where('day', 'DAYOFMONTH(date)')

    # Filter by event:
    buider.where('event', 'event')

    # Filter by type:
    builder.where('type', 'type', validate=validate_type)

    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit}
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)

    for event in cargo_results:
        del event['date__precision']

    return jsonify(cargo_results)


def format_furniture(data):
    #Integers
    format_as_type(data, as_int, 'hha_base', 'sell', 'variation_total', 'pattern_total', 'custom_kits')

    #Booleans
    format_as_type(data, as_bool, 'customizable', 'lucky', 'door_decor', 'unlocked')
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

    grid_width, grid_length = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
    data['grid_width'] = float(grid_width)
    data['grid_length'] = float(grid_length)
    del data['grid_size']

    coalesce_fields_as_list(data, 2, 'themes', 'theme{}')

    coalesce_fields_as_list(data, 2, 'functions', 'function{}')

    coalesce_fields_as_object_list(data, 3, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_furniture_list(limit,tables,fields):
    builder = WhereBuilder()

    builder.where('category', 'category', formatter=str_lower_formatter, validate=validate_furniture_category)

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    ret = [format_furniture(_) for _ in cargo_results]
    return ret


def get_furniture_variation_list(limit,tables,fields,orderby):
    builder = WhereBuilder()

    builder.where_all_list('color', 'color{}', formatter=str_lower_formatter, validate=validate_color, count=2)

    builder.where('pattern', 'pattern')

    builder.where('variation', 'variation')

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'order_by': orderby, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    return cargo_results


def format_clothing(data):
    # Integers
    format_as_type(data, as_int, 'sell', 'variation_total')

    # Booleans
    format_as_type(data, as_bool, 'vill_equip', 'unlocked')

    # Turn label[1-5] into a list called label
    coalesce_fields_as_list(data, 5, 'label', 'label{}')

    coalesce_fields_as_list(data, 2, 'styles', 'style{}')

    coalesce_fields_as_object_list(data, 2, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_clothing_list(limit,tables,fields):
    builder = WhereBuilder()

    builder.where('category', 'category', formatter=str_lower_formatter, validate=validate_clothing_category)

    builder.where_all_list('style','style{}', formatter=str_lower_formatter, validate=validate_clothing_style, count=2)

    builder.where_list('label', 'label{}', formatter=str_lower_formatter, validate=validate_clothing_label, numbered=True, count=5)

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    ret = [format_clothing(_) for _ in cargo_results]
    return ret


def format_photo(data):
    # Integers
    format_as_type(data, int, 'hha_base', 'sell', 'custom_kits')

    # Booleans
    format_as_type(data, as_bool, 'customizable', 'interactable', 'unlocked')

    grid_width, grid_length = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
    data['grid_width'] = float(grid_width)
    data['grid_length'] = float(grid_length)
    del data['grid_size']

    coalesce_fields_as_object_list(data, 2, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_photo_list(limit,tables,fields):
    builder = WhereBuilder()

    builder.where('category', 'category', formatter=str_lower_formatter, validate=validate_photo_category)

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    ret = [format_photo(_) for _ in cargo_results]
    return ret


def format_interior(data):
    # Integers
    format_as_type(data, as_int, 'hha_base', 'sell')

    # Booleans
    format_as_type(data, as_bool, 'vfx', 'unlocked')

    if data['grid_size']:
        grid_width, grid_length = data['grid_size'].split("\u00d7") # \u00d7 is the multiplication sign, so 1.0x1.0 => [1.0,1.0]
        data['grid_width'] = float(grid_width)
        data['grid_length'] = float(grid_length)
    else:
        data['grid_width'] = ""
        data['grid_length'] = ""
    del data['grid_size']

    coalesce_fields_as_list(data, 2, 'themes', 'theme{}')

    coalesce_fields_as_list(data, 2, 'colors', 'color{}')

    coalesce_fields_as_object_list(data, 2, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_interior_list(limit,tables,fields):
    builder = WhereBuilder()

    builder.where_all_list('color', 'color{}', formatter=str_lower_formatter, validate=validate_color, count=2)

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

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
    format_as_type(data, as_int, 'sell', 'custom_kits', 'hha_base')

    # Booleans
    format_as_type(data, as_bool, 'customizable', 'unlocked')

    coalesce_fields_as_object_list(data, 3, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 2, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_tool_list(limit,tables,fields):
    builder = WhereBuilder()

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    ret = [format_tool(_) for _ in cargo_results]
    return ret


def format_other_item(data):
    # Integers
    format_as_type(data, as_int, 'stack', 'hha_base', 'sell', 'material_sort', 'material_name_sort', 'material_seasonality_sort')

    # Booleans
    format_as_type(data, as_bool, 'is_fence','edible', 'unlocked')

    coalesce_fields_as_object_list(data, 3, 'availability', ('from', 'availability{}'), ('note', 'availability{}_note'))

    coalesce_fields_as_object_list(data, 1, 'buy', ('price', 'buy{}_price'), ('currency', 'buy{}_currency'))
    format_coalesced_object_list(data, as_int, 'buy', 'price')

    return data


def get_other_item_list(limit,tables,fields):
    builder = WhereBuilder()

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

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
    builder = WhereBuilder()

    builder.where_all_list('color', 'color{}', formatter=str_lower_formatter, validate=validate_color, count=2)

    builder.where('variation', 'variation')

    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'limit': limit }
    builder.build_into_params(params)

    cargo_results = call_cargo(params, request.args)
    return cargo_results


def format_variation(data):
    if 'color1' in data:
        coalesce_fields_as_list(data, 2, 'colors', 'color{}')
        data['colors'] = set(data['colors'])
        data['colors'].discard('None')
        data['colors'] = list(data['colors'])
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
    if request.args.get('excludedetails') == 'true':
        fields = 'name'
    elif request.args.get('nhdetails') == 'true':
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
    if request.args.get('excludedetails') == 'true':
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,catchphrase3,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons fish
@app.route('/nh/fish/<string:fish>', methods=['GET'])
def get_nh_fish(fish):
    authorize(DB_KEYS, request)
    fish = fish.replace('_', ' ')
    limit = '1'
    tables = 'nh_fish'
    fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,catchphrase3,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + fish + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if exact_version('1.0'):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])


# All New Horizons bugs
@app.route('/nh/bugs', methods=['GET'])
def get_nh_bug_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_bug'
    if request.args.get('excludedetails') == 'true':
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons bug
@app.route('/nh/bugs/<string:bug>', methods=['GET'])
def get_nh_bug(bug):
    authorize(DB_KEYS, request)

    bug = bug.replace('_', ' ')
    limit = '1'
    tables = 'nh_bug'
    fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + bug + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if exact_version('1.0'):
            return jsonify(months_to_array(format_critters(cargo_results)))
        else:
            return jsonify(months_to_array(format_critters(cargo_results))[0])


# All New Horizons sea creatures
@app.route('/nh/sea', methods=['GET'])
def get_nh_sea_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_sea_creature'
    if request.args.get('excludedetails') == 'true':
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'

    return get_critter_list(limit, tables, fields)


# Specific New Horizons sea creature
@app.route('/nh/sea/<string:sea>', methods=['GET'])
def get_nh_sea(sea):
    authorize(DB_KEYS, request)

    sea = sea.replace('_', ' ')
    limit = '1'
    tables = 'nh_sea_creature'
    fields = 'name,_pageName=url,number,image_url,render_url,catchphrase,catchphrase2,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length,time,time_n_availability=time_n_months,time_s_availability=time_s_months,time2,time2_n_availability=time2_n_months,time2_s_availability=time2_s_months,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,n_m1_time,n_m2_time,n_m3_time,n_m4_time,n_m5_time,n_m6_time,n_m7_time,n_m8_time,n_m9_time,n_m10_time,n_m11_time,n_m12_time,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,s_m1_time,s_m2_time,s_m3_time,s_m4_time,s_m5_time,s_m6_time,s_m7_time,s_m8_time,s_m9_time,s_m10_time,s_m11_time,s_m12_time'
    where = 'name="' + sea + '"'
    params = {'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where, 'limit': limit}

    cargo_results = call_cargo(params, request.args)
    if cargo_results == []:
        abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
    else:
        if exact_version('1.0'):
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
    if request.args.get('excludedetails') == 'true':
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


@app.route('/nh/events', methods=['GET'])
def get_nh_event_all():
    authorize(DB_KEYS, request)

    limit = '1200'
    tables = 'nh_calendar'
    fields = 'event,date,type,link=url'
    orderby = 'date'

    return get_event_list(limit, tables, fields, orderby)


@app.route('/nh/furniture/<string:furniture>',methods=['GET'])
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


@app.route('/nh/furniture',methods=['GET'])
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
        return jsonify([_['name'] for _ in stitched])
    else:
        return jsonify(stitched)


@app.route('/nh/photos/<string:photo>',methods=['GET'])
def get_nh_photo(photo):
    authorize(DB_KEYS, request)

    photo = photo.replace('_',' ')
    photo_limit = '1'
    photo_tables = 'nh_photo'
    photo_fields = 'identifier,_pageName=url,en_name=name,category,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,customizable,custom_kits,custom_body_part,grid_size,interactable,version_added,unlocked'
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
    photo_fields = 'identifier,_pageName=url,en_name=name,category,hha_base,buy1_price,buy1_currency,buy2_price,buy2_currency,sell,availability1,availability1_note,availability2,availability2_note,customizable,custom_kits,custom_body_part,grid_size,interactable,version_added,unlocked'
    variation_limit = '3700'
    variation_tables = 'nh_photo_variation'
    variation_fields = 'identifier,variation,image_url,color1,color2'
    variation_orderby = 'variation_number'

    photo_list = get_photo_list(photo_limit, photo_tables, photo_fields)
    variation_list = get_variation_list(variation_limit, variation_tables, variation_fields, variation_orderby)
    stitched = stitch_variation_list(photo_list, variation_list)

    if request.args.get('excludedetails') == 'true':
        return jsonify([_['name'] for _ in stitched])
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
        return jsonify([_['name'] for _ in stitched])
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

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
app.config['JSON_SORT_KEYS'] = False # Prevent from automatically sorting JSON alphabetically
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
def error_resource_not_found(e):
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
def error_resource_not_found(e):
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

    except Exception as e:
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
# CARGO HANDLING
#################################

# Make a call to Nookipedia's Cargo API using supplied parameters:
@cache.memoize(300)
def call_cargo(parameters, request_args): # Request args are passed in just for the sake of caching
    try:
        r = requests.get(url = BASE_URL_API, params = parameters)
    except:
        abort(500, description=error_response("Error while calling Nookipedia's Cargo API.", "MediaWiki Cargo request failed for parameters: {}".format(parameters)))

    if not r.json()['cargoquery']:
        return []

    try:
        data = []
        # Check if user requested specific image size and modify accordingly:
        if request.args.get('thumbsize'):
            for obj in r.json()['cargoquery']:
                item = {}
                for key in obj['title']:
                    if key == 'image url': # If image, fetch the CDN thumbnail URL:
                        try:
                            r = requests.get(BASE_URL_WIKI + 'Special:FilePath/' + obj['title'][key].rsplit('/', 1)[-1] + '?width=' + request.args.get('thumbsize'))
                        except:
                            abort(500, description=error_response("Error while getting image CDN thumbnail URL.", "Failure occured with the following parameters: {}.".format(parameters)))
                        item['image_url'] = r.url
                    else:
                        # Replace all spaces in keys with underscores
                        item[key.replace(' ', '_')] = obj['title'][key]
                data.append(item)
        else:
            for obj in r.json()['cargoquery']:
                item = {}
                for key in obj['title']:
                    # Replace all spaces in keys with underscores
                    item[key.replace(' ', '_')] = obj['title'][key]
                data.append(item)

        return data
    except:
        abort(500, description=error_response("Error while formatting Cargo response.", "Iterating over cargoquery array in response object failed for the parameters: {}.".format(parameters)))

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

def months_to_array(data):
    month_fields = ['']
    n_months_array = []
    s_months_array = []
    for obj in data:
        for key in obj:
            if 'n_m' in key:
                if obj[key] == '1':
                    n_months_array.append(key.replace('n_m', ''))
            if 's_m' in key:
                if obj[key] == '1':
                    s_months_array.append(key.replace('s_m', ''))
        for i in range(1, 13):
            del obj['n_m' + str(i)]
            del obj['s_m' + str(i)]

        obj['n_availability_array'] = n_months_array
        obj['s_availability_array'] = s_months_array
        n_months_array = []
        s_months_array = []

    return data

def get_critter_list(limit, tables, fields):
    # If client wants details for certain month:
    if request.args.get('month'):
        calculated_month = month_to_int(request.args.get('month'))
        if not calculated_month:
            abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))

        where = 'n_m' + calculated_month + '="1"'
        params = { 'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': where }
        n_hemi = call_cargo(params, request.args)
        n_hemi = months_to_array(n_hemi)

        where = 's_m' + calculated_month + '="1"'
        params = { 'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': where }
        s_hemi = call_cargo(params, request.args)
        s_hemi = months_to_array(s_hemi)

        if n_hemi and s_hemi:
            try:
                # If client doesn't want details, return two arrays of strings called north and south:
                if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
                    n_hemi_array = []
                    for critter in n_hemi:
                        n_hemi_array.append(critter['name'])
                    s_hemi_array = []
                    for critter in s_hemi:
                        s_hemi_array.append(critter['name'])
                    return jsonify({ "month": calculated_month, "north": n_hemi_array, "south": s_hemi_array })
                else:
                    # If client wants all details, return array of objects:
                    return jsonify({ "month": calculated_month, "north": n_hemi, "south": s_hemi })
            except:
                abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
        else:
            abort(400, description=error_response("Failed to identify the provided month filter.", "Provided month filter {} was not recognized as a valid month.".format(request.args.get('month'))))
    else:
        params = { 'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields }
        if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
            cargo_results = call_cargo(params, request.args)
            results_array = []
            for critter in cargo_results:
                results_array.append(critter['name'])
            return jsonify(results_array)
        else:
            return jsonify(months_to_array(call_cargo(params, request.args)))

def format_villager(data):
    games = ['dnm', 'ac', 'e_plus', 'ww', 'cf', 'nl', 'wa', 'nh', 'film', 'hhd', 'pc']

    for obj in data:
        # Set islander to Boolean:
        if obj['islander'] == '0':
            obj['islander'] = False
        elif obj['islander'] == '1':
            obj['islander'] = True

        # Capitalize debut:
        obj['debut'] = obj['debut'].upper()

        # Place prev_phrases in array:
        prev_phrases = []
        if obj['prev_phrase'] != '':
            prev_phrases.append(obj['prev_phrase'])
            if obj['prev_phrase2']:
                prev_phrases.append(obj['prev_phrase2'])
        obj['prev_phrases'] = prev_phrases
        del obj['prev_phrase']
        del obj['prev_phrase2']

        # Place game appearances in array:
        games_array = []
        for key in obj:
            if obj[key] == '1':
                if key in games:
                    games_array.append(key.upper())
        for i in ['dnm', 'ac', 'e_plus', 'ww', 'cf', 'nl', 'wa', 'nh', 'film', 'hhd', 'pc']:
            del obj[i]
        obj['appearances'] = games_array

    return data

def get_villager_list(limit, tables, fields):
    where = None

    # Filter by name:
    if request.args.get('name'):
        villager = request.args.get('name')
        villager = villager.replace('_', ' ')
        if where:
            where = where + ' AND name = "' + villager + '"'
        else:
            where = 'name = "' + villager + '"'

    # Filter by personality:
    if request.args.get('personality'):
        personality_list = ['lazy', 'jock', 'cranky', 'smug', 'normal', 'peppy', 'snooty', 'sisterly']
        personality = request.args.get('personality').lower()
        if personality not in personality_list:
            abort(400, description=error_response("Could not recognize provided personality.", "Ensure personality is either lazy, jock, cranky, smug, normal, peppy, snooty, or sisterly."))

        if where:
            where = where + ' AND personality = "' + personality + '"'
        else:
            where = 'personality = "' + personality + '"'

    # Filter by species:
    if request.args.get('species'):
        species_list = ['alligator', 'anteater', 'bear', 'bird', 'bull', 'cat', 'cub', 'chicken', 'cow', 'deer', 'dog', 'duck', 'eagle', 'elephant', 'frog', 'goat', 'gorilla', 'hamster', 'hippo', 'horse', 'koala', 'kangaroo', 'lion', 'monkey', 'mouse', 'octopus', 'ostrich', 'penguin', 'pig', 'rabbit', 'rhino', 'sheep', 'squirrel', 'tiger', 'wolf']
        species = request.args.get('species').lower()
        if species not in species_list:
            abort(400, description=error_response("Could not recognize provided species.", "Ensure provided species is valid."))

        if where:
            where = where + ' AND species = "' + species + '"'
        else:
            where = 'species = "' + species + '"'
    
    if where:
        params = { 'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields, 'where': where }
    else:
        params = { 'action': 'cargoquery', 'format': 'json', 'limit': limit, 'tables': tables, 'fields': fields }

    print(str(params))
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        cargo_results = call_cargo(params, request.args)
        results_array = []
        for villager in cargo_results:
            results_array.append(villager['name'])
        return jsonify(results_array)
    else:
        return jsonify(format_villager(call_cargo(params, request.args)))

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
        return jsonify({ 'uuid': new_uuid, 'email': email, 'project': project})
    except:
        abort(500, description=error_response("Failed to create new client UUID.", "UUID generation, or UUID insertion into keys table, failed."))

# Villagers
@app.route('/villagers', methods=['GET'])
def get_villager_all():
    authorize(DB_KEYS, request)

    limit = '500'
    tables = 'villager'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name'
    else:
        fields = 'url,name,alt_name,id,image_url,species,personality,gender,birthday_month,birthday_day,sign,quote,phrase,prev_phrase,prev_phrase2,clothes,islander,debut,dnm,ac,e_plus,ww,cf,nl,wa,nh,film,hhd,pc'

    return get_villager_list(limit, tables, fields)

# All New Horizons fish
@app.route('/nh/fish', methods=['GET'])
def get_nh_fish_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_fish'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'url,name,number,image_url,catchphrase,catchphrase2,catchphrase3,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length'

    return get_critter_list(limit, tables, fields)

# Specific New Horizons fish
@app.route('/nh/fish/<string:fish>', methods=['GET'])
def get_nh_fish(fish):
    authorize(DB_KEYS, request)
    fish = fish.replace('_', ' ')
    tables = 'nh_fish'
    fields = 'url,name,number,image_url,catchphrase,catchphrase2,catchphrase3,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,location,shadow_size,rarity,total_catch,sell_nook,sell_cj,tank_width,tank_length'
    where = 'name="' + fish + '"'
    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where }

    if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
        return jsonify(months_to_array(call_cargo(params, request.args)))
    else:
        cargo_results = call_cargo(params, request.args)
        if cargo_results == []:
            abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
        else:
            return jsonify(months_to_array(cargo_results)[0])

# All New Horizons bugs
@app.route('/nh/bugs', methods=['GET'])
def get_nh_bug_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_bug'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'url,name,number,image_url,catchphrase,catchphrase2,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length'

    return get_critter_list(limit, tables, fields)

# Specific New Horizons bug
@app.route('/nh/bugs/<string:bug>', methods=['GET'])
def get_nh_bug(bug):
    authorize(DB_KEYS, request)

    bug = bug.replace('_', ' ')
    tables = 'nh_bug'
    fields = 'url,name,number,image_url,catchphrase,catchphrase2,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length'
    where = 'name="' + bug + '"'
    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where }

    if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
        return jsonify(months_to_array(call_cargo(params, request.args)))
    else:
        cargo_results = call_cargo(params, request.args)
        if cargo_results == []:
            abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
        else:
            return jsonify(months_to_array(cargo_results)[0])

# All New Horizons sea creatures
@app.route('/nh/sea', methods=['GET'])
def get_nh_sea_all():
    authorize(DB_KEYS, request)

    limit = '100'
    tables = 'nh_sea_creature'
    if request.args.get('excludedetails') and (request.args.get('excludedetails') == 'true'):
        fields = 'name,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12'
    else:
        fields = 'url,name,number,image_url,catchphrase,catchphrase2,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length'

    return get_critter_list(limit, tables, fields)

# Specific New Horizons sea creature
@app.route('/nh/sea/<string:sea>', methods=['GET'])
def get_nh_sea(sea):
    authorize(DB_KEYS, request)

    sea = sea.replace('_', ' ')
    tables = 'nh_sea_creature'
    fields = 'url,name,number,image_url,catchphrase,catchphrase2,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,shadow_size,shadow_movement,rarity,total_catch,sell_nook,tank_width,tank_length'
    where = 'name="' + sea + '"'
    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where }

    if(request.headers.get('Accept-Version') and request.headers.get('Accept-Version')[:3] == '1.0'):
        return jsonify(months_to_array(call_cargo(params, request.args)))
    else:
        cargo_results = call_cargo(params, request.args)
        if cargo_results == []:
            abort(404, description=error_response("No data was found for the given query.", "MediaWiki Cargo request succeeded by nothing was returned for the parameters: {}".format(params)))
        else:
            return jsonify(months_to_array(cargo_results)[0])

if __name__ == '__main__':
    app.run(host = '0.0.0.0')

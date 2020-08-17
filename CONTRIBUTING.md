# Contributing
Anyone is welcome and encourages to contribute to the Nookipedia API!

## Opening a PR
When contributing, please create a fork of this repository and work off of the `dev` branch. Changes will be merged into `dev` and tested before being merged into `master`.

When making changes to endpoints, please be sure to also update the OpenAPI documenation accordingly (see Documentation section below).

In your pull request (PR), please be sure to provide a detailed description describing the changes you have made.

## File overview
* `app.py`: The Python Flask application that serves the API and routing
* `config.ini`: Configs for `app.py`. Must be filled out before running
* `dashboard-config.cfg`: Configurations for [Flask-MonitoringDashboard](https://github.com/flask-dashboard/Flask-MonitoringDashboard)
* `static/index.html`: The project's homepage (https://api.nookipedia.com/)
* `static/doc.html`: Renders [redoc](https://github.com/Redocly/redoc) OpenAPI documentation page (https://api.nookipedia.com/doc)
* `static/doc.json` & `static/doc.yaml`: YAML and JSON files of the OpenAPI documentation
* `static/css/style.css`: CSS for `static/index.html`
* `static/css/brands.min.css` & `static/css/fontawesome.min.css`: [Font Awesome](https://fontawesome.com/) CSS for rendering icons on homepage
* `static/js/redoc.standalone.js`: JavaScript for [redoc](https://github.com/Redocly/redoc)
* `static/webfonts/*`: [Font Awesome](https://fontawesome.com/) fonts for rendering icons on homepage

## Style guide
Python files:
* Indents are four spaces

HTML + CSS files:
* Indents are two spaces

## Endpoint examples

Below is an example of the endpoint to retrieve details about a specified New Horizons bug, with an explanation following.

```
@app.route('/nh/bugs/<string:bug>', methods=['GET'])
def get_nh_bug(bug):
    authorize(DB_KEYS, request)

    bug = bug.replace('_', ' ')
    tables = 'nh_bug'
    fields = 'url,name,number,image_url,catchphrase,catchphrase2,n_availability,n_m1,n_m2,n_m3,n_m4,n_m5,n_m6,n_m7,n_m8,n_m9,n_m10,n_m11,n_m12,s_availability,s_m1,s_m2,s_m3,s_m4,s_m5,s_m6,s_m7,s_m8,s_m9,s_m10,s_m11,s_m12,time,location,rarity,total_catch,sell_nook,sell_flick,tank_width,tank_length'
    where = 'name="' + bug + '"'
    params = { 'action': 'cargoquery', 'format': 'json', 'tables': tables, 'fields': fields, 'where': where }

    return jsonify(months_to_array(call_cargo(params, request.args)))
```

* First, we declare the route (`/<game>/<subject>/<parameter>`) and method type (GET request), as well as the function name.
* `authorize(DB_KEYS, request)` performs the check to ensure the user is authenticated via their API key.
* For the bug name parameter, we need to replace any underscores with a space (`bug = bug.replace('_', ' ')`); the MediaWiki API does not treat them interchangibly.
* We specify the Cargo table(s) we will be querying (see [Special:CargoTables](https://nookipedia.com/wiki/Special:CargoTables) for full list of tables, and [Project Database](https://nookipedia.com/wiki/Nookipedia:Project_Database) for status of tables and if they are ready to be queried in production).
* Declare the fields (columns) that we want to query. Most, if not all, columns will be queried for most endpoints. Sometimes some columns contain data meant to be used exlcusively on-wiki (e.g. formatted wikitext), which we can disclude.
* Since we want a specific resource, we also add a `where` with the bug's name.
* Set up the `params` to pass into the Cargo call.
* Make the Cargo call. `call_cargo` is the function that makes the call to Nookipedia's Cargo API, formats the response as-needed, and returns it. In this case, we also put the response through `months_to_array`, which merges the individual month fields into more easily-parsed arrays.


Below is an example of the endpoint to retrieve all New Horizons bugs, with an explanation following.

```
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
```

* First, we declare the route (`/<game>/<subject>`) and method type (GET request), as well as the function name.
* `authorize(DB_KEYS, request)` performs the check to ensure the user is authenticated via their API key.
* We set a limit of 100. The default limit for a Cargo query is 50, and the maximum is 500.
* We specify the Cargo table(s) we will be querying (see [Special:CargoTables](https://nookipedia.com/wiki/Special:CargoTables) for full list of tables, and [Project Database](https://nookipedia.com/wiki/Nookipedia:Project_Database) for status of tables and if they are ready to be queried in production).
* This endpoint lets users specify if the want all details about all bugs (default), or just a list of bug names (via `excludedetails` query parameter). If details are excluded, we only query for name and month availability (in case the user wants a particular month). Otherwise, we request all columns.
* `get_critter_list` is a function made to handle New Horizons all-critter calls to Cargo. This takes care of checking for any `month` filters and formatting the return.

## Documentation
When changing or creating endpoints, please be sure to also update the OpenAPI documentation, located inside the `static` directory.

Copy the YAML into [Swagger editor](https://editor.swagger.io/) and modify accordingly. When finished, save the YAML as well as the JSON copy (File -> Convert and save as JSON).

## Versioning
Version numbers are in #.#.# (Major.Minor.Patch) format.
* A patch update is a small change that won't impact most users. Bug fixes, adding an insignificant queried field, etc.
* A minor update is an impactful change, such as the addition of a new endpoint, new filters, etc.
* A major update would include many large-scale changes and breaking changes. We don't anticipate incrementing from 1.#.# anytime soon.

## Breaking changes
We try our best to avoid breaking changes, but it is bound to happen at some point. Users are asked to send in a `Accept-Version` header with the version they are using; when implementing a breaking change, add a check for version to direct logic accordingly and prevent breaking the API for existing users.

## Licensing
The Nookipedia API codebase is licensed under the MIT license. See [license file](https://github.com/Nookipedia/nookipedia-api/blob/master/LICENSE) for full text.

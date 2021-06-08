from flask import Flask
from flask_cors import CORS

from nookipedia.config import config
from nookipedia.dashboard import configure_dashboard
from nookipedia import api, db, errors
from nookipedia.cache import cache


app = Flask(__name__, static_folder="../static")
CORS(app)
app.config["JSON_SORT_KEYS"] = False  # Prevent from automatically sorting JSON alphabetically
app.config["SECRET_KEY"] = config.get("APP", "SECRET_KEY")


@app.teardown_appcontext
def teardown(exception):
    db.close_connection(exception)


cache.init_app(app)

cache.set("session", None)

configure_dashboard(app)

app.register_error_handler(400, errors.error_bad_request)
app.register_error_handler(401, errors.error_resource_not_authorized)
app.register_error_handler(404, errors.error_resource_not_found)
app.register_error_handler(405, errors.error_invalid_method)
app.register_error_handler(500, errors.error_server)

app.register_blueprint(api.admin.router)
app.register_blueprint(api.art.router)
app.register_blueprint(api.bugs.router)
app.register_blueprint(api.clothing.router)
app.register_blueprint(api.events.router)
app.register_blueprint(api.fish.router)
app.register_blueprint(api.furniture.router)
app.register_blueprint(api.interior.router)
app.register_blueprint(api.items.router)
app.register_blueprint(api.photos.router)
app.register_blueprint(api.recipes.router)
app.register_blueprint(api.sea.router)
app.register_blueprint(api.static.router)
app.register_blueprint(api.tools.router)
app.register_blueprint(api.villagers.router)
app.register_blueprint(api.fossils.router)

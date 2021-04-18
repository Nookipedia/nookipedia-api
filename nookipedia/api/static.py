from flask import current_app, Blueprint


router = Blueprint("home", __name__)


@router.route('/')
def static_index():
    return current_app.send_static_file('index.html')


@router.route('/doc')
def static_doc():
    return current_app.send_static_file('doc.html')

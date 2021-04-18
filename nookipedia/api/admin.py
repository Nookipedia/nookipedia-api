import uuid
from flask import abort, jsonify, request, Blueprint

from nookipedia import db
from nookipedia.config import DB_ADMIN_KEYS, DB_KEYS
from nookipedia.middlewares import authorize
from nookipedia.errors import error_response


router = Blueprint('admin', __name__)


@router.route('/admin/gen_key', methods=['POST'])
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
        db.insert_db('INSERT INTO ' + DB_KEYS + ' VALUES("' + new_uuid + '","' + email + '","' + project + '")')
        return jsonify({'uuid': new_uuid, 'email': email, 'project': project})
    except:
        abort(500, description=error_response("Failed to create new client UUID.", "UUID generation, or UUID insertion into keys table, failed."))

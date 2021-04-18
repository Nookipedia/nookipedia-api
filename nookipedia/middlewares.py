from flask import abort
from nookipedia.errors import error_response
from nookipedia.db import query_db


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

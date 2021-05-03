import json


# @errors_blueprint.errorhandler(400)
def error_bad_request(e):
    response = e.get_response()
    if "title" in e.description:
        response.data = json.dumps(
            {
                "title": e.description["title"],
                "details": e.description["details"],
            }
        )
    else:
        response.data = json.dumps(
            {
                "title": "Invalid input",
                "details": "Please ensure provided parameters have valid vales.",
            }
        )
    response.content_type = "application/json"
    return response, 400


# @errors_blueprint.errorhandler(401)
def error_resource_not_authorized(e):
    response = e.get_response()
    if "title" in e.description:
        response.data = json.dumps(
            {
                "title": e.description["title"],
                "details": e.description["details"],
            }
        )
    else:
        response.data = json.dumps(
            {
                "title": "Unauthorized.",
                "details": "Failed to authorize client for requested action.",
            }
        )
    response.content_type = "application/json"
    return response, 401


# @errors_blueprint.errorhandler(404)
def error_resource_not_found(e):
    response = e.get_response()
    if "title" in e.description:
        response.data = json.dumps(
            {
                "title": e.description["title"],
                "details": e.description["details"],
            }
        )
    else:
        response.data = json.dumps(
            {
                "title": "Resource not found.",
                "details": "Please ensure requested resource exists.",
            }
        )
    response.content_type = "application/json"
    return response, 404


# @errors_blueprint.errorhandler(405)
def error_invalid_method(e):
    response = e.get_response()
    if "title" in e.description:
        response.data = json.dumps(
            {
                "title": e.description["title"],
                "details": e.description["details"],
            }
        )
    else:
        response.data = json.dumps(
            {
                "title": "Method not allowed.",
                "details": "The method you requested (GET, POST, etc.) is not valid for this endpoint.",
            }
        )
    response.content_type = "application/json"
    return response, 405


# @errors_blueprint.errorhandler(500)
def error_server(e):
    response = e.get_response()
    if "title" in e.description:
        response.data = json.dumps(
            {
                "title": e.description["title"],
                "details": e.description["details"],
            }
        )
    else:
        response.data = json.dumps(
            {
                "title": "API experienced a fatal error.",
                "details": "Details unknown.",
            }
        )
    response.content_type = "application/json"
    return response, 500


# Format and return json error response body:
def error_response(title, details):
    return {"title": title, "details": details}

from datetime import datetime

from flask import Flask, request, render_template, make_response
from flask.ext.limiter import Limiter
from blocklister import __version__
from blocklister.models import Blocklist
from blocklister.helpers import get_changelog
from blocklister.cache import cached
from blocklister.exc import DownloadError, EmptyListError


app = Flask(__name__)
limiter = Limiter(app, headers_enabled=True)
store = "/tmp"


def get_class(classname):
    """
    Run through all subclassess of `Blocklist` and return the
    appropiate class, if None was found raise a `ValueError`

    :param classname: str Classname to look up
    :rtype `class`
    :returns Class for which we were looking for
    """
    for subcls in Blocklist.__subclasses__():
        if subcls.__name__ == classname.title():
            return subcls
    raise ValueError("No class found for {}".format(classname))


@app.errorhandler(IOError)
def handle_filenotavailable(exc):
    msg = "File on disk is not available"
    response = make_response(msg, 500)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.errorhandler(ValueError)
def handle_unknown_blacklist(exc):
    routes = [
        "/{}".format(x.__name__.lower()) for x in Blocklist.__subclasses__()
    ]
    msg = render_template(
        'unknown_blacklist.jinja2',
        routes=routes,
        exc=exc,
    )
    response = make_response(msg, 404)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.errorhandler(EmptyListError)
def handle_empty_ip_list(exc):
    response = make_response(str(exc), 404)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.errorhandler(DownloadError)
def handle_downloaderror(exc):
    msg = "Error downloading requested list"
    response = make_response(msg, 500)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.errorhandler(429)
def handle_ratelimit(exc):
    msg = "Too Many Request from your ip"
    response = make_response(msg, 429)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.route("/", methods=['GET'])
def index():
    lists = Blocklist.__subclasses__()
    result = render_template(
        "welcome.jinja2", lists=lists, version=__version__
    )
    response = make_response(result, 200)
    response.headers['Content-Type'] = "text/plain"
    return response


@app.route("/changelog", methods=['GET'])
def changelog():
    result = get_changelog()
    response = make_response(result, 200)
    response.headers['Content-Type'] = "text/plain"
    return response


@limiter.limit("10 per day")
@app.route("/<string:blacklist>", methods=['GET'])
@cached()
def get_list(blacklist):
    # First find the right class
    _class = get_class(blacklist.title())
    bl = _class(store)

    # Get File if it does not exist yet
    if not bl.file_exists:
        bl.get()

    # Get User variables if any
    listname = request.args.get(
        "listname",
        "{}_list".format(_class.__name__.lower())
    )
    comment = request.args.get(
        "comment",
        "{}".format(_class.__name__.title())
    )

    # Check if file is older than 3 days, if so update
    now = datetime.now()
    if (now - bl.last_saved).days > 3:
        bl.get()

    ips = bl.get_ips()

    if not ips:
        raise EmptyListError(
            "No ips found for {}".format(blacklist.title())
        )

    result = render_template(
        "mikrotik_addresslist.jinja2",
        ips=ips,
        listname=listname,
        comment=comment
    )
    response = make_response(result, 200)
    response.headers['Content-Type'] = "text/plain"
    return response


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    app.debug = True
    app.run()

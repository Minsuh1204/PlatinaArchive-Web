import os
from datetime import timedelta
from typing import Dict, Set

import redis
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    current_user,
    get_jwt,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)
from sqlalchemy import desc, select

from api.routes import api_bp_v1
from models import Decoder, DecodeResult, db

BASEDIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(BASEDIR)
load_dotenv()

VERSION = (1, 2, 3)
ALLOWED_REDIRECT_PATHS: Set[str] = {"/my", "/archive", "/recent"}
ENDPOINTS_MAP: Dict[str, str] = {
    "/": "homepage",
    "/login": "login",
    "/logout": "logout",
    "/recent": "recent",
}
ACCESS_EXPIRES = timedelta(days=30)
TITLE = "PLATiNA-ARCHiVE"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("LAB_DB_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_POOL_RECYCLE"] = 3600
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET")
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = True
app.config["JWT_COOKIE_CSRF_PROTECT"] = True
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = ACCESS_EXPIRES
app.register_blueprint(api_bp_v1)

db.init_app(app)
jwt = JWTManager(app, add_context_processor=True)  # We can use current_user in jinja!!

jwt_redis_blocklist = redis.StrictRedis(
    host=os.getenv("REDIS_HOST"),
    port=11809,
    decode_responses=True,
    username=os.getenv("REDIS_USERNAME"),
    password=os.getenv("REDIS_PASS"),
)


def is_url_safe(url: str) -> bool:
    return url in ALLOWED_REDIRECT_PATHS


@app.context_processor
def inject_global_variables():
    return dict(version=VERSION, title=TITLE)


@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(jti)
    return token_in_redis is not None


@jwt.user_identity_loader
def user_identity_lookup(decoder: Decoder):
    return decoder.name


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return Decoder.query.get(identity)


@jwt.invalid_token_loader
def handle_invalid_token(reason):
    flash(f"로그인 쿠키가 유효하지 않습니다. 다시 로그인해주세요. ({reason})", "danger")
    response = make_response(redirect(url_for("login")))
    unset_jwt_cookies(response)
    return response


@jwt.expired_token_loader
@jwt.revoked_token_loader
def handle_expired_token(_jwt_header, jwt_data):
    flash(f"로그인 쿠키가 만료되었습니다. 다시 로그인해주세요.", "info")
    endpoint = ENDPOINTS_MAP.get(request.path, "homepage")
    response = make_response(redirect(url_for("login", next=endpoint)))
    unset_jwt_cookies(response)
    return response


@jwt.unauthorized_loader
def handle_not_logged_in(reason):
    flash("로그인이 필요합니다.", "warning")
    endpoint = ENDPOINTS_MAP.get(request.path, "homepage")
    return redirect(url_for("login", next=endpoint))


@app.route("/")
@jwt_required(optional=True)
def homepage():
    return render_template("home.html")


@app.route("/login", methods=["POST", "GET"])
@jwt_required(optional=True)
def login():
    if request.method == "GET":
        return render_template("login.html")
    next_endpoint = request.args.get("next", "homepage")
    name = request.form.get("name")
    password = request.form.get("password")

    decoder: Decoder = db.session.get(Decoder, name)
    if decoder and decoder.check_pass(password):
        access_token = create_access_token(identity=decoder)
        response = make_response(
            redirect(
                url_for(
                    next_endpoint
                    if next_endpoint in ENDPOINTS_MAP.values()
                    else "homepage"
                )
            )
        )
        set_access_cookies(response, access_token)
        flash(f"환영합니다, {decoder.name}!", "success")
        return response
    flash("로그인 실패", "danger")
    return render_template("login.html")


@app.route("/logout")
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_redis_blocklist.set(jti, "", ex=ACCESS_EXPIRES)
    response = make_response(redirect("/"))
    unset_jwt_cookies(response)
    flash("성공적으로 로그아웃 되었습니다.", "info")
    return response


@app.route("/recent")
@jwt_required()
def recent():
    recent_50_results: list[DecodeResult] = (
        db.session.execute(
            select(DecodeResult)
            .filter_by(decoder=current_user.name)
            .order_by(desc(DecodeResult.decoded_at))
            .limit(50)
        )
        .scalars()
        .all()
    )
    return render_template("recent.html", recent_results=recent_50_results)


if __name__ == "__main__":
    app.run(debug=True, port=8000)

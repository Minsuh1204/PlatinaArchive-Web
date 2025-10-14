import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, flash, make_response, redirect, render_template, request
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
)
import redis

from api.routes import api_bp_v1
from models import Decoder, db

BASEDIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(BASEDIR)
load_dotenv()

VERSION = (1, 1, 6)
ALLOWED_REDIRECT_PATHS: set[str] = {"/my", "/archive"}
ACCESS_EXPIRES = timedelta(days=30)

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
jwt = JWTManager(app)

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
@jwt_required(optional=True)
def inject_global_variables():
    decoder_name = get_jwt_identity()
    if decoder_name is None:
        decoder = None
        is_logged_in = False
    else:
        decoder = Decoder.query.get(decoder_name)
        is_logged_in = True
    return dict(version=VERSION, decoder=decoder, is_logged_in=is_logged_in)


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


@app.route("/")
def homepage():
    return render_template("home.html")


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    next_url = request.args.get("next", "/")
    name = request.form.get("name")
    password = request.form.get("password")

    decoder: Decoder = Decoder.query.get(name)
    if decoder and decoder.check_pass(password):
        access_token = create_access_token(identity=decoder)
        response = make_response(
            redirect(next_url) if is_url_safe(next_url) else redirect("/")
        )
        set_access_cookies(response, access_token)
        return response
    flash("로그인 실패", "danger")
    return render_template("login.html")


@app.route("/logout")
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_redis_blocklist.set(jti, "", ex=ACCESS_EXPIRES)


if __name__ == "__main__":
    app.run(debug=True, port=8000)

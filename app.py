import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import redis
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
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

from api.routes import _load_info_json, api_bp_v1, api_bp_v2
from models import Decoder, DecodeResult, DecoderProgress, PlatinaSong, db, emblem_map

BASEDIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(BASEDIR)
load_dotenv()

lines = ["4L", "4L+", "6L", "6L+"]

VERSION = (1, 5, 2)
ENDPOINTS_MAP: dict[str, str] = {
    "/": "homepage",
    "/login": "login",
    "/logout": "logout",
    "/recent": "recent",
    "/archive": "decoder_archive",
}
ACCESS_EXPIRES = timedelta(days=30)
TITLE = "PLATiNA-ARCHiVE"

app = Flask(__name__, static_url_path="/static")
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
app.register_blueprint(api_bp_v2)

db.init_app(app)
jwt = JWTManager(app, add_context_processor=True)  # We can use current_user in jinja!!

jwt_redis_blocklist = redis.StrictRedis(
    host=os.getenv("REDIS_HOST"),
    port=11809,
    decode_responses=True,
    username=os.getenv("REDIS_USERNAME"),
    password=os.getenv("REDIS_PASS"),
)


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
    return db.session.get(Decoder, identity)


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


@app.route("/favicon.ico")
@jwt_required(optional=True)
def favicon():
    # Image from: https://platinalab.net/characters
    return send_file("./static/favicon.ico")


@app.route("/client")
@jwt_required(optional=True)
def client():
    return render_template("client.html")


@app.route("/login", methods=["POST", "GET"])
@jwt_required(optional=True)
def login():
    if request.method == "GET":
        return render_template(
            "login.html", next_endpoint=request.args.get("next", "homepage")
        )
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
    return render_template(
        "recent.html",
        recent_results=recent_50_results,
        _format_judge_str=_format_judge_str,
    )


@app.route("/archive")
@jwt_required()
def decoder_archive():
    decoder: Decoder = current_user
    status_4 = decoder.get_status(4, False)
    status_4_plus = decoder.get_status(4, True)
    status_6 = decoder.get_status(6, False)
    status_6_plus = decoder.get_status(6, True)
    overall_total_patterns = (
        status_4["total_patterns"]
        + status_4_plus["total_patterns"]
        + status_6["total_patterns"]
        + status_6_plus["total_patterns"]
    )
    overall_cleared_patterns = (
        status_4["cleared_patterns"]
        + status_4_plus["cleared_patterns"]
        + status_6["cleared_patterns"]
        + status_6_plus["cleared_patterns"]
    )
    overall_full_combo = (
        status_4["full_combo_patterns"]
        + status_4_plus["full_combo_patterns"]
        + status_6["full_combo_patterns"]
        + status_6_plus["full_combo_patterns"]
    )
    overall_perfect_decode = (
        status_4["perfect_decode_patterns"]
        + status_4_plus["perfect_decode_patterns"]
        + status_6["perfect_decode_patterns"]
        + status_6_plus["perfect_decode_patterns"]
    )
    overall_max_patch = (
        status_4["max_patch_patterns"]
        + status_4_plus["max_patch_patterns"]
        + status_6["max_patch_patterns"]
        + status_6_plus["max_patch_patterns"]
    )
    return render_template(
        "archive_all.html",
        status_4=status_4,
        status_4_plus=status_4_plus,
        status_6=status_6,
        status_6_plus=status_6_plus,
        overall_total_patterns=overall_total_patterns,
        overall_cleared_patterns=overall_cleared_patterns,
        overall_full_combo=overall_full_combo,
        overall_perfect_decode=overall_perfect_decode,
        overall_max_patch=overall_max_patch,
    )


@app.route("/archive/<line>")
@jwt_required()
def get_archive_by_line(line: str):
    if not line in lines:
        abort(404)
    decoder: Decoder = current_user
    line_int = int(line.split("L")[0])
    top_50_patch_results = decoder.get_top_50_patch_results(
        line_int, line.endswith("+")
    )
    progresses: list[DecoderProgress] = DecoderProgress.get_all_progresses(
        current_user.name, line
    )
    dates = [p.recorded_at.astimezone(timezone.utc).isoformat() for p in progresses]
    data = [round(p.total, 2) for p in progresses]
    total_patch, emblem = decoder.calculate_emblem(line_int, line.endswith("+"))
    return render_template(
        "archive_line.html",
        dates=dates,
        data=data,
        progresses=progresses,
        results=top_50_patch_results,
        emblem=emblem,
        line=line,
        total_patch=total_patch,
        _format_judge_str=_format_judge_str,
    )


@app.route("/song_autocomplete")
def song_autocomplete():
    query = request.args.get("query", "").lower().strip()
    if not query or len(query) < 2:
        return jsonify([])
    update_song_titles_cache()
    song_titles: list[str] = _get_song_titles()
    starts_with = []
    contains = []

    for title in song_titles:
        title_lower = title.lower()
        if title_lower.startswith(query):
            starts_with.append(title)
        elif query in title_lower:
            contains.append(title)
    suggestions = (starts_with + contains)[:10]

    return jsonify(suggestions)


@app.route("/search")
@jwt_required(optional=True)
def search():
    query = request.args.get("query", "").strip()
    update_song_titles_cache()
    song_titles: list[str] = _get_song_titles()
    if query in song_titles:
        song_id = db.session.execute(
            select(PlatinaSong.song_id).filter(PlatinaSong.title == query)
        ).scalar()
        return redirect(url_for("get_song", song_id=song_id))
    abort(404)


@app.route("/songs/<int:song_id>")
@jwt_required(optional=True)
def get_song(song_id: int):
    song_data = PlatinaSong.from_song_id(song_id)
    if not song_data:
        abort(404)
    all_results: list[DecodeResult] = song_data.decode_results
    if current_user:
        results: list[DecodeResult] = [
            r for r in all_results if r.decoder == current_user.name
        ]
    else:
        results = []
    results_4l_easy = "N/A"
    results_4l_hard = "N/A"
    results_4l_over = "N/A"
    results_4l_plus_easy = "N/A"
    results_4l_plus_hard = "N/A"
    results_4l_plus_over = "N/A"
    results_6l_easy = "N/A"
    results_6l_hard = "N/A"
    results_6l_over = "N/A"
    results_6l_plus_easy = "N/A"
    results_6l_plus_hard = "N/A"
    results_6l_plus_over = "N/A"
    non_plus_results = [r for r in results if r.difficulty != "PLUS"]
    for r in non_plus_results:
        if r.line == 4:
            if r.difficulty == "EASY":
                results_4l_easy = r
            elif r.difficulty == "HARD":
                results_4l_hard = r
            else:
                results_4l_over = r
        else:
            if r.difficulty == "EASY":
                results_6l_easy = r
            elif r.difficulty == "HARD":
                results_6l_hard = r
            else:
                results_6l_over = r
    results_4l_plus = [r for r in results if r.line == 4 and r.difficulty == "PLUS"]
    for r in results_4l_plus:
        if r.level < 10:
            results_4l_plus_easy = r
        elif r.level < 20:
            results_4l_plus_hard = r
        else:
            results_4l_plus_over = r
    results_6l_plus = [r for r in results if r.line == 6 and r.difficulty == "PLUS"]
    for r in results_6l_plus:
        if r.level < 10:
            results_6l_plus_easy = r
        elif r.level < 20:
            results_6l_plus_hard = r
        else:
            results_6l_plus_over = r
    return render_template(
        "song_db.html",
        song=song_data,
        results_4l_easy=results_4l_easy,
        results_4l_hard=results_4l_hard,
        results_4l_over=results_4l_over,
        results_4l_plus_easy=results_4l_plus_easy,
        results_4l_plus_hard=results_4l_plus_hard,
        results_4l_plus_over=results_4l_plus_over,
        results_6l_easy=results_6l_easy,
        results_6l_hard=results_6l_hard,
        results_6l_over=results_6l_over,
        results_6l_plus_easy=results_6l_plus_easy,
        results_6l_plus_hard=results_6l_plus_hard,
        results_6l_plus_over=results_6l_plus_over,
        _format_judge_str=_format_judge_str,
    )


def update_song_titles_cache() -> bool:
    """Update the _get_song_titles function's cache. If updates, return True."""
    today = datetime.today()
    songs_last_updated = datetime.fromisoformat(
        _load_info_json()["songs_db_last_updated"]
    )
    if today > songs_last_updated:
        _get_song_titles.cache_clear()
        return True
    return False


@lru_cache(maxsize=1)
def _get_song_titles() -> list[str]:
    return [s.title for s in PlatinaSong.get_all()]


def _format_judge_str(result: DecodeResult, old: bool = False) -> str:
    if old:
        if result.old_judge == 0:
            return ""
        base = f"{result.old_judge}%"
        additional = ""
        if result.old_is_max_patch:
            additional = (
                " <span style='color: var(--platina-max-patch)'>MAX P.A.T.C.H.</span>"
            )
        elif result.old_judge == 100:
            additional = " <img src='https://r2.platina-archive.app/perfect_decode.png' class='inline-icon'>"
        elif result.old_is_full_combo:
            additional = " <img src='https://r2.platina-archive.app/full_combo.png' class='inline-icon'>"
        return base + additional
    base = f"{result.judge}%"
    additional = ""
    if result.is_max_patch:
        additional = (
            " <span style='color: var(--platina-max-patch)'>MAX P.A.T.C.H.</span>"
        )
    elif result.judge == 100:
        additional = " <img src='https://r2.platina-archive.app/perfect_decode.png' class='inline-icon'>"
    elif result.is_full_combo:
        additional = " <img src='https://r2.platina-archive.app/full_combo.png' class='inline-icon'>"
    return base + additional


if __name__ == "__main__":
    app.run(debug=True, port=8000)

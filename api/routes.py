import base64
import binascii
import json
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, make_response, request
from ruamel.yaml import YAML

from models import (Decoder, DecodeResult, PlatinaPattern, PlatinaSong,
                    PlatinaSongGo, db)

BASEDIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
api_bp_v1 = Blueprint("api", __name__, url_prefix="/api/v1")
api_bp_v2 = Blueprint("api_v2", __name__, url_prefix="/api/v2")

yaml = YAML(pure=True)
os.chdir(BASEDIR)


def _load_info_json() -> dict:
    with open("./info.json") as f:
        info_dict = json.load(f)
    return info_dict


def check_cache_headers(db_last_modified: datetime):
    db_last_modified_str = db_last_modified.isoformat()
    if_modified_since = request.headers.get("If-Modified-Since")

    if if_modified_since:
        try:
            client_date = datetime.fromisoformat(if_modified_since).astimezone(
                timezone.utc
            )
            if client_date >= db_last_modified.astimezone(timezone.utc):
                response = make_response("", 304)
                response.headers["Last-Modified"] = db_last_modified_str
                return response
        except ValueError as e:
            pass

    return None


@api_bp_v1.route("/client_version")
def client_version():
    client_latest = _load_info_json()["client_latest_version"]
    return jsonify(
        major=client_latest["major"],
        minor=client_latest["minor"],
        patch=client_latest["patch"],
    )

@api_bp_v1.route("/config")
def config():
    # cache check
    config_db_last_updated = datetime.fromisoformat(
        _load_info_json()["config_last_updated"]
    )
    cache_response = check_cache_headers(config_db_last_updated)
    if cache_response:
        return cache_response
    with open("./config.yaml") as f:
        config_dict = yaml.load(f)
    if "version" in config_dict and hasattr(config_dict["version"], "strftime"):
        config_dict["version"] = config_dict["version"].strftime("%Y-%m-%d")
    return jsonify(config_dict)

@api_bp_v1.route("/platina_songs")
def api_platina_songs():
    # cache check
    songs_db_last_updated = datetime.fromisoformat(
        _load_info_json()["songs_db_last_updated"]
    )
    cache_response = check_cache_headers(songs_db_last_updated)
    if cache_response:
        return cache_response

    songs = PlatinaSong.get_all()
    songs_json = []
    for song in songs:
        songs_json.append(
            {
                "songID": song.song_id,
                "title": song.title,
                "artist": song.artist,
                "BPM": song.bpm,
                "DLC": song.dlc,
                "pHash": song.phash,
                "plusPHash": song.plus_phash,
            }
        )
    response = jsonify(songs_json)
    last_modified_str = songs_db_last_updated.isoformat()
    response.headers["Last-Modified"] = last_modified_str
    return response


@api_bp_v2.route("/platina_songs")
def api_platina_songs_v2():
    # cache check
    songs_db_last_updated = datetime.fromisoformat(
        _load_info_json()["songs_db_last_updated"]
    )
    cache_response = check_cache_headers(songs_db_last_updated)
    if cache_response:
        return cache_response

    songs = PlatinaSongGo.get_all()
    songs_json = []
    for song in songs:
        songs_json.append(
            {
                "songID": song.song_id,
                "title": song.title,
                "artist": song.artist,
                "BPM": song.bpm,
                "DLC": song.dlc,
                "pHash": song.phash,
                "plusPHash": song.plus_phash,
            }
        )
    response = jsonify(songs_json)
    last_modified_str = songs_db_last_updated.isoformat()
    response.headers["Last-Modified"] = last_modified_str
    return response


@api_bp_v1.route("/platina_patterns")
def api_platina_patterns():
    # cache check
    patterns_db_last_updated = datetime.fromisoformat(
        _load_info_json()["patterns_db_last_updated"]
    )
    cache_response = check_cache_headers(patterns_db_last_updated)
    if cache_response:
        return cache_response
    patterns = PlatinaPattern.get_all()
    patterns_json = []
    for pattern in patterns:
        patterns_json.append(
            {
                "songID": pattern.song_id,
                "line": pattern.line,
                "difficulty": pattern.difficulty,
                "level": pattern.level,
                "designer": pattern.designer,
            }
        )
    response = jsonify(patterns_json)
    last_modified_str = patterns_db_last_updated.isoformat()
    response.headers["Last-Modified"] = last_modified_str
    return response


@api_bp_v1.route("/register", methods=["POST"])
def register_decoder():
    params = request.get_json()
    name = params.get("name", "")
    password = params.get("password", "")
    result = Decoder.register(name, password)
    if not result:
        return jsonify({"msg": "Name already taken"}), 400

    decoder, key = result
    success_json = {"name": decoder.name, "key": key}
    return jsonify(success_json)


def _update_db_archive(params, api_key: str):
    song_id = params.get("song_id")
    line = params.get("line")
    difficulty = params.get("difficulty")
    level = params.get("level")
    judge = params.get("judge")
    score = params.get("score")
    patch = params.get("patch")
    is_full_combo = params.get("is_full_combo")
    is_max_patch = params.get("is_max_patch")

    decoder = Decoder.load_by_key(api_key)
    if not decoder:
        msg = {"msg": "Invalid API key"}
        return jsonify(msg), 401

    song_obj: PlatinaSong = PlatinaSong.query.get((song_id))
    if not song_obj:
        return jsonify({"msg": "Unknown song ID"}), 404
    if not line in (4, 6):
        return jsonify({"msg": "Invalid line value"}), 400
    if not difficulty in ("EASY", "HARD", "OVER", "PLUS"):
        return jsonify({"msg": "Invalid difficulty value"}), 400
    available_levels = song_obj.get_available_levels(line, difficulty)
    if not level in available_levels:
        return jsonify({"msg": "Invalid level value"}), 400
    if (
        not (isinstance(judge, float) or isinstance(judge, int))
        or judge < 0
        or judge > 100
    ):
        return jsonify({"msg": "Invalid judge value"}), 400
    if not isinstance(score, int) or score < 0:
        return jsonify({"msg": "Invalid score value"}), 400
    if not (isinstance(patch, float) or isinstance(patch, int)) or patch < 0:
        return jsonify({"msg": "Invalid P.A.T.C.H. value"}), 400
    if not isinstance(is_full_combo, bool):
        return jsonify({"msg": "Invalid is_full_combo value"}), 400
    if not isinstance(is_max_patch, bool):
        return jsonify({"msg": "Invalid is_max_patch value"}), 400

    update_success = DecodeResult.update_or_make(
        decoder.name,
        song_id,
        line,
        difficulty,
        level,
        judge,
        score,
        patch,
        is_full_combo,
        is_max_patch,
    )
    if update_success:
        return jsonify({"msg": "success"}), 200
    else:
        return jsonify({"msg": "failed"}), 500


@api_bp_v1.route("/update_archive", methods=["POST"])
def update_archive():
    params = request.get_json()
    api_key = request.headers.get("X-API-Key", "::")
    return _update_db_archive(params, api_key)


@api_bp_v2.route("/update_archive", methods=["POST"])
def update_archive_v2():
    params = request.get_json()
    b64_api_key = request.headers.get("X-API-Key")
    if not b64_api_key:
        return jsonify({"msg": "No API key"}), 401
    try:
        api_key = base64.b64decode(b64_api_key.encode("utf-8")).decode("utf-8")
    except (UnicodeDecodeError, binascii.Error):
        return jsonify({"msg": "API key is not encoded correctly"}), 400
    return _update_db_archive(params, api_key)


def _get_archive(api_key: str):
    decoder: Decoder | None = Decoder.load_by_key(api_key)
    if not decoder:
        msg = {"msg": "Invalid API key"}
        return jsonify(msg), 401
    archive: list[DecodeResult] = DecodeResult.get_archive(decoder.name)
    json_archive = []
    for arc in archive:
        json_archive.append(
            {
                "decoder": arc.decoder,
                "song_id": arc.song_id,
                "line": arc.line,
                "difficulty": arc.difficulty,
                "level": arc.level,
                "judge": arc.judge,
                "score": arc.score,
                "patch": arc.patch,
                "decoded_at": arc.decoded_at.isoformat(),
                "is_full_combo": arc.is_full_combo,
                "is_max_patch": arc.is_max_patch,
            }
        )
    return jsonify(json_archive)


@api_bp_v1.route("/get_archive", methods=["POST"])
def get_archive():
    api_key = request.headers.get("X-API-Key", "::")
    return _get_archive(api_key)


@api_bp_v2.route("/get_archive", methods=["POST"])
def get_archive_v2():
    b64_api_key = request.headers.get("X-API-Key")
    if not b64_api_key:
        return jsonify({"msg": "No API key"}), 401
    try:
        api_key = base64.b64decode(b64_api_key.encode("utf-8")).decode("utf-8")
        return _get_archive(api_key)
    except (UnicodeDecodeError, binascii.Error):
        return jsonify({"msg": "API key is not encoded correctly"}), 400


@api_bp_v1.route("/login", methods=["POST"])
def login():
    request_json = request.get_json()
    name = request_json.get("name", "")
    password = request_json.get("password", "")
    decoder: Decoder = db.session.get(Decoder, name)
    if not decoder or not decoder.check_pass(password):
        return jsonify(msg="로그인 실패"), 401
    api_key = decoder.make_new_secret()
    return jsonify(msg="success", key=api_key)

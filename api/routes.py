import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, make_response, request

from models import Decoder, DecodeResult, PlatinaPattern, PlatinaSong

BASEDIR = os.path.abspath(os.path.dirname(__file__))
api_bp_v1 = Blueprint("api", __name__, url_prefix="/api/v1")

CLIENT_LATEST = (0, 2, 5)
SONGS_DB_LAST_UPDATED = datetime(2025, 10, 3).astimezone(timezone.utc)
PATTERNS_DB_LAST_UPDATED = datetime(2025, 10, 3).astimezone(timezone.utc)


def check_cache_headers(db_last_modified: datetime):
    db_last_modified_str = db_last_modified.isoformat()
    if_modified_since = request.headers.get("If-Modified-Since")

    if if_modified_since:
        try:
            client_date = datetime.fromisoformat(if_modified_since)
            if client_date >= db_last_modified:
                response = make_response("", 304)
                response.headers["Last-Modified"] = db_last_modified_str
                return response
        except ValueError:
            pass

    return None


@api_bp_v1.route("/client_version")
def client_version():
    return jsonify(
        major=CLIENT_LATEST[0], minor=CLIENT_LATEST[1], patch=CLIENT_LATEST[2]
    )


@api_bp_v1.route("/platina_songs")
def api_platina_songs():
    # cache check
    cache_response = check_cache_headers(SONGS_DB_LAST_UPDATED)
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
    last_modified_str = SONGS_DB_LAST_UPDATED.isoformat()
    response.headers["Last-Modified"] = last_modified_str
    return response


@api_bp_v1.route("/platina_patterns")
def api_platina_patterns():
    # cache check
    cache_response = check_cache_headers(PATTERNS_DB_LAST_UPDATED)
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
    last_modified_str = PATTERNS_DB_LAST_UPDATED.isoformat()
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


@api_bp_v1.route("/update_archive", methods=["POST"])
def update_archive():
    params = request.get_json()
    api_key = request.headers.get("X-API-Key", "::")
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


@api_bp_v1.route("/get_archive", methods=["POST"])
def get_archive():
    api_key = request.headers.get("X-API-Key", "::")
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

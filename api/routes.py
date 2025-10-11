from datetime import datetime, timezone
import os

from flask import Blueprint, jsonify, request

from models import db, Decoder, DecodeResult, PlatinaPattern, PlatinaSong


BASEDIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES = os.path.join(BASEDIR, "templates")
api_bp = Blueprint("api", __name__, url_prefix="/api", template_folder=TEMPLATES)


@api_bp.route("/platina_songs", methods=["POST"])
def api_platina_songs():
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
    return jsonify(songs_json)


@api_bp.route("/platina_patterns", methods=["POST"])
def api_platina_patterns():
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
    return jsonify(patterns_json)


@api_bp.route("/register", methods=["POST"])
def register_decoder():
    params = request.get_json()
    name = params.get("name", "")
    password = params.get("password", "")
    result = Decoder.register(name, password)
    if not result:
        return "Name already taken", 400

    decoder, key = result
    success_json = {"name": decoder.name, "key": key}
    return jsonify(success_json)


@api_bp.route("/update_archive", methods=["POST"])
def update_archive():
    params = request.get_json()
    api_key = params.get("api_key")
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

    existing_archive: DecodeResult = DecodeResult.query.get(
        (decoder.name, song_id, line, difficulty, level)
    )
    utc_now = datetime.now(timezone.utc)
    if existing_archive:
        existing_archive.judge = judge
        existing_archive.score = score
        existing_archive.patch = patch
        existing_archive.is_full_combo = is_full_combo
        existing_archive.is_max_patch = is_max_patch
        existing_archive.decoded_at = utc_now
        db.session.commit()

    else:
        new_archive = DecodeResult(
            decoder=decoder.name,
            song_id=song_id,
            line=line,
            difficulty=difficulty,
            level=level,
            judge=judge,
            score=score,
            patch=patch,
            decoded_at=utc_now,
            is_full_combo=is_full_combo,
            is_max_patch=is_max_patch,
        )
        db.session.add(new_archive)
        db.session.commit()

    return jsonify({"msg": "success"}), 200


@api_bp.route("/get_archive", methods=["POST"])
def get_archive():
    params = request.get_json()
    api_key = params.get("api_key")
    decoder = Decoder.load_by_key(api_key)
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

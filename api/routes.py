import os

from flask import Blueprint, jsonify, request

from models import Decoder, PlatinaPattern, PlatinaSong


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
    name = params["name"]
    password = params["password"]
    result = Decoder.register(name, password)
    if not result:
        return "Name already taken", 400

    decoder, key = result
    success_json = {"name": decoder.name, "key": key}
    return jsonify(success_json)

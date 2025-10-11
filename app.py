import os

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_jwt_extended import JWTManager

from api.routes import api_bp
from models import db, Decoder

BASEDIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(BASEDIR)
load_dotenv()

app = Flask(__name__)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("LAB_DB_URI")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_POOL_RECYCLE"] = 3600
app.config["JWT_SECRET_KEY"] = os.getenv("FLASK_SECRET")
app.register_blueprint(api_bp)

db.init_app(app)
jwt = JWTManager(app)


@jwt.user_identity_loader
def user_identity_lookup(decoder: Decoder):
    return decoder.name


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return Decoder.query.filter_by(name=identity).one_or_none()


@app.route("/")
def homepage():
    return render_template("home.html")


if __name__ == "__main__":
    app.run(debug=True, port=8000)

import os

from dotenv import load_dotenv
from flask import Flask, render_template

from api.routes import api_bp
from models import db

BASEDIR = os.path.abspath(os.path.dirname(__file__))
os.chdir(BASEDIR)
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("LAB_DB_URI")
app.register_blueprint(api_bp)
db.init_app(app)


@app.route("/")
def homepage():
    return render_template("home.html")


if __name__ == "__main__":
    app.run(debug=True, port=8000)

from markdown import markdown
import os

from dotenv import load_dotenv
from flask import Flask, render_template

from api.routes import api_bp

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET")
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("LAB_DB_URI")
app.register_blueprint(api_bp)

BASEDIR = os.path.abspath(os.path.dirname(__file__))


@app.route("/")
def homepage():
    readme_loc = os.path.join(BASEDIR, os.path.pardir, "README.md")
    with open(readme_loc, "r") as f:
        readme_md = f.read()
    return render_template("home.html", readme=markdown(readme_md))


if __name__ == "__main__":
    app.run(debug=True, port=8000)

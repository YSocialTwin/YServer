from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import json
import shutil
import os

# create the experiments folder
if not os.path.exists('./experiments'):
    os.mkdir('./experiments')

# read the experiment configuration
config = json.load(open("config_files/exp_config.json"))

# copy the clean database to the experiments folder
shutil.copyfile("data_schema/database_clean_server.db", f"experiments/{config['name']}.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "4YrzfpQ4kGXjuP6w"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///../experiments/{config['name']}.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

from y_server import routes_api

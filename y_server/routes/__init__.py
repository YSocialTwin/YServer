from .time_management import *
from .user_managment import *
from .content_management import *
from .interaction_management import *
from .experiment_management import *

config = json.load(open("config_files/exp_config.json"))

import importlib

for module in config["modules"]:
    try:
        importlib.import_module(f".{module}_management", "y_server.routes")
    except:
        raise Exception(f"Module {module} does not exists")

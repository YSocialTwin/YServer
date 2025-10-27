"""
Routes initialization module.

This module imports and registers all route handlers for the YSocial server,
including time management, user management, content management, interaction management,
and experiment management routes. It also dynamically loads additional modules
specified in the experiment configuration file.
"""

import os
from .time_management import *
from .user_managment import *
from .content_management import *
from .interaction_management import *
from .experiment_management import *

try:
    config = json.load(open(f"config_files{os.sep}exp_config.json"))

    import importlib

    for module in config["modules"]:
        try:
            importlib.import_module(f".{module}_management", "y_server.routes")
        except:
            raise Exception(f"Module {module} does not exists")
except:
    # Y Web subprocess
    from .content_management import *
    from .image_management import *
    from .news_management import *
    from .voting_management import *

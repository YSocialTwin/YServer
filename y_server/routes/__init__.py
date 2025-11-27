import json
import os
import traceback

from y_server.error_logging import log_error

from .content_management import *
from .experiment_management import *
from .interaction_management import *
from .time_management import *
from .user_managment import *

try:
    config = json.load(open(f"config_files{os.sep}exp_config.json"))

    import importlib

    for module in config["modules"]:
        try:
            importlib.import_module(f".{module}_management", "y_server.routes")
        except Exception as module_error:
            log_error(f"Failed to import module '{module}_management': {str(module_error)}\nTraceback: {traceback.format_exc()}")
            raise Exception(f"Module {module} does not exists")
except Exception as config_error:
    # Y Web subprocess - log the initialization fallback
    log_error(f"Routes initialization fallback to Y Web subprocess mode: {str(config_error)}\nTraceback: {traceback.format_exc()}")
    from .content_management import *
    from .image_management import *
    from .news_management import *
    from .voting_management import *

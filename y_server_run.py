import json
import os
import sys
import traceback
from datetime import datetime


def log_error(message):
    """
    Log an error message to stderr with timestamp formatting.
    
    Each write starts with "### date and time ###\n" and ends with "\n####".
    Uses flush=True to ensure immediate output for debugging.
    
    Note: This is defined locally to avoid import issues during module loading.
    
    :param message: the error message to log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"### {timestamp} ###\n{message}\n####", file=sys.stderr, flush=True)


def start_server(config):
    """
    Start the app
    """
    try:
        print(config)
        config_path = config.get("__config_file__")
        if config_path:
            os.environ["YSERVER_CONFIG"] = config_path
        from y_server import app

        # import nltk
        # nltk.download("vader_lexicon")
        debug = False
        app.config["perspective_api"] = config.get("perspective_api")
        app.config["toxicity_annotation"] = config.get("toxicity_annotation", False)
        app.config["sentiment_annotation"] = config.get("sentiment_annotation", False)
        app.config["emotion_annotation"] = config.get("emotion_annotation", False)
        app.config["memory_enabled"] = bool(
            (config.get("memory") or {}).get("enabled", config.get("memory_enabled", False))
        )
        
        log_error(f"SERVER STARTING: Flask app.run() about to be called\nProcess ID: {os.getpid()}\nHost: {config['host']}\nPort: {config['port']}\nDebug: {debug}")
        
        app.run(debug=debug, port=int(config["port"]), host=config["host"])
        
        # If we reach here, app.run() returned - this should only happen on shutdown
        log_error(f"SERVER STOPPED: Flask app.run() returned normally\nProcess ID: {os.getpid()}\nThis indicates the server stopped without an exception.\nPossible causes: SIGTERM/SIGINT received, werkzeug reloader exiting, or server shutdown requested.")
        
    except SystemExit as e:
        log_error(f"SERVER EXITING: SystemExit raised in start_server\nProcess ID: {os.getpid()}\nExit code: {e.code}\nTraceback: {traceback.format_exc()}")
        raise
    except Exception as e:
        log_error(f"Error starting server: {str(e)}\nConfig: {config}\nTraceback: {traceback.format_exc()}")
        raise


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()

    parser.add_argument(
        "-c",
        "--config_file",
        default=f"config_files{os.sep}exp_config.json",
        help="JSON file describing the simulation configuration",
    )
    args = parser.parse_args()

    config_file = args.config_file
    try:
        config = json.load(open(config_file, "r"))
        config["__config_file__"] = config_file
    except Exception as e:
        log_error(f"Error loading config file {config_file}: {str(e)}\nTraceback: {traceback.format_exc()}")
        raise

    start_server(config)

import json
import os
import sys
import traceback
from datetime import datetime


def _log_error_stderr(message):
    """
    Log an error message to stderr with timestamp formatting.
    
    Each write starts with "### date and time ###\n" and ends with "\n####".
    Uses flush=True to ensure immediate output for debugging.
    
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
        from y_server import app

        # import nltk
        # nltk.download("vader_lexicon")
        debug = True
        app.config["perspective_api"] = config["perspective_api"]
        app.config["sentiment_annotation"] = config["sentiment_annotation"]
        app.config["emotion_annotation"] = config["emotion_annotation"]
        app.run(debug=debug, port=int(config["port"]), host=config["host"])
    except Exception as e:
        _log_error_stderr(f"Error starting server: {str(e)}\nConfig: {config}\nTraceback: {traceback.format_exc()}")
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
    except Exception as e:
        _log_error_stderr(f"Error loading config file {config_file}: {str(e)}\nTraceback: {traceback.format_exc()}")
        raise

    start_server(config)

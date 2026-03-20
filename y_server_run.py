import json
import os


def _resolve_server_log_file(config_file: str) -> str:
    env_path = str(os.environ.get("YSERVER_LOG_FILE", "") or "").strip()
    if env_path:
        return env_path
    config_dir = os.path.dirname(os.path.abspath(config_file or "")) or os.getcwd()
    return os.path.join(config_dir, "_server.log")


def start_server(config):
    """
    Start the app
    """
    from y_server import app

    debug = False
    app.run(debug=debug, port=int(config["port"]), host=config["host"])


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
    config = json.load(open(config_file, "r"))

    log_file = _resolve_server_log_file(config_file)
    os.environ["YSERVER_LOG_FILE"] = log_file
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8"):
            pass
    except Exception:
        pass

    from y_server import app

    app.config["log_file"] = log_file

    start_server(config)

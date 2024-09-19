from y_server import app
import json

if __name__ == "__main__":
    config = json.load(open("config_files/exp_config.json"))
    debug = True if config["debug"] == "True" else False

    app.run(debug=debug, port=int(config["port"]), host=config["host"])

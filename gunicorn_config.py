"""
Gunicorn configuration file for YServer.

This file provides default configuration for running YServer with Gunicorn.
You can override these settings by passing command-line arguments to gunicorn.

Usage:
    gunicorn -c gunicorn_config.py wsgi:app
"""
import json
import os
import multiprocessing

# Read configuration from exp_config.json
config_file = os.path.join('config_files', 'exp_config.json')
if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        exp_config = json.load(f)
else:
    # Default configuration
    exp_config = {
        "host": "0.0.0.0",
        "port": 5010
    }

# Server socket
bind = f"{exp_config.get('host', '0.0.0.0')}:{exp_config.get('port', 5010)}"

# Worker processes
# Recommended: (2 x $num_cores) + 1, with a maximum of 8 to avoid resource contention
workers = min(multiprocessing.cpu_count() * 2 + 1, 8)

# Worker class
# Use 'sync' for CPU-bound tasks, 'gevent' or 'eventlet' for I/O-bound tasks
worker_class = 'sync'

# Maximum requests a worker will process before restarting
# Helps prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Timeout for requests (in seconds)
timeout = 120

# Access log
accesslog = '-'  # Log to stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Error log
errorlog = '-'  # Log to stderr
loglevel = 'info'

# Process naming
proc_name = 'yserver'

# Preload application for better performance
preload_app = True

# Server mechanics
daemon = False
pidfile = None

# SSL (if needed, uncomment and configure)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

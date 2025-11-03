"""
Gunicorn configuration file for YServer.

This file provides default configuration for running YServer with Gunicorn.
You can override these settings by passing command-line arguments to gunicorn.

Usage:
    # Default config (config_files/exp_config.json):
    gunicorn -c gunicorn_config.py wsgi:app
    
    # With custom config file via environment variable:
    YSERVER_CONFIG=/path/to/config.json gunicorn -c gunicorn_config.py wsgi:app
    
    # From Python with Popen (each subprocess has its own environment):
    env = os.environ.copy()
    env['YSERVER_CONFIG'] = '/path/to/config.json'
    subprocess.Popen(['gunicorn', '-c', 'gunicorn_config.py', 'wsgi:app'], env=env)

Note on running multiple instances:
    When starting multiple Gunicorn processes, each should have its own YSERVER_CONFIG
    environment variable set in the subprocess environment. Each process will have its
    own Python interpreter and won't interfere with other instances.
"""
import json
import os
import multiprocessing

# Read configuration from exp_config.json or custom path via environment variable
config_file = os.environ.get('YSERVER_CONFIG', os.path.join('config_files', 'exp_config.json'))
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

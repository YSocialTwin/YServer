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

Note on macOS:
    On macOS (Darwin), preload_app is automatically disabled to prevent fork safety
    issues with CoreFoundation, Objective-C runtime, and other macOS frameworks.
    These frameworks cannot be safely used after fork() without exec(), which causes
    SIGSEGV crashes. While this reduces startup performance slightly, it ensures
    stability on macOS. The OBJC_DISABLE_INITIALIZE_FORK_SAFETY environment variable
    is also set as an additional safeguard.
"""
import json
import os
import multiprocessing
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


# Read configuration from exp_config.json or custom path via environment variable
config_file = os.environ.get('YSERVER_CONFIG', os.path.join('config_files', 'exp_config.json'))
try:
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            exp_config = json.load(f)
    else:
        log_error(f"Gunicorn config file not found: {config_file}, using defaults")
        # Default configuration
        exp_config = {
            "host": "0.0.0.0",
            "port": 5010
        }
except Exception as e:
    log_error(f"Error loading Gunicorn config: {str(e)}\nTraceback: {traceback.format_exc()}")
    exp_config = {
        "host": "0.0.0.0",
        "port": 5010
    }

# Server socket
bind = f"{exp_config.get('host', '0.0.0.0')}:{exp_config.get('port', 5010)}"

# Worker processes
# Recommended: (2 x $num_cores) + 1, with a maximum of 8 to avoid resource contention
workers = 1 #min(multiprocessing.cpu_count() * 2 + 1, 8)
threads = 1

# Worker class
# Use 'sync' for CPU-bound tasks, 'gevent' or 'eventlet' for I/O-bound tasks
# Note: Using 'sync' worker with PostgreSQL and NullPool for reliability
worker_class = 'sync'

# Maximum requests a worker will process before restarting
# Helps prevent memory leaks and ensures clean worker restarts
max_requests = 1000
max_requests_jitter = 50

# Timeout for requests (in seconds)
# Increased for potentially long-running database operations
timeout = 120

# Access log
accesslog = '-'  # Log to stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Error log
errorlog = '-'  # Log to stderr
loglevel = 'info'

accesslog = "access.log"
errorlog = "error.log"

# Capture application output
capture_output = True

# Process naming
proc_name = 'yserver'

# Preload application for better performance
# Disable on macOS due to CoreFoundation/Objective-C fork safety issues
preload_app = sys.platform != 'darwin'

# Environment variables for workers
# Fix for macOS fork() safety issue with Objective-C runtime
# Note: Even with these environment variables, macOS may still have issues with
# preload_app=True due to CoreFoundation and other frameworks, so we disable it on macOS
# See: https://github.com/ansible/ansible/issues/32499
raw_env = [
    'OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES',
]

# Server mechanics
daemon = False
pidfile = None

# SSL (if needed, uncomment and configure)
# keyfile = '/path/to/keyfile'
# certfile = '/path/to/certfile'

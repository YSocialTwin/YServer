"""
Error logging utility for YServer.

Provides advanced error logging using print redirected to sys.stderr with flush=True.
Each log entry starts with "### date and time ###\n" and ends with "\n####".
"""
import sys
import traceback
from datetime import datetime


def log_error(message):
    """
    Log an error message to stderr with timestamp formatting.
    
    Each write starts with "### date and time ###\n" and ends with "\n####".
    Uses flush=True to ensure immediate output for debugging.
    
    :param message: the error message to log
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"### {timestamp} ###\n{message}\n####", file=sys.stderr, flush=True)


def log_exception(context, exception, include_traceback=True):
    """
    Log an exception with context information.
    
    :param context: description of what was happening when the exception occurred
    :param exception: the exception object
    :param include_traceback: whether to include the full traceback
    """
    message = f"{context}: {str(exception)}"
    if include_traceback:
        message += f"\nTraceback: {traceback.format_exc()}"
    log_error(message)

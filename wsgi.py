"""
WSGI entry point for YServer.

This module provides the WSGI application object for production deployment
with servers like Gunicorn.

Usage:
    gunicorn wsgi:app
    gunicorn -w 4 -b 0.0.0.0:5010 wsgi:app
"""
from y_server import app

# The app object is automatically created when y_server is imported
# and can be used directly by WSGI servers like Gunicorn
if __name__ == "__main__":
    # This allows testing the WSGI module directly
    app.run()

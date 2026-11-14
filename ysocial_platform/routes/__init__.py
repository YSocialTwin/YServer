"""Pages and actions of the microblogging platform, registered on the core blueprints."""

from . import (  # noqa: F401  (side effect: registers the routes)
    clients_standard,
    clients_standard_pages,
    interactions_microblogging,
    social_microblogging,
)

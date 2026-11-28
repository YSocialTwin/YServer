"""Pages that follow a client of the Standard runtime of microblogging: its recommenders, LLM, settings and the
opinion dynamics of the experiment. The shared logic stays in the core (``y_web.sdk.web``).
"""

from flask import redirect, url_for
from flask_login import login_required
from y_web.sdk import routes
from y_web.sdk.web import (
    apply_opinion_distributions_to_population,
    invalidate_opinion_evolution_cache_for_experiment,
    opinion_configuration_internal,
    persist_non_hpc_opinion_dynamics,
    resolve_opinion_submission_context,
    sync_initial_standard_opinions_to_experiment_db,
    update_client_llm_internal,
    update_client_simulation_internal,
    update_recsys_internal,
)

clientsr = routes.blueprint("clients")


@clientsr.route("/admin/update_standard_recsys/<int:uid>", methods=["POST"])
@login_required
def update_standard_recsys(uid):
    """Update recommenders for a standard microblogging client."""
    return update_recsys_internal(uid, "standard")


@clientsr.route("/admin/update_standard_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_standard_client_llm(uid):
    """Update LLM for a standard microblogging client."""
    return update_client_llm_internal(uid, "standard")


@clientsr.route("/admin/update_standard_client_settings/<int:uid>", methods=["POST"])
@login_required
def update_standard_client_settings(uid):
    return update_client_simulation_internal(uid, "standard")


@clientsr.route("/admin/opinion_configuration_standard/<int:idexp>")
@login_required
def opinion_configuration_standard(idexp):
    """Display opinion configuration for a standard microblogging experiment."""
    return opinion_configuration_internal(idexp, "standard")


@clientsr.route("/admin/set_standard_opinion_distributions", methods=["POST"])
@login_required
def set_standard_opinion_distributions():
    """Persist opinion distributions for a standard microblogging experiment."""
    context, error_response = resolve_opinion_submission_context("standard")
    if error_response is not None:
        return error_response
    save_error = apply_opinion_distributions_to_population(context)
    if save_error is not None:
        return save_error
    persist_non_hpc_opinion_dynamics(context)
    sync_initial_standard_opinions_to_experiment_db(context)
    invalidate_opinion_evolution_cache_for_experiment(int(context["idexp"]))
    return redirect(url_for("experiments.experiment_details", uid=context["idexp"]))

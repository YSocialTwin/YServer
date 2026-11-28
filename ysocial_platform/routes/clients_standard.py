"""Pages and creation of a client on the Standard runtime of microblogging (YClient).

They used to live in the core (``clients_standard`` and ``create_standard_client``); the core finds them by the
name of the view (``clientsr.clients_standard``) through the provider's ``clients_page``.
"""

import json
import os
import random

import networkx as nx
import numpy as np
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from y_web.sdk import gettext as _
from y_web.sdk import routes
from y_web.sdk.agents import summarize_agent_custom_features_bulk
from y_web.sdk.models import (
    ActivityProfile,
    Agent,
    Agent_Ext,
    Agent_Population,
    Agent_Profile,
    Client,
    Exp_Topic,
    Exps,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
    db,
)
from y_web.sdk.runtime import get_writable_path, prompt_packs
from y_web.sdk.web import (
    allocate_topics_by_percentage,
)
from y_web.sdk.web import (
    apply_population_attributes_to_client_config as _apply_population_attributes_to_client_config,
)
from y_web.sdk.web import (
    apply_structured_features_to_agent_payload as _apply_structured_features_to_agent_payload,
)
from y_web.sdk.web import (
    build_client_creation_context as _build_client_creation_context,
)
from y_web.sdk.web import check_privileges
from y_web.sdk.web import (
    experiment_configuration_update_required as _experiment_configuration_update_required,
)
from y_web.sdk.web import experiment_details_page, get_db_type, log_telemetry_event
from y_web.sdk.web import (
    memory_enabled_for_client_creation as _memory_enabled_for_client_creation,
)
from y_web.sdk.web import mode_view
from y_web.sdk.web import (
    opinion_dynamics_enabled_for_client_creation as _opinion_dynamics_enabled_for_client_creation,
)
from y_web.sdk.web import provider_of as _provider_of
from y_web.sdk.web import redirect_to_clients_page as _redirect_to_clients_page

clientsr = routes.blueprint("clients")


@clientsr.route("/admin/clients_standard/<idexp>")
@login_required
def clients_standard(idexp):
    """Render the standard microblogging client creation page."""
    check_privileges(current_user.username)

    context = _build_client_creation_context(idexp, "Standard")
    exp = context["experiment"]
    if exp is None:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    misplaced = _redirect_to_clients_page(exp, "clientsr.clients_standard")
    if misplaced is not None:
        return misplaced
    if _experiment_configuration_update_required(exp):
        flash(
            _(
                "Update Experiment Configuration before creating clients for this experiment."
            ),
            "warning",
        )
        return redirect(url_for("experiments.experiment_details", uid=idexp))

    return render_template("admin/clients.html", **context)


def _create_standard_client_internal():
    """Create a standard microblogging client without forum-specific branching."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")

    exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()
    if not exp:
        flash(_("Experiment not found."), "error")
        return redirect(url_for("experiments.settings"))
    if getattr(exp, "simulator_type", "Standard") == "HPC":
        flash(
            _("Use the dedicated HPC client creation route for this experiment."),
            "error",
        )
        return redirect(url_for("clientsr.clients_hpc", idexp=exp_id))
    provider = _provider_of(exp)
    mode = provider.client_mode("Standard")
    if mode != "standard" or provider.standard_runtime is None:
        flash(
            _("Use the dedicated forum client creation route for this experiment."),
            "error",
        )
        if mode_view("clients_{mode}", mode) is not None:
            return redirect(url_for(f"clientsr.clients_{mode}", idexp=exp_id))
        return redirect(url_for("clientsr.clients_standard", idexp=exp_id))

    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
    probability_of_follow_back = request.form.get("probability_of_follow_back")
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post", "0")
    share = request.form.get("share", "0")
    image = request.form.get("image", "0")
    comment = request.form.get("comment", "0")
    read = request.form.get("read", "0")
    news = request.form.get("news", "0")
    search = request.form.get("search", "0")
    vote = request.form.get("vote", "0")
    share_link = request.form.get("share_link", "0")
    share_image = request.form.get("share_image", "0")
    initial_agents = request.form.get("initial_agents")
    clock_mode = (request.form.get("clock_mode") or "simulated").strip().lower()
    clock_timezone = (request.form.get("clock_timezone") or "Europe/Rome").strip()
    clock_feed_refresh = (
        (request.form.get("clock_feed_refresh") or "hourly").strip().lower()
    )
    max_thread_context_chars = request.form.get("max_thread_context_chars", "3200")
    max_replies_per_round = request.form.get("max_replies_per_round", "2")
    reply_cooldown_rounds = request.form.get("reply_cooldown_rounds", "2")
    memory_enabled = request.form.get("memory_enabled") in {"on", "true", "1", "yes"}
    memory_pair_limit = request.form.get("memory_pair_limit", "5")
    memory_prompt_max_chars = request.form.get("memory_prompt_max_chars", "1600")
    memory_social_decay_lambda = request.form.get("memory_social_decay_lambda", "0.05")
    memory_social_corruption_rate = request.form.get(
        "memory_social_corruption_rate", "0.02"
    )
    memory_social_resummarize_every_events = request.form.get(
        "memory_social_resummarize_every_events", "4"
    )
    memory_thread_decay_lambda = request.form.get("memory_thread_decay_lambda", "0.03")
    memory_thread_corruption_rate = request.form.get(
        "memory_thread_corruption_rate", "0.01"
    )
    memory_thread_resummarize_every_events = request.form.get(
        "memory_thread_resummarize_every_events", "4"
    )
    memory_evidence_tail_max = request.form.get("memory_evidence_tail_max", "8")
    memory_digest_update_cadence_rounds = request.form.get(
        "memory_digest_update_cadence_rounds", "3"
    )
    memory_digest_events_limit = request.form.get("memory_digest_events_limit", "80")
    memory_cold_start_window = request.form.get("memory_cold_start_window", "5")
    memory_semantic_enabled = request.form.get("memory_semantic_enabled") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_search_k = request.form.get("memory_search_k", "8")
    memory_search_max_chars = request.form.get("memory_search_max_chars", "900")
    memory_search_time_window_rounds = request.form.get(
        "memory_search_time_window_rounds", "40"
    )
    memory_tier_a_max_chars = request.form.get("memory_tier_a_max_chars", "350")
    memory_tier_b_max_chars = request.form.get("memory_tier_b_max_chars", "900")
    memory_tier_c_max_chars = request.form.get("memory_tier_c_max_chars", "900")
    memory_total_max_chars = request.form.get("memory_total_max_chars", "2200")
    memory_tier_c_uncertainty_threshold = request.form.get(
        "memory_tier_c_uncertainty_threshold", "0.45"
    )
    memory_reflection_cadence_rounds = request.form.get(
        "memory_reflection_cadence_rounds", "3"
    )
    memory_reflection_min_events = request.form.get(
        "memory_reflection_min_events", "12"
    )
    memory_reflection_trigger_importance_sum = request.form.get(
        "memory_reflection_trigger_importance_sum", "3.5"
    )
    memory_reflection_max_items_per_run = request.form.get(
        "memory_reflection_max_items_per_run", "60"
    )
    memory_embedding_model = request.form.get(
        "memory_embedding_model", "snowflake-arctic-embed:110m"
    )
    memory_embedding_async = request.form.get("memory_embedding_async") in {
        "on",
        "true",
        "1",
        "yes",
    }
    memory_importance_mode = request.form.get(
        "memory_importance_mode", "heuristic_then_batch_llm"
    )

    if not memory_semantic_enabled:
        memory_embedding_async = False

    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )
    experiment_memory_enabled = _memory_enabled_for_client_creation(exp)
    if not experiment_memory_enabled:
        memory_enabled = False
        memory_semantic_enabled = False
        memory_embedding_async = False

    posted_opinion_flag = (
        str(request.form.get("experiment_opinion_dynamics_enabled", "")).strip().lower()
    )
    if posted_opinion_flag in {"true", "1", "yes", "on"}:
        opinions_enabled = True
    elif posted_opinion_flag in {"false", "0", "no", "off"}:
        opinions_enabled = False
    else:
        opinions_enabled = _opinion_dynamics_enabled_for_client_creation(exp)

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = "-1"
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Get agent archetype enabled status
    enable_archetypes = request.form.get("enable_archetypes") == "on"

    # Get agent archetype values (optional, with defaults)
    try:
        archetype_validator = (
            float(request.form.get("archetype_validator", "52")) / 100.0
        )
        archetype_broadcaster = (
            float(request.form.get("archetype_broadcaster", "20")) / 100.0
        )
        archetype_explorer = float(request.form.get("archetype_explorer", "28")) / 100.0
        trans_val_val = float(request.form.get("trans_val_val", "85.3")) / 100.0
        trans_val_broad = float(request.form.get("trans_val_broad", "8.1")) / 100.0
        trans_val_expl = float(request.form.get("trans_val_expl", "6.6")) / 100.0
        trans_broad_broad = float(request.form.get("trans_broad_broad", "72.9")) / 100.0
        trans_broad_val = float(request.form.get("trans_broad_val", "19.5")) / 100.0
        trans_broad_expl = float(request.form.get("trans_broad_expl", "7.5")) / 100.0
        trans_expl_expl = float(request.form.get("trans_expl_expl", "49.0")) / 100.0
        trans_expl_val = float(request.form.get("trans_expl_val", "36.4")) / 100.0
        trans_expl_broad = float(request.form.get("trans_expl_broad", "14.6")) / 100.0
    except (ValueError, TypeError) as e:
        flash(_("Invalid archetype values: %(error)s", error=str(e)), "error")
        return redirect(request.referrer)

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
        # days = -1 means infinite/run-until-stopped
        if days != -1 and days < 1:
            errors.append(
                "Days must be at least 1, or use -1 for infinite duration (run until stopped)"
            )
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        max_thread_context_chars = int(max_thread_context_chars)
        if max_thread_context_chars < 200 or max_thread_context_chars > 4800:
            errors.append("Thread Context Max Chars must be between 200 and 4800")
    except (ValueError, TypeError):
        errors.append("Thread Context Max Chars must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")
    try:
        max_replies_per_round = int(max_replies_per_round)
        if max_replies_per_round < 0:
            errors.append("Max Replies per Round must be at least 0")
    except (ValueError, TypeError):
        errors.append("Max Replies per Round must be a valid integer")
    try:
        reply_cooldown_rounds = int(reply_cooldown_rounds)
        if reply_cooldown_rounds < 0:
            errors.append("Reply Cooldown must be at least 0")
    except (ValueError, TypeError):
        errors.append("Reply Cooldown must be a valid integer")
    try:
        memory_pair_limit = int(memory_pair_limit)
        memory_prompt_max_chars = int(memory_prompt_max_chars)
        memory_search_k = int(memory_search_k)
        memory_search_max_chars = int(memory_search_max_chars)
        memory_search_time_window_rounds = int(memory_search_time_window_rounds)
        memory_tier_a_max_chars = int(memory_tier_a_max_chars)
        memory_tier_b_max_chars = int(memory_tier_b_max_chars)
        memory_tier_c_max_chars = int(memory_tier_c_max_chars)
        memory_total_max_chars = int(memory_total_max_chars)
        memory_reflection_cadence_rounds = int(memory_reflection_cadence_rounds)
        memory_reflection_min_events = int(memory_reflection_min_events)
        memory_reflection_max_items_per_run = int(memory_reflection_max_items_per_run)
        memory_social_resummarize_every_events = int(
            memory_social_resummarize_every_events
        )
        memory_thread_resummarize_every_events = int(
            memory_thread_resummarize_every_events
        )
        memory_evidence_tail_max = int(memory_evidence_tail_max)
        memory_digest_update_cadence_rounds = int(memory_digest_update_cadence_rounds)
        memory_digest_events_limit = int(memory_digest_events_limit)
        memory_cold_start_window = int(memory_cold_start_window)
    except (ValueError, TypeError):
        errors.append("Memory settings must use valid numeric values")
    try:
        memory_social_decay_lambda = float(memory_social_decay_lambda)
        memory_social_corruption_rate = float(memory_social_corruption_rate)
        memory_thread_decay_lambda = float(memory_thread_decay_lambda)
        memory_thread_corruption_rate = float(memory_thread_corruption_rate)
        memory_tier_c_uncertainty_threshold = float(memory_tier_c_uncertainty_threshold)
        memory_reflection_trigger_importance_sum = float(
            memory_reflection_trigger_importance_sum
        )
    except (ValueError, TypeError):
        errors.append("Memory weights must use valid numeric values")

    if clock_mode not in {"simulated", "real_time"}:
        errors.append("Experiment Clock Mode must be either simulated or real_time")
    if clock_feed_refresh not in {"hourly"}:
        errors.append("Feed refresh must be hourly")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None
    try:
        probability_of_follow_back = float(probability_of_follow_back)
    except (ValueError, TypeError):
        errors.append("Probability Follow/Unfollow Back must be a valid number")
        probability_of_follow_back = None
    action_probability_values = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    parsed_action_values = {}
    for field_name, raw_value in action_probability_values.items():
        try:
            parsed_action_values[field_name] = float(raw_value)
        except (ValueError, TypeError):
            errors.append(f"{field_name} must be a valid number")
            parsed_action_values[field_name] = None

    post = parsed_action_values["Post new content"]
    comment = parsed_action_values["Comment a Post"]
    read = parsed_action_values["Read a content"]
    search = parsed_action_values["Search a Hashtag"]
    share_link = parsed_action_values["Share Link"]
    share_image = parsed_action_values["Share Image"]
    share = 0.0
    image = 0.0
    news = 0.0
    vote = 0.0

    # Check probability ranges for true probabilities.
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
        "Probability Follow/Unfollow Back": probability_of_follow_back,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    # Standard action relevance fields use relative weights in [0, 10].
    action_scores = {
        "Post new content": post,
        "Comment a Post": comment,
        "Read a content": read,
        "Search a Hashtag": search,
        "Share Link": share_link,
        "Share Image": share_image,
    }
    for field_name, value in action_scores.items():
        if value is not None and not (0 <= value <= 10):
            errors.append(f"{field_name} must be between 0 and 10")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = db.session.scalars(select(Exp_Topic).filter_by(exp_id=exp_id)).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics_objs = (
        db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    )
    topics = [t.name for t in topics_objs]

    # Get topic interest percentages from form
    topic_percentages = {}
    for topic_obj in topics_objs:
        percentage_key = f"topic_interest_{topic_obj.id}"
        percentage_value = request.form.get(percentage_key, "100")
        try:
            topic_percentages[topic_obj.name] = float(percentage_value)
        except (ValueError, TypeError):
            topic_percentages[topic_obj.name] = 100.0  # Default to 100% if invalid

    # if name already exists, return to the previous page
    if db.session.scalars(select(Client).filter_by(name=name)).first():
        flash(_("Client name already exists."), "error")
        return redirect(request.referrer)

    exp = db.session.scalars(select(Exps).filter_by(idexp=exp_id)).first()

    # get population
    population = db.session.scalars(
        select(Population).filter_by(id=population_id)
    ).first()

    if population is None:
        flash(_("Population not found."), "error")
        return redirect(request.referrer)

    # a population is not tied to a platform: any of them can be deployed on any experiment

    initial_agents_int = None
    if initial_agents and initial_agents.strip():
        try:
            initial_agents_int = int(initial_agents)
            if initial_agents_int < 1:
                initial_agents_int = None
        except (ValueError, TypeError):
            initial_agents_int = None

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = db.session.scalars(
        select(Population_Experiment).filter_by(
            id_population=population_id, id_exp=exp_id
        )
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()
        from y_web.sdk.federation import population_added  # INV-18

        population_added(exp_id, population_id)

    # create the Client object
    prompt_language = prompt_packs.resolve(
        request.form.get("prompt_language"), exp.prompt_language
    )
    client = Client(
        name=name,
        prompt_language=prompt_language,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=int(llm_max_tokens),
        llm_temperature=float(llm_temperature),
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=int(llm_v_max_tokens),
        llm_v_temperature=float(llm_v_temperature),
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        status=0,
        archetype_validator=archetype_validator,
        archetype_broadcaster=archetype_broadcaster,
        archetype_explorer=archetype_explorer,
        trans_val_val=trans_val_val,
        trans_val_broad=trans_val_broad,
        trans_val_expl=trans_val_expl,
        trans_broad_broad=trans_broad_broad,
        trans_broad_val=trans_broad_val,
        trans_broad_expl=trans_broad_expl,
        trans_expl_expl=trans_expl_expl,
        trans_expl_val=trans_expl_val,
        trans_expl_broad=trans_expl_broad,
    )

    db.session.add(client)
    db.session.commit()

    # If experiment was completed, reset status to stopped since a new client was added
    if exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    if "database_server.db" in exp.db_name:
        uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix("experiments_")

    BASE_DIR = get_writable_path()
    experiment_folder = os.path.join(BASE_DIR, "y_web", "experiments", uid)
    experiment_config_path = os.path.join(experiment_folder, "config_server.json")
    resolved_clock = {
        "mode": clock_mode,
        "timezone": clock_timezone or "Europe/Rome",
        "feed_refresh": clock_feed_refresh,
    }

    try:
        experiment_config = {}
        if os.path.exists(experiment_config_path):
            with open(experiment_config_path, "r", encoding="utf-8") as config_file:
                experiment_config = json.load(config_file)
        experiment_config["clock"] = {
            "mode": resolved_clock["mode"],
            "timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
        }
        if (
            resolved_clock["mode"] == "real_time"
            and "anchor_date" not in experiment_config["clock"]
        ):
            experiment_config["clock"]["anchor_date"] = (
                __import__("datetime").date.today().isoformat()
            )
        with open(experiment_config_path, "w", encoding="utf-8") as config_file:
            json.dump(experiment_config, config_file, indent=4)
    except Exception:
        pass

    config = {
        "name": name,
        "servers": {
            "llm": llm,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "initial_agents": initial_agents_int,
            "clock_mode": resolved_clock["mode"],
            "clock_timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": 0.0,
                "news": 0.0,
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": 0.0,
                "search": float(search) if search is not None else 0,
                "cast": 0.0,
                "share_link": float(share_link) if share_link is not None else 0,
                "share_image": float(share_image) if share_image is not None else 0,
            },
            "emotion_annotation": emotion_annotation,
            "opinion_dynamics": {
                "enabled": bool(opinions_enabled),
            },
            "agent_archetypes": {
                "enabled": enable_archetypes,
                "distribution": {
                    "validator": archetype_validator,
                    "broadcaster": archetype_broadcaster,
                    "explorer": archetype_explorer,
                },
                "transitions": {
                    "validator": {
                        "validator": trans_val_val,
                        "broadcaster": trans_val_broad,
                        "explorer": trans_val_expl,
                    },
                    "broadcaster": {
                        "validator": trans_broad_val,
                        "broadcaster": trans_broad_broad,
                        "explorer": trans_broad_expl,
                    },
                    "explorer": {
                        "validator": trans_expl_val,
                        "broadcaster": trans_expl_broad,
                        "explorer": trans_expl_expl,
                    },
                },
            },
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "llm_v_agent": llm_v_agent or "qwen3-vl:8b",
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "max_thread_context_chars": int(max_thread_context_chars),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "probability_of_follow_back": float(probability_of_follow_back),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [] if llm_agents_enabled else [None],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
            "max_replies_per_round": int(max_replies_per_round),
            "reply_cooldown_rounds": int(reply_cooldown_rounds),
            "thread_browse_mode": "llm",
            "thread_browse_order": "tree_dfs",
            "thread_browse_max_nodes": 400,
            "thread_browse_chunk_size": 20,
            "thread_browse_top_k": 6,
            "thread_browse_max_llm_steps": 3,
            "thread_browse_snippet_chars": 220,
            "thread_browse_context_window": 30,
            "memory_enabled": bool(memory_enabled),
            "memory_pair_limit": int(memory_pair_limit),
            "memory_prompt_max_chars": int(memory_prompt_max_chars),
            "memory_social_decay_lambda": float(memory_social_decay_lambda),
            "memory_social_corruption_rate": float(memory_social_corruption_rate),
            "memory_social_resummarize_every_events": int(
                memory_social_resummarize_every_events
            ),
            "memory_thread_decay_lambda": float(memory_thread_decay_lambda),
            "memory_thread_corruption_rate": float(memory_thread_corruption_rate),
            "memory_thread_resummarize_every_events": int(
                memory_thread_resummarize_every_events
            ),
            "memory_evidence_tail_max": int(memory_evidence_tail_max),
            "memory_digest_update_cadence_rounds": int(
                memory_digest_update_cadence_rounds
            ),
            "memory_digest_events_limit": int(memory_digest_events_limit),
            "memory_cold_start_window": int(memory_cold_start_window),
            "memory_semantic_enabled": bool(memory_semantic_enabled),
            "memory_search_k": int(memory_search_k),
            "memory_search_max_chars": int(memory_search_max_chars),
            "memory_search_time_window_rounds": int(memory_search_time_window_rounds),
            "memory_tier_a_max_chars": int(memory_tier_a_max_chars),
            "memory_tier_b_max_chars": int(memory_tier_b_max_chars),
            "memory_tier_c_max_chars": int(memory_tier_c_max_chars),
            "memory_total_max_chars": int(memory_total_max_chars),
            "memory_tier_c_uncertainty_threshold": float(
                memory_tier_c_uncertainty_threshold
            ),
            "memory_reflection_cadence_rounds": int(memory_reflection_cadence_rounds),
            "memory_reflection_min_events": int(memory_reflection_min_events),
            "memory_reflection_trigger_importance_sum": float(
                memory_reflection_trigger_importance_sum
            ),
            "memory_reflection_max_items_per_run": int(
                memory_reflection_max_items_per_run
            ),
            "memory_embedding_model": str(memory_embedding_model).strip(),
            "memory_embedding_async": bool(memory_embedding_async),
            "memory_importance_mode": str(memory_importance_mode).strip(),
            "memory_backend": (
                "hybrid_semantic" if bool(memory_semantic_enabled) else "simple_recent"
            ),
            "memory_prompt_mode": "subtle_timeline",
            "memory_reply_context_max_chars": int(max_thread_context_chars),
            "memory_vote_signal_only": False,
        },
    }

    if not _apply_population_attributes_to_client_config(config, population_id):
        flash(
            _(
                "The selected population has no usable agents or is missing age data. Rebuild or re-upload the population before creating a client."
            ),
            "error",
        )
        return redirect(request.referrer)

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    prompt_packs.write_pack(
        "prompts.json", f"{data_base_path}prompts.json", prompt_language
    )
    prompt_packs.record_language(
        data_base_path, client=name, client_language=prompt_language
    )

    # Create agent population file
    writable_base = get_writable_path()

    if "database_server.db" in exp.db_name:
        # exp.db_name is like "experiments/uid/database_server.db"
        filename = os.path.join(
            writable_base,
            "y_web",
            exp.db_name.split("database_server.db")[0],
            f"{population.name.replace(' ', '')}.json",
        )
    else:
        # Legacy format
        filename = os.path.join(
            writable_base,
            "y_web",
            "experiments",
            exp.db_name.replace("experiments_", ""),
            f"{population.name.replace(' ', '')}.json",
        )

    agents = db.session.scalars(
        select(Agent_Population).filter_by(population_id=population.id)
    ).all()
    # get the agent details
    agents = [
        db.session.scalars(select(Agent).filter_by(id=a.agent_id)).first()
        for a in agents
    ]

    # Assign archetypes to agents based on distribution probabilities
    num_agents = len(agents)
    archetype_assignments = []

    if enable_archetypes and num_agents > 0:
        # Build list of active archetypes and their probabilities
        active_archetypes = []
        active_probabilities = []

        if archetype_validator > 0:
            active_archetypes.append("validator")
            active_probabilities.append(archetype_validator)

        if archetype_broadcaster > 0:
            active_archetypes.append("broadcaster")
            active_probabilities.append(archetype_broadcaster)

        if archetype_explorer > 0:
            active_archetypes.append("explorer")
            active_probabilities.append(archetype_explorer)

        # Normalize probabilities if they don't sum to 1
        if len(active_probabilities) > 0:
            total_prob = sum(active_probabilities)
            if total_prob > 0:
                active_probabilities = [p / total_prob for p in active_probabilities]
                # Assign archetypes to agents using numpy random choice
                archetype_assignments = np.random.choice(
                    active_archetypes, size=num_agents, p=active_probabilities
                ).tolist()
            else:
                # If all probabilities are 0, assign None
                archetype_assignments = [None] * num_agents
        else:
            # No active archetypes
            archetype_assignments = [None] * num_agents
    else:
        # Archetypes disabled, assign None to all agents
        archetype_assignments = [None] * num_agents

    res = {"agents": []}
    feature_map = summarize_agent_custom_features_bulk([agent.id for agent in agents])
    agent_ext_rows = (
        db.session.scalars(
            select(Agent_Ext).filter(
                Agent_Ext.agent_id.in_([agent.id for agent in agents])
            )
        ).all()
        if agents
        else []
    )
    agent_ext_map: dict[int, dict[str, str]] = {}
    for entry in agent_ext_rows:
        agent_ext_map.setdefault(entry.agent_id, {})[
            entry.feature_name
        ] = entry.feature_value
    for idx, a in enumerate(agents):
        custom_prompt = db.session.scalars(
            select(Agent_Profile).filter_by(agent_id=a.id)
        ).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # Allocate topics based on specified percentages
        interests = allocate_topics_by_percentage(topics, topic_percentages)

        ints = [interests, len(interests)]

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=a.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        agent_payload = {
            "name": a.name,
            "email": f"{a.name}@ysocial.it",
            "password": f"{a.name}",
            "age": a.age,
            "type": user_type,  # ,a.ag_type,
            "leaning": a.leaning,
            "interests": ints,
            "oe": a.oe,
            "co": a.co,
            "ex": a.ex,
            "ag": a.ag,
            "ne": a.ne,
            "rec_sys": crecsys,
            "frec_sys": frecsys,
            "language": a.language,
            "owner": exp.owner,
            "education_level": a.education_level,
            "round_actions": int(a.round_actions),
            "gender": a.gender,
            "nationality": a.nationality,
            "toxicity": a.toxicity,
            "is_page": 0,
            "prompts": custom_prompt if custom_prompt else None,
            "daily_activity_level": a.daily_activity_level,
            "profession": a.profession,
            "activity_profile": activity_profile_name,
            "archetype": archetype_assignments[idx],
            "opinions": (
                {i: random.random() for i in ints[0]} if opinions_enabled else None
            ),  # @todo: check initial opinions
        }
        _apply_structured_features_to_agent_payload(
            agent_payload, feature_map.get(a.id, {})
        )
        _provider_of(exp).hpc_agent_payload(
            agent_payload, a, agent_ext_map.get(a.id, {}), normalize_recsys=False
        )
        res["agents"].append(agent_payload)

    # get the pages associated with the population
    pages = db.session.scalars(
        select(Page_Population).filter_by(population_id=population.id)
    ).all()
    pages = [
        db.session.scalars(select(Page).filter_by(id=p.page_id)).first() for p in pages
    ]

    for p in pages:
        # get pages topics
        page_topics = (
            db.session.query(Exp_Topic, Topic_List)
            .join(Topic_List)
            .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
            .all()
        )
        page_topics = [t[1].name for t in page_topics]
        page_topics = list(set(page_topics) & set(topics))

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=p.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": p.name,
                "email": f"{p.name}@ysocial.it",
                "password": f"{p.name}",
                "age": 0,
                "type": user_type,
                "leaning": p.leaning,
                "interests": [page_topics, len(page_topics)],
                "oe": "",
                "co": "",
                "ex": "",
                "ag": "",
                "ne": "",
                "rec_sys": "",
                "frec_sys": "",
                "language": "english",
                "owner": exp.owner,
                "education_level": "",
                "round_actions": 3,
                "gender": "",
                "nationality": "",
                "toxicity": "none",
                "is_page": 1,
                "feed_url": p.feed,
                "activity_profile": activity_profile_name,
            }
        )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w", encoding="utf-8"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = db.session.scalars(
            select(Population).filter_by(id=client.population_id)
        ).all()
        # get agents for the populations
        agents = db.session.scalars(
            select(Agent_Population).filter(
                Agent_Population.population_id.in_([p.id for p in populations])
            )
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [
            db.session.scalars(select(Agent).filter_by(id=a.agent_id)).first().name
            for a in agents
        ]

        BASE = get_writable_path()
        dbtypte = get_db_type()

        if dbtypte == "sqlite":
            exp_folder = exp.db_name.split(os.sep)[1]
        else:
            exp_folder = exp.db_name.removeprefix("experiments_")

        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w", encoding="utf-8") as o:
                    error, error2 = False, False
                    with open(temp_path, "r", encoding="utf-8") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = db.session.scalars(
                                select(Agent).filter_by(name=l[0])
                            ).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = db.session.scalars(
                                    select(Agent_Population).filter(
                                        Agent_Population.agent_id.in_(aids),
                                        Agent_Population.population_id
                                        == client.population_id,
                                    )
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = db.session.scalars(
                                    select(Page).filter_by(name=l[0])
                                ).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = db.session.scalars(
                                        select(Page_Population).filter(
                                            Page_Population.page_id.in_(aids),
                                            Page_Population.population_id
                                            == client.population_id,
                                        )
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = db.session.scalars(
                                select(Agent).filter_by(name=l[1])
                            ).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = db.session.scalars(
                                    select(Agent_Population).filter(
                                        Agent_Population.agent_id.in_(aids),
                                        Agent_Population.population_id
                                        == client.population_id,
                                    )
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = db.session.scalars(
                                    select(Page).filter_by(name=l[1])
                                ).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = db.session.scalars(
                                        select(Page_Population).filter(
                                            Page_Population.page_id.in_(aids),
                                            Page_Population.population_id
                                            == client.population_id,
                                        )
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    _(
                                        "Agent %(l)s or %(l2)s not found in network file.",
                                        l=l[0],
                                        l2=l[1],
                                    ),
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    _(
                        "Network file format error: provide a csv file containing two columns with agent names. No header required."
                    ),
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            # Extract parameters with defaults
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1
            k = (
                int(request.form.get("network_k"))
                if request.form.get("network_k")
                else 4
            )
            ws_p = (
                float(request.form.get("network_ws_p"))
                if request.form.get("network_ws_p")
                else 0.3
            )
            plc_m = (
                int(request.form.get("network_plc_m"))
                if request.form.get("network_plc_m")
                else 2
            )
            plc_p = (
                float(request.form.get("network_plc_p"))
                if request.form.get("network_plc_p")
                else 0.5
            )
            blocks = (
                int(request.form.get("network_blocks"))
                if request.form.get("network_blocks")
                else 3
            )
            p_in = (
                float(request.form.get("network_p_in"))
                if request.form.get("network_p_in")
                else 0.3
            )
            p_out = (
                float(request.form.get("network_p_out"))
                if request.form.get("network_p_out")
                else 0.05
            )
            tau1 = (
                float(request.form.get("network_tau1"))
                if request.form.get("network_tau1")
                else 2.5
            )
            tau2 = (
                float(request.form.get("network_tau2"))
                if request.form.get("network_tau2")
                else 1.5
            )
            mu = (
                float(request.form.get("network_mu"))
                if request.form.get("network_mu")
                else 0.1
            )
            avg_degree = (
                int(request.form.get("network_avg_degree"))
                if request.form.get("network_avg_degree")
                else 5
            )

            n = len(agent_ids)

            # Generate network based on selected model
            if network_model == "BA":
                g = nx.barabasi_albert_graph(n, m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(n, p=p)
            elif network_model == "WS":
                g = nx.watts_strogatz_graph(n, k=k, p=ws_p)
            elif network_model == "PLC":
                g = nx.powerlaw_cluster_graph(n, m=plc_m, p=plc_p)
            elif network_model == "C":
                g = nx.complete_graph(n)
            elif network_model == "SBM":
                # Divide nodes into blocks
                block_sizes = [n // blocks] * blocks
                # Add remaining nodes to last block
                block_sizes[-1] += n % blocks
                # Create probability matrix
                probs = [
                    [p_in if i == j else p_out for j in range(blocks)]
                    for i in range(blocks)
                ]
                g = nx.stochastic_block_model(block_sizes, probs)
            elif network_model == "LFR":
                # LFR benchmark with community structure
                # Calculate min_community: at least 5 nodes, at most n/3 to allow multiple communities
                min_community = min(max(5, n // 10), n // 3)
                g = nx.LFR_benchmark_graph(
                    n=n,
                    tau1=tau1,
                    tau2=tau2,
                    mu=mu,
                    average_degree=avg_degree,
                    min_community=min_community,
                )
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w", encoding="utf-8") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    log_telemetry_event(
        current_user,
        data={
            "action": "create_client",
            "data": {
                "llm_agents_enabled": llm_agents_enabled,
                "days": days,
                "percentage_new_agents_iteration": percentage_new_agents_iteration,
                "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
                "max_length_thread_reading": max_length_thread_reading,
                "reading_from_follower_ratio": reading_from_follower_ratio,
                "probability_of_daily_follow": probability_of_daily_follow,
                "attention_window": attention_window,
                "visibility_rounds": visibility_rounds,
                "actions": {
                    "post": post,
                    "share": share,
                    "image": image,
                    "comment": comment,
                    "read": read,
                    "news": news,
                    "search": search,
                    "vote": vote,
                    "share_link": share_link,
                    "share_image": share_image,
                },
                "llm": user_type,
                "probability_of_secondary_follow": probability_of_secondary_follow,
                "crecsys": crecsys,
                "frecsys": frecsys,
            },
        },
    )

    if bool(opinions_enabled):
        return redirect(
            url_for(
                "clientsr.opinion_configuration_standard",
                idexp=exp_id,
                client_id=client.id,
            )
        )

    return experiment_details_page(exp_id)


@clientsr.route("/admin/create_standard_client", methods=["POST"])
@login_required
def create_standard_client():
    """Create a standard microblogging client."""
    return _create_standard_client_internal()

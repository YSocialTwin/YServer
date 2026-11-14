"""The microblogging platform on the Standard runtime: what YSocial needs to run, show and manage a microblogging
experiment whose server is YServer and whose client is YClient.

This repository is a silo: it carries its own pages (``routes/``, ``templates/``, ``static/``) and does not know
the HPC repository of the same platform (YSimulator), which declares its own provider for the same platform key. The
core tells the two apart by repository id and chooses by the runtime of the experiment (``simulator_types``). The
provider is declared in ``meta/registry.json`` (``platform`` section), loaded by YSocial at startup, and talks to the
core through ``y_web.sdk`` only.
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping, Optional

from y_web.sdk import (
    N_,
    STANDARD,
    CreationRules,
    FederationTraits,
    PlatformProvider,
    StandardRuntime,
)
from y_web.sdk import gettext as _


class MicrobloggingStandard(PlatformProvider):
    key = "microblogging"
    id = "ysocial_server"
    simulator_types = (STANDARD,)
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10

    @property
    def human_gateway(self):
        """How a person of a World Simulation gets an account here and acts (``gateway.py``)."""
        return importlib.import_module(f"{__package__}.gateway").HUMAN_GATEWAY

    federation_traits = FederationTraits(
        mdi_icon="mdi-message-text-outline",
        local_kind="post",
        author_sql="SELECT p.id, u.username, p.user_id FROM post p LEFT JOIN user_mgmt u ON u.id = p.user_id WHERE p.id IN ({q})",
        content_path="/{exp}/thread/{id}",
        profile_path="/{exp}/profile/{account}/recent/1",
        account_sql="SELECT id, username FROM user_mgmt WHERE id = ?",
        text_limit=280,
        decision_triggers=("publish", "interaction"),
        simulators=(STANDARD,),
        topic_migration_key="topic_migration",
        topic_migration_always=False,
    )
    default_platform = True

    prompt_pack = ("prompts.json", "prompts.json")
    standard_runtime = StandardRuntime(
        server_repo="YServer",
        client_repo="YClient",
        fake_agent_module="y_client.classes",
        activity_profiles=True,
    )
    profile_template = "@ysocial_server/microblogging/profile.html"
    has_interview = True

    def attach_routes(self) -> None:
        importlib.import_module(f"{__package__}.routes")

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"

    def creation_rules(self, simulator_type: str) -> CreationRules:
        return CreationRules(
            database="server", copies_clean_database=simulator_type == STANDARD
        )

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        # the only runtime of this repository is Standard, whatever was asked for
        if available["microblogging"]:
            return STANDARD, None
        return STANDARD, _(
            "Microblogging experiments are unavailable because neither YServer nor YClient is present."
        )

    def render_interview(self, exp_id: int, context: dict) -> Any:
        from flask import render_template
        from flask_login import current_user
        from sqlalchemy import select
        from y_web.sdk.models import Admin_users, Agent, db

        profile_pic = ""
        try:
            agent = db.session.scalars(
                select(Agent).filter_by(name=current_user.username)
            ).first()
            if agent is not None and agent.profile_pic is not None:
                profile_pic = agent.profile_pic
            else:
                admin = db.session.scalars(
                    select(Admin_users).filter_by(username=current_user.username)
                ).first()
                profile_pic = admin.profile_pic if admin else ""
        except Exception:
            profile_pic = ""
        return render_template(
            "@ysocial_server/microblogging/interview.html",
            profile_pic=profile_pic,
            experiment_memory_enabled=True,
            len=len,
            **context,
        )

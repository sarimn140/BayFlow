"""The worker: one job per dispatched AI leg (spec 05 §2, §4.10, §5.4, §6).

Explicit dispatch only (`agent_name="bayflow-front-desk"`). The job reads its dispatch metadata,
starts the session with the API (A2), greets the caller, enforces the time limit and silence rules,
and after the room closes posts the transcript and summary (A5).
"""

import asyncio
import contextlib
import json
import logging
from typing import Any

from livekit.agents import AgentServer, AgentSession, JobContext
from livekit.agents.llm import RealtimeModel

from bayflow_agent.config import Settings, get_settings
from bayflow_agent.front_desk import FrontDeskAgent
from bayflow_agent.internal_api import InternalApi, InternalApiError
from bayflow_agent.prompts import SILENT_GOODBYE, STILL_THERE, WRAP_UP, greeting
from bayflow_agent.summary import summarise
from bayflow_agent.transcript import build_transcript

logger = logging.getLogger("bayflow_agent")

AGENT_NAME = "bayflow-front-desk"
WRAP_UP_LEAD_SECONDS = 30


def realtime_model(settings: Settings) -> RealtimeModel:
    """The selected speech-to-speech model, with the canonical key passed explicitly."""
    assert settings.llm_api_key is not None  # noqa: S101 - checked at start-up
    key = settings.llm_api_key.get_secret_value()
    options: dict[str, Any] = {"api_key": key}
    if settings.ai_realtime_model:
        options["model"] = settings.ai_realtime_model
    if settings.ai_provider == "gemini":
        from livekit.plugins import google  # noqa: PLC0415 - the selected provider only

        return google.realtime.RealtimeModel(**options)
    from livekit.plugins import openai  # noqa: PLC0415

    return openai.realtime.RealtimeModel(voice="marin", **options)


def build_server(settings: Settings) -> AgentServer:
    server = AgentServer(
        ws_url=settings.call_provider_url,
        api_key=settings.call_provider_api_key.get_secret_value()
        if settings.call_provider_api_key
        else None,
        api_secret=settings.call_provider_api_secret.get_secret_value()
        if settings.call_provider_api_secret
        else None,
        port=settings.agent_port,
        num_idle_processes=1,  # one warm job process
        shutdown_process_timeout=60.0,  # room for the post-call summary
    )

    server.rtc_session(front_desk, agent_name=AGENT_NAME)
    return server


async def front_desk(ctx: JobContext) -> None:
    """The job entrypoint. Module level, because job processes receive it pickled."""
    await run_job(ctx, get_settings())


async def run_job(ctx: JobContext, settings: Settings) -> None:
    metadata = json.loads(ctx.job.metadata or "{}")
    assert settings.agent_service_token is not None  # noqa: S101 - checked at start-up
    api = InternalApi(
        settings.api_internal_url,
        settings.agent_service_token.get_secret_value(),
        metadata["call_id"],
        metadata["call_token"],
    )
    try:
        started = await api.start_session()  # A2
    except InternalApiError as exc:
        logger.info("job.not_waiting", extra={"call_id": api.call_id, "status": exc.status})
        await api.aclose()
        return
    shop = started["shop"]
    max_seconds = int(started.get("max_ai_seconds", 300))
    session: AgentSession[Any] = AgentSession(llm=realtime_model(settings), user_away_timeout=15.0)
    agent = FrontDeskAgent(api, shop_name=shop["name"], shop_city=shop["city"])
    timers: list[asyncio.Task[None]] = []

    async def after_call() -> None:  # runs once the room is gone (bounded by the shutdown timeout)
        for task in timers:
            task.cancel()
        transcript = build_transcript(session.history.items)
        payload = await summarise(settings, shop["name"], transcript)
        status = await api.post_summary(payload)
        logger.info("job.summary_posted", extra={"call_id": api.call_id, "status": status})
        await api.aclose()

    ctx.add_shutdown_callback(after_call)
    watch_silence(session, agent)
    try:
        await ctx.connect()
        await session.start(room=ctx.room, agent=agent)
        session.generate_reply(instructions=greeting(shop["name"]))
        timers.append(asyncio.create_task(time_limit(session, agent, api, max_seconds)))
    except Exception as exc:  # model or connection failure → A3 with an error
        logger.exception("job.failed", extra={"call_id": api.call_id})
        with contextlib.suppress(Exception):
            await api.end_call(error=f"LLM_ERROR: {type(exc).__name__}")
        raise


def watch_silence(session: AgentSession[Any], agent: FrontDeskAgent) -> None:
    """§4.10: when the caller goes quiet, ask once; the second time, say goodbye and end."""
    away = {"count": 0}

    @session.on("user_state_changed")
    def _on_user_state(event: Any) -> None:
        if getattr(event, "new_state", None) != "away" or agent.ended:
            return
        away["count"] += 1
        session.generate_reply(instructions=STILL_THERE if away["count"] == 1 else SILENT_GOODBYE)


async def time_limit(
    session: AgentSession[Any], agent: FrontDeskAgent, api: InternalApi, max_seconds: int
) -> None:
    """§4.10: wrap-up instructions 30 s before the limit, then end the leg at the limit."""
    await asyncio.sleep(max(0, max_seconds - WRAP_UP_LEAD_SECONDS))
    if not agent.ended:
        session.generate_reply(instructions=WRAP_UP)
    await asyncio.sleep(WRAP_UP_LEAD_SECONDS)
    if not agent.ended:
        await api.end_call()


def main() -> None:
    from livekit.agents import cli  # noqa: PLC0415

    settings = get_settings()
    missing = settings.missing()
    if missing:
        msg = f"the AI Front Desk needs: {', '.join(missing)}"
        raise SystemExit(msg)
    cli.run_app(build_server(settings))

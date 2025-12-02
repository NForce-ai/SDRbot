"""Observability callback handlers for LangSmith, Langfuse, and Opik."""

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers import LangChainTracer
from langfuse.langchain import CallbackHandler as LangfuseHandler
from langsmith import Client as LangSmithClient
from opik.integrations.langchain import OpikTracer

from sdrbot_cli.config import COLORS, console, settings
from sdrbot_cli.services.registry import load_config


def get_observability_callbacks() -> list[BaseCallbackHandler]:
    """Create and return configured observability callback handlers.

    Only returns callbacks for services that are enabled in the registry
    AND have credentials configured.

    Returns:
        List of callback handlers for enabled observability tools.
    """
    callbacks: list[BaseCallbackHandler] = []
    config = load_config()

    # LangSmith
    if config.is_enabled("langsmith") and settings.has_langsmith:
        try:
            client = LangSmithClient(api_key=settings.langsmith_api_key)
            tracer = LangChainTracer(
                project_name=settings.langsmith_project or "SDRbot",
                client=client,
            )
            callbacks.append(tracer)
            console.print(f"[{COLORS['dim']}]LangSmith tracing enabled[/]")
        except Exception as e:
            console.print(f"[yellow]LangSmith initialization failed: {e}[/yellow]")

    # Langfuse
    if config.is_enabled("langfuse") and settings.has_langfuse:
        try:
            handler = LangfuseHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,  # None uses default cloud
            )
            callbacks.append(handler)
            console.print(f"[{COLORS['dim']}]Langfuse tracing enabled[/]")
        except Exception as e:
            console.print(f"[yellow]Langfuse initialization failed: {e}[/yellow]")

    # Opik
    if config.is_enabled("opik") and settings.has_opik:
        try:
            tracer = OpikTracer(
                project_name=settings.opik_project or "SDRbot",
            )
            callbacks.append(tracer)
            console.print(f"[{COLORS['dim']}]Opik tracing enabled[/]")
        except Exception as e:
            console.print(f"[yellow]Opik initialization failed: {e}[/yellow]")

    return callbacks

"""WatiAgent: the agentic loop that bridges LLM and WATI API."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import litellm
import structlog
from litellm import Router

from wati_agent.agent.memory import ConversationMemory
from wati_agent.agent.prompts import get_system_prompt
from wati_agent.agent.tools import (
    TOOL_DISPATCH,
    TOOL_HTTP_MAP_V1,
    WATI_TOOLS,
    resolve_endpoint,
)
from wati_agent.api.base import WatiClient
from wati_agent.api.models import CustomParam
from wati_agent.config import Settings
from wati_agent.executor import PlanExecutor
from wati_agent.executor.plan import ActionPlan
from wati_agent.observability.audit import AuditLogger

logger = structlog.get_logger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True
litellm.set_verbose = False

# Tools that modify data — intercepted by dry-run
WRITE_TOOLS = frozenset(
    {
        "send_text_message",
        "send_template_message",
        "add_contact",
        "update_contacts",
        "add_tag",
        "remove_tag",
        "assign_operator",
        "assign_ticket",
        "send_broadcast_to_segment",
    }
)


@dataclass
class ToolCallRecord:
    """Record of a single tool call for display."""

    name: str
    params: dict[str, Any]
    result: dict[str, Any]
    success: bool
    duration_ms: float


@dataclass
class AgentResponse:
    """Response from the agent to the user."""

    text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    has_pending_writes: bool = False


def _get_api_key(model: str, settings: Settings) -> str | None:
    """Resolve the API key for a given model string."""
    if "openrouter" in model:
        return settings.openrouter_api_key or None
    elif "anthropic" in model:
        return settings.anthropic_api_key or None
    else:
        return settings.openai_api_key or None


class WatiAgent:
    """Orchestrates LLM reasoning and WATI API execution.

    Dry-run mode: Write tools are intercepted and queued. The CLI asks
    for confirmation once, then calls execute_pending_writes() to run
    them for real. This is deterministic — no dependency on LLM behavior.
    """

    def __init__(
        self,
        settings: Settings,
        api_client: WatiClient,
        audit: AuditLogger,
    ) -> None:
        self._api = api_client
        self._audit = audit

        # Select memory mode based on active API client
        from wati_agent.api.mock import MockWatiClient

        self._http_map = TOOL_HTTP_MAP_V1
        api_mode = "mock" if isinstance(api_client, MockWatiClient) else "real"
        self._memory = ConversationMemory(api_mode=api_mode)
        self.dry_run = settings.dry_run_default
        self._pending_writes: list[tuple[str, dict[str, Any]]] = []

        # Build model list for litellm Router (primary + fallbacks)
        model_list: list[dict] = []

        primary_params: dict[str, Any] = {"model": settings.llm_model}
        key = _get_api_key(settings.llm_model, settings)
        if key:
            primary_params["api_key"] = key
        model_list.append(
            {
                "model_name": "main",
                "litellm_params": primary_params,
            }
        )

        if settings.llm_fallback_models:
            for fb_model in settings.llm_fallback_models.split(","):
                fb_model = fb_model.strip()
                if not fb_model:
                    continue
                fb_params: dict[str, Any] = {"model": fb_model}
                fb_key = _get_api_key(fb_model, settings)
                if fb_key:
                    fb_params["api_key"] = fb_key
                model_list.append(
                    {
                        "model_name": "main",
                        "litellm_params": fb_params,
                    }
                )

        self._router = Router(model_list=model_list, num_retries=1)

    async def handle_message(self, user_input: str, session_id: str) -> AgentResponse:
        """Process user input through the agentic loop."""
        messages = self._memory.get_messages(session_id)
        messages.append({"role": "user", "content": user_input})
        tool_records: list[ToolCallRecord] = []
        self._pending_writes.clear()

        max_iterations = 15
        for _ in range(max_iterations):
            response = await self._router.acompletion(
                model="main",
                messages=[{"role": "system", "content": get_system_prompt()}, *messages],
                tools=WATI_TOOLS,
                max_tokens=4096,
            )

            choice = response.choices[0]
            message = choice.message

            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                text = message.content or ""
                self._memory.set_messages(session_id, messages)
                return AgentResponse(
                    text=text,
                    tool_calls=tool_records,
                    has_pending_writes=len(self._pending_writes) > 0,
                )

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                logger.info("tool_call", tool=fn_name, args=fn_args)

                start = time.monotonic()
                try:
                    if self.dry_run and fn_name in WRITE_TOOLS:
                        # Queue for later execution
                        self._pending_writes.append((fn_name, fn_args))
                        result = {
                            "dry_run": True,
                            "would_execute": fn_name,
                            "params": fn_args,
                            "message": f"[DRY-RUN] Would execute: {fn_name}",
                        }
                        success = True
                        error = None
                    else:
                        result = await self._execute_tool(fn_name, fn_args)
                        success = True
                        error = None
                except Exception as e:
                    result = {"error": str(e)}
                    success = False
                    error = str(e)
                    logger.error("tool_call_failed", tool=fn_name, error=error)
                elapsed_ms = (time.monotonic() - start) * 1000

                tool_records.append(
                    ToolCallRecord(
                        name=fn_name,
                        params=fn_args,
                        result=result,
                        success=success,
                        duration_ms=round(elapsed_ms, 1),
                    )
                )

                # Audit real executions with HTTP method + endpoint
                if not (self.dry_run and fn_name in WRITE_TOOLS):
                    method, endpoint = resolve_endpoint(fn_name, fn_args, self._http_map)
                    self._audit.log_action(
                        session_id=session_id,
                        action=fn_name,
                        method=method,
                        endpoint=endpoint,
                        params=fn_args,
                        result=result if success else None,
                        success=success,
                        duration_ms=round(elapsed_ms, 1),
                        error=error,
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, default=str),
                    }
                )

        self._memory.set_messages(session_id, messages)
        return AgentResponse(
            text="Maximum iterations reached. Please try a simpler request.",
            tool_calls=tool_records,
        )

    async def summarize_results(self, plan: ActionPlan, session_id: str) -> str:
        """Ask the LLM to summarize execution results in natural language."""
        from wati_agent.executor.plan import StepStatus

        # Build a concise results summary for the LLM
        lines: list[str] = []
        for step in plan.steps:
            target = step.params.get("target", "?")
            tool = step.tool_name
            if step.status == StepStatus.SUCCESS:
                lines.append(f"- {tool}(target={target}): SUCCESS")
            elif step.status == StepStatus.FAILED:
                lines.append(f"- {tool}(target={target}): FAILED - {step.error}")
            elif step.status == StepStatus.SKIPPED:
                lines.append(f"- {tool}(target={target}): SKIPPED")

        results_text = "\n".join(lines)

        messages = self._memory.get_messages(session_id)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"[SYSTEM: The following actions were executed. "
                    f"Summarize the results for the user in natural language. "
                    f"Be concise and friendly.]\n\n{results_text}"
                ),
            }
        )

        response = await self._router.acompletion(
            model="main",
            messages=[{"role": "system", "content": get_system_prompt()}, *messages],
            max_tokens=1024,
        )

        text = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": text})
        self._memory.set_messages(session_id, messages)
        return text

    def get_pending_count(self) -> int:
        """Get number of pending write actions."""
        return len(self._pending_writes)

    def build_pending_plan(self, session_id: str) -> ActionPlan:
        """Build an ActionPlan from queued pending writes."""
        executor = self.get_plan_executor(session_id)
        plan = executor.build_plan(self._pending_writes)
        self._pending_writes.clear()
        return plan

    def get_plan_executor(self, session_id: str) -> PlanExecutor:
        """Return a PlanExecutor wired with this agent's tool dispatch."""
        return PlanExecutor(
            tool_executor=self._execute_tool,
            audit=self._audit,
            session_id=session_id,
            http_map=self._http_map,
        )

    async def _execute_tool(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call against the real API client.

        Uses TOOL_DISPATCH to generically map tool names to WatiClient methods,
        avoiding per-tool boilerplate handlers.
        """
        spec = TOOL_DISPATCH.get(name)
        if not spec:
            raise ValueError(f"Unknown tool: {name}")

        # Build kwargs from spec: required args + optional defaults + custom_params
        missing = [arg for arg in spec.args if arg not in params]
        if missing:
            raise ValueError(f"Missing required parameters for {name}: {', '.join(missing)}")
        kwargs: dict[str, Any] = {arg: params[arg] for arg in spec.args}
        for key, default in spec.defaults.items():
            kwargs[key] = params.get(key, default)
        if spec.has_custom_params:
            kwargs["custom_params"] = _parse_custom_params(params.get("custom_params"))

        api_method = getattr(self._api, spec.method)
        result = await api_method(**kwargs)
        data = result.model_dump(mode="json")

        # send_template_message: check for API-level failure
        if name == "send_template_message" and not result.result:
            raise ValueError(result.status or "Failed to send template")

        return data


def _parse_custom_params(raw: list[dict] | None) -> list[CustomParam] | None:
    """Convert raw dicts from LLM to CustomParam objects."""
    if not raw:
        return None
    return [CustomParam(name=p["name"], value=p["value"]) for p in raw]

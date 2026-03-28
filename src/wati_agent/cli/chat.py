"""Interactive CLI REPL for the WATI Agent."""

from __future__ import annotations

import asyncio
import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from wati_agent.agent.agent import AgentResponse, WatiAgent
from wati_agent.config import Settings
from wati_agent.executor import PlanExecutor
from wati_agent.executor.plan import ActionPlan, StepStatus
from wati_agent.observability.audit import AuditLogger

# Words that mean "no" — everything else is treated as "yes"
_NEGATIVE_WORDS = frozenset(
    {
        "n",
        "no",
        "nao",
        "não",
        "nope",
        "nah",
        "never",
        "cancel",
        "cancelar",
        "cancela",
        "para",
        "pare",
        "stop",
        "abort",
        "abortar",
        "não quero",
        "nao quero",
        "desisto",
        "deixa",
        "esquece",
        "forget",
        "negative",
    }
)

console = Console()


def _is_negative(text: str) -> bool:
    """Check if user input expresses negative intent."""
    words = text.lower().strip().split()
    return any(w in _NEGATIVE_WORDS for w in words)


# --- Message History Tracker ---


# --- Display functions ---


def _print_response(response: AgentResponse) -> None:
    """Print only the agent's text response (clean chat experience)."""
    if response.text:
        lines = response.text.strip().split("\n", 1)
        console.print(f"\n[bold cyan]wati agent:[/bold cyan] {lines[0]}")
        if len(lines) > 1:
            console.print(Markdown(lines[1]))
    console.print()


def _format_audit_details(params: dict) -> str:
    """Format audit params for readable display — no truncation."""
    skip_keys = {"page_size", "page_number"}
    parts: list[str] = []

    if "target" in params:
        parts.append(f"to: {params['target']}")

    for key, value in params.items():
        if key in skip_keys or key == "target":
            continue
        parts.append(f"{key}={value}")

    return ", ".join(parts) if parts else "-"


def _method_style(method: str) -> str:
    """Color-code HTTP method for display."""
    styles = {"GET": "dim", "POST": "yellow", "PUT": "blue", "DELETE": "red"}
    style = styles.get(method, "white")
    return f"[{style}]{method}[/{style}]"


def _print_audit_all(audit: AuditLogger, current_session_id: str) -> None:
    """Show full audit log from all sessions, grouped by session."""
    all_entries = audit.load_all_from_disk()
    # Also include current in-memory entries not yet on disk
    current_entries = audit.get_session_entries(current_session_id)
    disk_ts = {e.timestamp.isoformat() for e in all_entries if e.session_id == current_session_id}
    for e in current_entries:
        if e.timestamp.isoformat() not in disk_ts:
            all_entries.append(e)

    # Group by session, sorted by last action desc
    from collections import defaultdict as _dd

    by_session: dict[str, list] = _dd(list)
    for e in all_entries:
        by_session[e.session_id].append(e)

    # Ensure current session always appears (even if no actions yet)
    if current_session_id not in by_session:
        by_session[current_session_id] = []

    # Sort sessions: current first, then most recent to oldest
    def _sort_key(kv: tuple) -> tuple:
        sid, entries = kv
        if sid == current_session_id:
            return (0, "9")  # current always first
        if entries:
            # Negate by using reverse string for desc order
            ts = max(e.timestamp for e in entries).isoformat()
            return (1, ts)
        return (2, "")

    sorted_sessions = sorted(by_session.items(), key=_sort_key, reverse=False)
    # Re-sort: current first, then others by timestamp desc
    current = [(s, e) for s, e in sorted_sessions if s == current_session_id]
    others = [(s, e) for s, e in sorted_sessions if s != current_session_id]
    others.sort(
        key=lambda kv: max(e.timestamp for e in kv[1]).isoformat() if kv[1] else "",
        reverse=True,
    )
    sorted_sessions = current + others

    if not any(entries for _, entries in sorted_sessions):
        console.print("[dim]No audit history found.[/dim]")
        return

    for sid, entries in sorted_sessions:
        is_current = sid == current_session_id
        if is_current:
            label = f"[bold green]>> {sid} (current session)[/bold green]"
        else:
            label = f"[cyan]{sid}[/cyan]"
        console.print(f"\n{label}  [dim]({len(entries)} actions)[/dim]")

        if entries:
            # Sort entries within session by time asc
            entries.sort(key=lambda e: e.timestamp)
            _print_audit_entries(entries, title="")
        else:
            console.print("[dim]  No actions yet in this session.[/dim]")


def _print_audit_entries(entries: list, title: str = "Session Audit Trail") -> None:
    """Display a list of audit entries as a table."""
    if not entries:
        console.print("[dim]No actions recorded.[/dim]")
        return

    table = Table(
        title=title,
        show_header=True,
        header_style="bold",
        box=None,
    )
    table.add_column("Time", style="dim", width=10)
    table.add_column("Method", width=6)
    table.add_column("Endpoint", style="cyan", no_wrap=False)
    table.add_column("Action", style="bold")
    table.add_column("Status", width=10)
    table.add_column("Duration", justify="right", width=8)
    table.add_column("Details", no_wrap=False)

    message_actions = {"user_message", "agent_response"}
    current_plan_id = None
    for e in entries:
        # Visual separator between plans
        if e.plan_id and e.plan_id != current_plan_id:
            if current_plan_id is not None:
                table.add_row("", "", "", "", "", "", "")
            current_plan_id = e.plan_id

        time_str = e.timestamp.strftime("%H:%M:%S")

        if e.action in message_actions:
            # Conversation messages — show message_id
            msg_id = e.params.get("message_id", "-")
            if e.action == "user_message":
                label = "[green]You[/green]"
            else:
                label = "[cyan]wati agent[/cyan]"
            table.add_row(time_str, "[dim]-[/dim]", "-", label, "-", "-", msg_id)
            continue

        method = _method_style(e.method) if e.method else "[dim]-[/dim]"
        endpoint = e.endpoint or "-"

        if not e.success:
            status = f"[red]{e.error or 'failed'}[/red]"
        elif e.dry_run:
            status = "[yellow]dry-run[/yellow]"
        else:
            # Show delivery status from result if available
            rs = ""
            if e.result and isinstance(e.result, dict):
                rs = e.result.get("status", "")
            status = f"[green]{rs}[/green]" if rs else "[green]ok[/green]"

        duration = f"{e.duration_ms:.0f}ms" if e.duration_ms else "-"

        # Build details: params + message_id from result
        details = _format_audit_details(e.params)
        if e.result and isinstance(e.result, dict):
            mid = e.result.get("message_id")
            if mid:
                details += f", message_id={mid}"

        table.add_row(time_str, method, endpoint, e.action, status, duration, details)

    console.print(table)


def _print_help(dry_run: bool) -> None:
    """Display available commands."""
    help_text = Text()
    help_text.append("Available Commands:\n", style="bold")
    help_text.append("  /audit              ", style="cyan")
    help_text.append("Show API calls for current session\n")
    help_text.append("  /audit --all        ", style="cyan")
    help_text.append("List all audit sessions\n")
    help_text.append("  /audit --session ID ", style="cyan")
    help_text.append("Show audit for a specific session\n")
    help_text.append("  /dry-run on    ", style="cyan")
    help_text.append("Enable dry-run (preview before executing)\n")
    help_text.append("  /dry-run off   ", style="cyan")
    help_text.append("Disable dry-run (execute actions immediately)\n")
    help_text.append("  /clear         ", style="cyan")
    help_text.append("Clear conversation history\n")
    help_text.append("  /help          ", style="cyan")
    help_text.append("Show this help\n")
    help_text.append("  /quit          ", style="cyan")
    help_text.append("Save session and exit\n")
    dry_run_status = "[green]on[/green]" if dry_run else "[red]off[/red]"
    help_text.append(f"\n  Dry-run: {dry_run_status}", style="dim")
    console.print(Panel(help_text, title="Help", border_style="blue"))


# --- Plan execution ---


async def _execute_plan_batch(plan: ActionPlan, executor: PlanExecutor) -> bool:
    """Execute all plan steps after a single Y/n confirmation.

    Returns True if executed, False if cancelled.
    """
    n = len(plan.steps)
    suffix = "s" if n > 1 else ""
    try:
        answer = console.input(f"[bold]Confirm execution ({n} action{suffix})? [/bold]").strip()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if _is_negative(answer):
        for step in plan.steps:
            executor.skip_step(step)
        console.print("[dim]Cancelled.[/dim]\n")
        return False

    with console.status("[bold cyan]Executing...", spinner="dots"):
        for step in plan.steps:
            if step.status == StepStatus.FAILED:
                continue  # skip validation failures
            await executor.execute_step(step, plan_id=plan.id)

    return True


# --- Main loop ---


async def chat_loop(
    agent: WatiAgent,
    settings: Settings,
    audit: AuditLogger,
    *,
    is_mock_fallback: bool = False,
    api_version: str = "",
) -> None:
    """Main REPL loop."""
    session_id = str(uuid.uuid4())

    # Header
    if is_mock_fallback:
        api_mode = "[red]mock (fallback - wati API unavailable)[/red]"
    elif settings.use_mock_api:
        api_mode = "mock"
    else:
        version_label = f" ({api_version})" if api_version else ""
        api_mode = f"[green]live{version_label}[/green]"
    dr_label = "[green]on[/green]" if agent.dry_run else "[red]off[/red]"

    from wati_agent import __version__

    console.print(
        Panel(
            f"[bold]wati agent v{__version__}[/bold]\n"
            f"Model: [cyan]{settings.llm_model}[/cyan] | "
            f"API: [yellow]{api_mode}[/yellow] | "
            f"Dry-run: {dr_label}\n"
            f"Type [cyan]/help[/cyan] for commands. [cyan]/quit[/cyan] to exit.",
            border_style="green",
        )
    )

    # Silently load ALL previous sessions as accumulated context
    prev_sessions = agent._memory.load_all_previous_sessions()
    if prev_sessions:
        agent._memory.preload_context(session_id, prev_sessions)

    while True:
        try:
            user_input = console.input("[bold green]> [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            agent._memory.save_session(session_id)
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            parts = user_input.lower().split()
            cmd = parts[0]
            if cmd in ("/quit", "/exit", "/q"):
                agent._memory.save_session(session_id)
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "/help":
                _print_help(agent.dry_run)
                continue
            elif cmd == "/audit":
                if len(parts) >= 2 and parts[1] == "--all":
                    _print_audit_all(audit, session_id)
                elif len(parts) >= 3 and parts[1] == "--session":
                    # Use original (non-lowered) input for session ID
                    raw_parts = user_input.split()
                    target_sid = raw_parts[2] if len(raw_parts) >= 3 else ""
                    entries = audit.load_session_from_disk(target_sid)
                    if not entries:
                        # Try partial match
                        all_sessions = audit.list_sessions_from_disk()
                        for s in all_sessions:
                            if s["session_id"].startswith(target_sid):
                                entries = audit.load_session_from_disk(s["session_id"])
                                break
                    _print_audit_entries(entries, title="Session Audit Trail")
                else:
                    entries = audit.get_session_entries(session_id)
                    _print_audit_entries(entries)
                continue
            elif cmd == "/dry-run":
                if len(parts) >= 2 and parts[1] == "off":
                    agent.dry_run = False
                    console.print(
                        "[dim]Dry-run: [red]off[/red] — actions execute immediately.[/dim]"
                    )
                else:
                    agent.dry_run = True
                    console.print(
                        "[dim]Dry-run: [green]on[/green] — preview before executing.[/dim]"
                    )
                continue
            elif cmd == "/clear":
                agent._memory.clear(session_id)
                console.print("[dim]Conversation history cleared.[/dim]")
                continue
            elif cmd == "/reset":
                import shutil

                # Clear in-memory state
                agent._memory.clear(session_id)
                # Delete session files for current mode only
                sdir = agent._memory.sessions_dir
                if sdir.exists():
                    shutil.rmtree(sdir)
                # Delete audit log for current mode only
                audit_path = audit._file
                if audit_path.exists():
                    audit_path.unlink()
                console.print("[dim]All history, sessions, and audit logs deleted.[/dim]")
                continue
            else:
                console.print(f"[red]Unknown command: {cmd}[/red]. Type /help for commands.")
                continue

        # Log user message to audit
        msg_id = str(uuid.uuid4())[:8]
        audit.log_action(
            session_id=session_id,
            action="user_message",
            params={"message_id": f"msg-{msg_id}"},
        )

        # Process with agent
        with console.status("[bold cyan]Thinking...", spinner="dots"):
            try:
                response = await agent.handle_message(user_input, session_id)
            except Exception as e:
                import traceback

                console.print(f"[red]Error: {e}[/red]")
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
                continue

        _print_response(response)

        # Log agent response to audit
        if response.text:
            resp_id = str(uuid.uuid4())[:8]
            audit.log_action(
                session_id=session_id,
                action="agent_response",
                params={"message_id": f"msg-{resp_id}"},
            )

        # Dry-run: confirm and execute pending writes
        if response.has_pending_writes:
            plan = agent.build_pending_plan(session_id)
            executor = agent.get_plan_executor(session_id)
            executed = await _execute_plan_batch(plan, executor)
            if executed:
                # Ask LLM for natural language summary
                with console.status("[bold cyan]Summarizing...", spinner="dots"):
                    summary = await agent.summarize_results(plan, session_id)
                if summary:
                    sum_id = str(uuid.uuid4())[:8]
                    audit.log_action(
                        session_id=session_id,
                        action="agent_response",
                        params={"message_id": f"msg-{sum_id}"},
                    )
                    lines = summary.strip().split("\n", 1)
                    console.print(f"\n[bold cyan]wati agent:[/bold cyan] {lines[0]}")
                    if len(lines) > 1:
                        console.print(Markdown(lines[1]))
                    console.print()


def run_cli(
    agent: WatiAgent, settings: Settings, audit: AuditLogger, *, is_mock_fallback: bool = False
) -> None:
    """Entry point for the CLI."""
    asyncio.run(chat_loop(agent, settings, audit, is_mock_fallback=is_mock_fallback))

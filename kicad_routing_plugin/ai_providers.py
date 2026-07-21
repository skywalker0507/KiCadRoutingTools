"""Pluggable headless AI providers for the KiCad routing plugin.

The GUI uses one provider-neutral runner contract while each provider owns CLI
location, command construction, skill syntax, JSONL event parsing, model/effort
choices, and authentication guidance.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KNOWN_SKILLS = {
    "analyze-power-nets",
    "diagnose-routing-failures",
    "find-high-speed-nets",
    "identify-diff-pairs",
    "plan-pcb-routing",
    "recommend-plane-mappings",
    "recommend-stackup",
    "review-routed-board",
    "stress-test-router",
}


@dataclass
class ProviderStreamState:
    """Mutable state accumulated while consuming one provider JSONL stream."""

    final_text: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AIProvider:
    """Provider contract used by the wx runner."""

    provider_id = "base"
    display_name = "AI"
    cli_name = ""
    executable_candidates: Sequence[str] = ()
    model_choices: Sequence[Tuple[str, Optional[str]]] = (("Default", None),)
    effort_choices: Sequence[str] = ("Default",)

    def __init__(self, executable: Optional[str] = None):
        self.executable = executable or self.find_executable()

    @classmethod
    def find_executable(cls) -> Optional[str]:
        path = shutil.which(cls.cli_name)
        if path:
            return path
        for candidate in cls.executable_candidates:
            expanded = os.path.expanduser(os.path.expandvars(candidate))
            if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
                return expanded
        return None

    @property
    def available(self) -> bool:
        return bool(self.executable)

    def availability_text(self) -> str:
        if self.executable:
            return f"{self.display_name} CLI found: {self.executable}"
        return f"{self.display_name} CLI not found."

    def skill_reference(self, name: str) -> str:
        raise NotImplementedError

    def normalize_prompt(self, prompt: str) -> str:
        return prompt

    def build_command(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        allowed_tools: Optional[str] = None,
    ) -> List[str]:
        raise NotImplementedError

    def format_event(
        self, event: Dict[str, Any], state: ProviderStreamState
    ) -> Optional[str]:
        raise NotImplementedError

    def finish(
        self, state: ProviderStreamState, stderr: str, returncode: int
    ) -> Tuple[Optional[str], Optional[str]]:
        if state.error:
            return None, state.error
        if returncode != 0:
            return None, stderr.strip() or f"{self.cli_name} exited with code {returncode}"
        if state.final_text is None:
            return None, stderr.strip() or f"{self.cli_name} produced no final response"
        return state.final_text, None

    def auth_error_hint(self, error: Optional[str]) -> str:
        return ""


def _compact(value: Any, max_len: int = 140) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= max_len else text[:max_len] + "..."


def _claude_tool_summary(name: str, tool_input: Dict[str, Any]) -> str:
    if name == "Bash":
        detail = tool_input.get("description") or tool_input.get("command", "")
    elif name in ("Read", "Write", "Edit"):
        detail = tool_input.get("file_path", "")
    elif name in ("Glob", "Grep"):
        detail = tool_input.get("pattern", "")
    elif name == "WebSearch":
        detail = tool_input.get("query", "")
    elif name == "WebFetch":
        detail = tool_input.get("url", "")
    else:
        try:
            detail = json.dumps(tool_input, ensure_ascii=False)
        except (TypeError, ValueError):
            detail = str(tool_input)
    return f"{name}: {_compact(detail, 120)}"


def _claude_tool_result(block: Dict[str, Any]) -> str:
    content = block.get("content", "")
    if isinstance(content, list):
        content = " ".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    first = str(content).strip().splitlines()
    return _compact(first[0] if first else "(no output)", 120)


def _text_from_content(value: Any) -> str:
    """Extract user-visible text from common provider message shapes."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    return str(value or "")


class ClaudeProvider(AIProvider):
    provider_id = "claude"
    display_name = "Claude Code"
    cli_name = "claude"
    executable_candidates = (
        "~/.claude/local/claude",
        "~/.local/bin/claude",
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        "%APPDATA%/npm/claude.cmd",
    )
    model_choices = (
        ("Default", None),
        ("Fable 5", "claude-fable-5"),
        ("Opus 4.8", "claude-opus-4-8"),
        ("Sonnet 4.6", "claude-sonnet-4-6"),
        ("Haiku 4.5", "claude-haiku-4-5"),
    )
    effort_choices = ("Default", "low", "medium", "high", "xhigh", "max")

    def availability_text(self) -> str:
        if self.executable:
            return f"Claude Code CLI found: {self.executable}"
        return (
            "Claude Code CLI not found. Install Claude Code and make sure "
            "`claude` is on PATH, then reopen this dialog."
        )

    def skill_reference(self, name: str) -> str:
        return f"/{name}"

    def build_command(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        allowed_tools: Optional[str] = None,
    ) -> List[str]:
        if not self.executable:
            raise RuntimeError("Claude Code CLI is not installed")
        command = [
            self.executable,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if allowed_tools:
            command += ["--allowedTools", allowed_tools]
        if model:
            command += ["--model", model]
        if effort:
            command += ["--effort", effort]
        return command

    def format_event(
        self, event: Dict[str, Any], state: ProviderStreamState
    ) -> Optional[str]:
        event_type = event.get("type")
        if event_type == "result":
            if event.get("is_error"):
                state.error = str(event.get("result", "unknown error from Claude"))
            else:
                state.final_text = str(event.get("result", ""))
            return None

        if event_type == "system" and event.get("subtype") == "init":
            model = event.get("model", "unknown")
            version = event.get("claude_code_version", "unknown")
            lines = [
                f"Claude Code {version} | model: {model}",
                f"cwd: {event.get('cwd', '?')}",
            ]
            skills = event.get("skills", [])
            if skills:
                shown = ", ".join(skills[:8]) + (", ..." if len(skills) > 8 else "")
                lines.append(f"skills discovered: {len(skills)} ({shown})")
            return "\n".join(lines) + "\n\n"

        if event_type == "assistant":
            lines = []
            for block in event.get("message", {}).get("content", []):
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text" and block.get("text", "").strip():
                    lines.append(block["text"].rstrip())
                elif block_type == "tool_use":
                    lines.append(
                        "  -> "
                        + _claude_tool_summary(
                            block.get("name", "?"), block.get("input", {})
                        )
                    )
            return "\n".join(lines) + "\n" if lines else None

        if event_type == "user":
            lines = []
            content = event.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        mark = "x" if block.get("is_error") else "ok"
                        lines.append(f"     [{mark}] {_claude_tool_result(block)}")
            return "\n".join(lines) + "\n" if lines else None
        return None

    def auth_error_hint(self, error: Optional[str]) -> str:
        markers = ("invalid api key", "/login", "not logged in", "authentication", "oauth")
        if error and any(marker in error.lower() for marker in markers):
            return (
                "\nClaude Code is installed but not logged in: open a terminal, "
                "run `claude`, complete /login, then retry."
            )
        return ""


class CodexProvider(AIProvider):
    provider_id = "codex"
    display_name = "OpenAI Codex"
    cli_name = "codex"
    executable_candidates = (
        "~/.local/bin/codex",
        "/opt/homebrew/bin/codex",
        "/usr/local/bin/codex",
        "%APPDATA%/npm/codex.cmd",
        "~/AppData/Roaming/npm/codex.cmd",
    )
    # Codex model availability follows the user's installed CLI/account. Keep the
    # plugin future-proof by defaulting to the CLI config while allowing a custom ID.
    model_choices = (("Default", None),)
    effort_choices = ("Default", "minimal", "low", "medium", "high", "xhigh")

    def availability_text(self) -> str:
        if self.executable:
            return f"OpenAI Codex CLI found: {self.executable}"
        return (
            "OpenAI Codex CLI not found. Install Codex CLI, run `codex login`, "
            "and make sure `codex` is on PATH, then reopen this dialog."
        )

    def skill_reference(self, name: str) -> str:
        return f"${name}"

    def normalize_prompt(self, prompt: str) -> str:
        # Existing field-level GUI prompts were written for Claude slash skills.
        # Convert only known skill names; leave filesystem paths such as /tmp intact.
        for name in sorted(KNOWN_SKILLS, key=len, reverse=True):
            prompt = re.sub(rf"(?<![\w$])/{re.escape(name)}\b", f"${name}", prompt)
        return prompt

    def build_command(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        allowed_tools: Optional[str] = None,
    ) -> List[str]:
        del allowed_tools  # Claude-only permission vocabulary.
        if not self.executable:
            raise RuntimeError("OpenAI Codex CLI is not installed")
        command = [
            self.executable,
            "exec",
            "--json",
            "--sandbox",
            "read-only",
        ]
        if model:
            command += ["--model", model]
        if effort:
            command += ["--config", f'model_reasoning_effort="{effort}"']
        command.append(self.normalize_prompt(prompt))
        return command

    def format_event(
        self, event: Dict[str, Any], state: ProviderStreamState
    ) -> Optional[str]:
        event_type = event.get("type", "")

        if event_type == "thread.started":
            thread_id = event.get("thread_id") or event.get("thread", {}).get("id")
            state.metadata["thread_id"] = thread_id
            return f"OpenAI Codex | thread: {thread_id or 'unknown'}\ncwd: {ROOT_DIR}\n\n"

        if event_type in ("error", "turn.failed"):
            error = event.get("message") or event.get("error") or event.get("detail")
            if isinstance(error, dict):
                error = error.get("message") or json.dumps(error, ensure_ascii=False)
            message = str(error or "unknown error from Codex")
            if state.error == message:
                return None
            state.error = message
            return f"[error] {message}\n"

        if event_type == "turn.completed":
            usage = event.get("usage") or event.get("token_usage")
            if isinstance(usage, dict) and usage:
                compact = ", ".join(f"{key}={value}" for key, value in usage.items())
                return f"\n[usage] {compact}\n"
            return None

        if not event_type.startswith("item."):
            return None

        item = event.get("item") or {}
        if not isinstance(item, dict):
            return None
        item_type = item.get("type", "")
        completed = event_type == "item.completed"
        started = event_type == "item.started"

        if item_type == "error" and completed:
            # Codex can emit non-terminal diagnostics as ``item.error`` before
            # continuing with a fallback. Terminal failures arrive as top-level
            # ``error`` / ``turn.failed`` events and set ``state.error``.
            message = item.get("message") or item.get("error") or "unknown diagnostic"
            if isinstance(message, dict):
                message = message.get("message") or json.dumps(message, ensure_ascii=False)
            return f"[warning] {message}\n"

        if item_type in ("agent_message", "message"):
            text = _text_from_content(item.get("text") or item.get("content")).strip()
            if completed and text:
                # Newer Codex streams may distinguish progress commentary from
                # the final answer. Keep showing commentary, but don't let it
                # satisfy the final-result contract.
                if item.get("phase") != "commentary":
                    state.final_text = text
                return text + "\n"
            return None

        if item_type in ("reasoning", "reasoning_summary"):
            # Do not expose private chain-of-thought. Show only an activity marker.
            return "  -> reasoning...\n" if started else None

        if item_type in ("command_execution", "command"):
            command = item.get("command") or item.get("cmd") or item.get("input")
            if started:
                return f"  -> command: {_compact(command)}\n"
            if completed:
                status = item.get("status", "completed")
                exit_code = item.get("exit_code")
                suffix = f", exit={exit_code}" if exit_code is not None else ""
                output = item.get("aggregated_output") or item.get("output") or ""
                first = str(output).strip().splitlines()
                detail = f" | {_compact(first[0], 120)}" if first else ""
                return f"     [{status}{suffix}]{detail}\n"

        if item_type == "web_search":
            query = item.get("query") or item.get("input") or item.get("action")
            return f"  -> web search: {_compact(query)}\n" if started or completed else None

        if item_type in ("file_change", "file_changes"):
            path = item.get("path") or item.get("file_path") or item.get("changes")
            return f"  -> file change: {_compact(path)}\n" if completed else None

        if item_type == "mcp_tool_call":
            server = item.get("server") or item.get("server_name") or "mcp"
            tool = item.get("tool") or item.get("tool_name") or "tool"
            status = item.get("status", "")
            return f"  -> {server}.{tool}{f' [{status}]' if status else ''}\n"

        if item_type in ("plan", "todo_list") and completed:
            return "  -> plan updated\n"
        return None

    def auth_error_hint(self, error: Optional[str]) -> str:
        markers = ("not logged in", "login", "unauthorized", "401", "authentication")
        lowered = error.lower() if error else ""
        if "requires a newer version of codex" in lowered:
            return (
                "\nThis model requires a newer Codex CLI. Update the Codex app or CLI, "
                "restart KiCad, then retry."
            )
        if error and any(marker in lowered for marker in markers):
            return (
                "\nOpenAI Codex is installed but not authenticated: open a terminal, "
                "run `codex login`, then retry."
            )
        return ""


PROVIDER_TYPES = {
    ClaudeProvider.provider_id: ClaudeProvider,
    CodexProvider.provider_id: CodexProvider,
}
PROVIDER_CHOICES = tuple(
    (provider_type.display_name, provider_id)
    for provider_id, provider_type in PROVIDER_TYPES.items()
)

_active_provider_id = os.environ.get("KICAD_ROUTING_AI_PROVIDER", "claude").lower()
if _active_provider_id not in PROVIDER_TYPES:
    _active_provider_id = "claude"


def create_provider(
    provider_id: Optional[str] = None, executable: Optional[str] = None
) -> AIProvider:
    provider_type = PROVIDER_TYPES.get(provider_id or _active_provider_id, ClaudeProvider)
    return provider_type(executable=executable)


def set_active_provider(provider_id: str) -> None:
    global _active_provider_id
    if provider_id not in PROVIDER_TYPES:
        raise ValueError(f"unknown AI provider: {provider_id}")
    _active_provider_id = provider_id


def get_active_provider_id() -> str:
    return _active_provider_id


def choose_initial_provider(preferred: Optional[str] = None) -> str:
    if preferred in PROVIDER_TYPES and PROVIDER_TYPES[preferred].find_executable():
        return str(preferred)
    if _active_provider_id in PROVIDER_TYPES and PROVIDER_TYPES[_active_provider_id].find_executable():
        return _active_provider_id
    for provider_id, provider_type in PROVIDER_TYPES.items():
        if provider_type.find_executable():
            return provider_id
    return preferred if preferred in PROVIDER_TYPES else "claude"


def available_provider_ids() -> Iterable[str]:
    for provider_id, provider_type in PROVIDER_TYPES.items():
        if provider_type.find_executable():
            yield provider_id

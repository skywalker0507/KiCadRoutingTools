"""KiCad Routing Tools - pluggable AI assistant integration.

Compatibility names such as ``ClaudeTab`` and ``ClaudeSkillDialog`` are retained
because other plugin modules already import them, but their implementation is
provider-neutral and supports both Claude Code and OpenAI Codex.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from typing import Optional

import wx

from .ai_providers import (
    PROVIDER_CHOICES,
    AIProvider,
    ClaudeProvider,
    ProviderStreamState,
    choose_initial_provider,
    create_provider,
    get_active_provider_id,
    set_active_provider,
)


PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PLUGIN_DIR)

# Existing field-level analysis prompts pass this Claude permission vocabulary.
# The Claude provider consumes it; the Codex provider intentionally ignores it
# and uses a read-only sandbox for all plugin-driven planning/analysis.
DEFAULT_ALLOWED_TOOLS = "Read,Glob,Grep,Bash,WebSearch"

# Compatibility exports for older code/tests. The live UI reads choices from the
# selected provider instead of these module constants.
MODEL_CHOICES = list(ClaudeProvider.model_choices)
EFFORT_CHOICES = list(ClaudeProvider.effort_choices)


def board_path_for_analysis(board_filename):
    """Snapshot the live pcbnew board for read-only headless analysis."""
    board = None
    try:
        import pcbnew

        board = pcbnew.GetBoard()
    except Exception:
        pass

    if board is not None:
        base = os.path.basename(board_filename) if board_filename else "board.kicad_pcb"
        snapshot = os.path.join(tempfile.gettempdir(), f"kicadrt_analysis_{base}")
        try:
            pcbnew.SaveBoard(snapshot, board)
            return snapshot
        except Exception as exc:
            wx.MessageBox(
                f"Could not snapshot the board for analysis: {exc}\n\n"
                "Falling back to the last saved file - unsaved changes will not "
                "be visible to the analysis.",
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )

    if not board_filename or not os.path.isfile(board_filename):
        wx.MessageBox(
            "Board file not found on disk. Save the board first so the analysis "
            f"sees the current state.\n\nLooked for: {board_filename}",
            "AI Assistant",
            wx.OK | wx.ICON_WARNING,
        )
        return None
    return os.path.abspath(board_filename)


def find_claude():
    """Compatibility helper returning the active (or first available) AI CLI.

    Historical callers use this function to decide whether an "Ask Claude"
    button should be enabled. It now selects the configured provider and falls
    back to another installed provider, allowing Codex-only installations.
    """
    provider_id = choose_initial_provider(get_active_provider_id())
    set_active_provider(provider_id)
    return create_provider(provider_id).executable


def find_codex():
    """Return the Codex CLI path, or None when Codex is not installed."""
    return create_provider("codex").executable


def extract_result_line(text):
    """Return the value of the last RESULT=<value> line, or None."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("RESULT="):
            return line[len("RESULT=") :].strip()
    return None


def auth_error_hint(error):
    """Compatibility wrapper using the currently selected provider."""
    return create_provider(get_active_provider_id()).auth_error_hint(error)


def format_stream_event(event):
    """Compatibility wrapper for formatting a Claude stream-json event."""
    return ClaudeProvider().format_event(event, ProviderStreamState())


class AIProviderRunner:
    """Run one provider CLI on a background thread and stream JSONL to wx."""

    def __init__(self, provider: AIProvider, on_transcript, on_done):
        self.provider = provider
        self.on_transcript = on_transcript
        self.on_done = on_done
        self._process = None
        self._thread = None
        self._cancel_requested = False

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def run(
        self,
        prompt,
        allowed_tools=DEFAULT_ALLOWED_TOOLS,
        model=None,
        effort=None,
    ):
        if self.is_running():
            raise RuntimeError(f"a {self.provider.display_name} run is already in progress")
        command = self.provider.build_command(
            prompt,
            model=model,
            effort=effort,
            allowed_tools=allowed_tools,
        )
        self._cancel_requested = False
        self._thread = threading.Thread(
            target=self._work, args=(command,), daemon=True
        )
        self._thread.start()

    def cancel(self):
        self._cancel_requested = True
        process = self._process
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    def _work(self, command):
        state = ProviderStreamState()
        stderr_chunks = []
        returncode = -1
        try:
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._process = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                bufsize=1,
                **kwargs,
            )
            stderr_thread = threading.Thread(
                target=lambda pipe: stderr_chunks.append(pipe.stderr.read()),
                args=(self._process,),
                daemon=True,
            )
            stderr_thread.start()

            for raw_line in self._process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    # Preserve useful non-JSON diagnostics instead of silently
                    # dropping them; both official CLIs normally emit JSONL.
                    wx.CallAfter(self.on_transcript, line + "\n")
                    continue
                transcript = self.provider.format_event(event, state)
                if transcript:
                    wx.CallAfter(self.on_transcript, transcript)

            self._process.wait()
            returncode = self._process.returncode
            stderr_thread.join(timeout=5)
        except Exception as exc:
            wx.CallAfter(
                self.on_done,
                None,
                f"Failed to launch {self.provider.display_name}: {exc}",
            )
            return
        finally:
            self._process = None

        stderr = "".join(stderr_chunks)
        wx.CallAfter(self._finish, state, stderr, returncode)

    def _finish(self, state, stderr, returncode):
        if self._cancel_requested:
            self.on_done(None, "Cancelled.")
            return
        result_text, error = self.provider.finish(state, stderr, returncode)
        self.on_done(result_text, error)


# Backward-compatible public name.
ClaudeSkillRunner = AIProviderRunner


class ClaudeSkillDialog(wx.Dialog):
    """Provider-neutral modal skill dialog (compatibility class name)."""

    def __init__(
        self,
        parent,
        title,
        prompt,
        claude_path=None,
        allowed_tools=DEFAULT_ALLOWED_TOOLS,
        intro=None,
        model=None,
        effort=None,
        provider_id=None,
    ):
        provider_id = provider_id or choose_initial_provider(get_active_provider_id())
        set_active_provider(provider_id)
        provider = create_provider(provider_id, executable=claude_path)
        display_title = title.replace("Claude", provider.display_name)
        super().__init__(
            parent,
            title=display_title,
            size=(720, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.provider = provider
        self.result_value = None
        self.result_text = None
        self._elapsed_seconds = 0
        self._done = False

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.output_ctrl = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.output_ctrl.SetFont(
            wx.Font(
                10,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        if intro:
            self.output_ctrl.SetValue(
                intro.replace("Claude", provider.display_name) + "\n\n"
            )
        sizer.Add(self.output_ctrl, 1, wx.EXPAND | wx.ALL, 8)

        self.gauge = wx.Gauge(self, range=100)
        sizer.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.elapsed_label = wx.StaticText(self, label="0s")
        button_sizer.Add(self.elapsed_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.action_btn = wx.Button(self, label="Cancel")
        self.action_btn.Bind(wx.EVT_BUTTON, self._on_action)
        button_sizer.Add(self.action_btn, 0)
        sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(sizer)

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._elapsed_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_elapsed_tick, self._elapsed_timer)
        self._elapsed_timer.Start(1000)

        self._runner = AIProviderRunner(provider, self._append, self._on_done)
        if provider.available:
            self._runner.run(
                prompt,
                allowed_tools=allowed_tools,
                model=model,
                effort=effort,
            )
        else:
            wx.CallAfter(self._on_done, None, provider.availability_text())

    def _append(self, text):
        if self:
            self.output_ctrl.AppendText(text)

    def _on_done(self, result_text, error):
        if not self:
            return
        self._done = True
        self._elapsed_timer.Stop()
        self.gauge.SetValue(0)
        self.action_btn.SetLabel("Close")
        if error:
            hint = self.provider.auth_error_hint(error)
            if self.output_ctrl.GetValue().rstrip().endswith(error.strip()):
                appended = hint
            else:
                appended = f"\n{error}{hint}"
            if appended:
                self.output_ctrl.AppendText(appended + "\n")
            return

        self.result_text = result_text
        self.result_value = extract_result_line(result_text)
        self.output_ctrl.AppendText(
            f"\n--- done in {self.elapsed_label.GetLabel()}"
            + (
                f" | RESULT={self.result_value}"
                if self.result_value is not None
                else " | no RESULT= line found"
            )
            + " ---\n"
        )

    def _on_action(self, _event):
        if self._done:
            self.EndModal(wx.ID_OK)
        else:
            self._runner.cancel()
            self.action_btn.Disable()

    def _on_close(self, _event):
        if not self._done:
            self._runner.cancel()
        self.EndModal(wx.ID_CANCEL)

    def _on_elapsed_tick(self, _event):
        if not self:
            return
        self._elapsed_seconds += 1
        minutes, seconds = divmod(self._elapsed_seconds, 60)
        self.elapsed_label.SetLabel(
            f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
        )
        self.gauge.Pulse()


class ClaudeTab(wx.Panel):
    """AI Assistant tab supporting Claude Code and OpenAI Codex.

    The historical class/attribute name is intentionally kept so existing plugin
    tabs and saved settings remain compatible.
    """

    def __init__(self, parent, board_filename, log_callback=None, routing_dialog=None):
        super().__init__(parent)
        self.board_filename = board_filename
        self.log_callback = log_callback
        self.routing_dialog = routing_dialog
        self._elapsed_timer = wx.Timer(self)
        self._elapsed_seconds = 0
        self.Bind(wx.EVT_TIMER, self._on_elapsed_tick, self._elapsed_timer)
        self._provider_id = choose_initial_provider(get_active_provider_id())
        set_active_provider(self._provider_id)
        self._provider = create_provider(self._provider_id)
        self._runner = None
        self._pending_kind = None
        self._plan_steps = []
        self._plan_executor = None
        self._model_values = []
        if self._provider.available:
            self._runner = AIProviderRunner(
                self._provider, self._append_transcript, self._on_done
            )
        self._create_ui()
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        wx.CallAfter(self._rename_legacy_ai_labels)

    # ---------------------------------------------------------------- lifecycle

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self.shutdown()
        event.Skip()

    def shutdown(self):
        if self._runner is not None:
            self._runner.cancel()
        if self._plan_executor is not None:
            self._plan_executor.stop()
        self._elapsed_timer.Stop()

    # ---------------------------------------------------------------------- UI

    def _create_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)

        steps_box = wx.StaticBox(self, label="Planned Steps")
        steps_sizer = wx.StaticBoxSizer(steps_box, wx.VERTICAL)
        self.plan_list = wx.CheckListBox(self, choices=[])
        self.plan_list.SetToolTip(
            "The routing plan from the selected AI provider. Check the steps to "
            "run and review each step's parameters on its native tab."
        )
        steps_sizer.Add(self.plan_list, 1, wx.EXPAND | wx.ALL, 3)
        top_sizer.Add(steps_sizer, 1, wx.EXPAND | wx.RIGHT, 8)

        self.provider_box = wx.StaticBox(self, label="AI Assistant")
        controls = wx.StaticBoxSizer(self.provider_box, wx.VERTICAL)

        selection_grid = wx.FlexGridSizer(cols=2, hgap=5, vgap=5)
        selection_grid.AddGrowableCol(1)

        selection_grid.Add(
            wx.StaticText(self, label="Provider:"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.provider_choice = wx.Choice(
            self, choices=[label for label, _value in PROVIDER_CHOICES]
        )
        selected_index = next(
            (
                index
                for index, (_label, value) in enumerate(PROVIDER_CHOICES)
                if value == self._provider_id
            ),
            0,
        )
        self.provider_choice.SetSelection(selected_index)
        self.provider_choice.SetToolTip(
            "Choose the CLI that performs planning and analysis. Routing itself is "
            "still executed by the plugin's local routing engines."
        )
        self.provider_choice.Bind(wx.EVT_CHOICE, self._on_provider_changed)
        selection_grid.Add(self.provider_choice, 0, wx.EXPAND)

        selection_grid.Add(
            wx.StaticText(self, label="Model:"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.model_choice = wx.ComboBox(self, style=wx.CB_DROPDOWN)
        self.model_choice.SetToolTip(
            "Default uses the selected CLI's configured model. A custom model ID may "
            "be entered when supported by that provider."
        )
        selection_grid.Add(self.model_choice, 0, wx.EXPAND)

        selection_grid.Add(
            wx.StaticText(self, label="Effort:"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.effort_choice = wx.Choice(self)
        selection_grid.Add(self.effort_choice, 0, wx.EXPAND)
        controls.Add(selection_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self.status_label = wx.StaticText(self, label="")
        self.status_label.Wrap(300)
        controls.Add(self.status_label, 0, wx.ALL, 5)

        self.plan_btn = wx.Button(self, label="Plan Routing")
        self.plan_btn.SetFont(self.plan_btn.GetFont().Bold())
        self.plan_btn.SetToolTip(
            "Run the provider's plan-pcb-routing skill in plugin-compatible plan "
            "mode, populate the native tabs, then review and run selected steps."
        )
        self.plan_btn.Bind(wx.EVT_BUTTON, self._on_plan)
        controls.Add(self.plan_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.cancel_btn = wx.Button(self, label="Cancel")
        self.cancel_btn.SetToolTip("Cancel the running AI analysis")
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.cancel_btn.Disable()
        controls.Add(self.cancel_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        controls.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.run_plan_btn = wx.Button(self, label="Run Selected Steps")
        self.run_plan_btn.SetToolTip(
            "Execute checked plan steps through the plugin's local routing tabs."
        )
        self.run_plan_btn.Bind(wx.EVT_BUTTON, self._on_run_selected)
        self.run_plan_btn.Disable()
        controls.Add(self.run_plan_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.stop_plan_btn = wx.Button(self, label="Stop")
        self.stop_plan_btn.SetToolTip("Stop after the current routing step finishes")
        self.stop_plan_btn.Bind(wx.EVT_BUTTON, self._on_stop_plan)
        self.stop_plan_btn.Disable()
        controls.Add(self.stop_plan_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        controls.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.review_btn = wx.Button(self, label="Review Routed Board")
        self.review_btn.SetToolTip(
            "Run read-only post-route DRC, connectivity, orphan, matching, return-path, "
            "and differential-pair review."
        )
        self.review_btn.Bind(wx.EVT_BUTTON, self._on_review)
        controls.Add(self.review_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.diagnose_btn = wx.Button(self, label="Diagnose Routing Failures")
        self.diagnose_btn.SetToolTip(
            "Analyze the board and this session's routing log, then recommend one "
            "targeted retry without modifying the board."
        )
        self.diagnose_btn.Bind(wx.EVT_BUTTON, self._on_diagnose)
        controls.Add(self.diagnose_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self.elapsed_label = wx.StaticText(self, label="")
        controls.Add(self.elapsed_label, 0, wx.LEFT | wx.RIGHT, 5)
        self.gauge = wx.Gauge(self, range=100)
        controls.Add(self.gauge, 0, wx.EXPAND | wx.ALL, 5)
        controls.AddStretchSpacer(1)
        top_sizer.Add(controls, 0, wx.EXPAND)
        sizer.Add(top_sizer, 1, wx.EXPAND | wx.ALL, 8)

        parsed_sizer = wx.BoxSizer(wx.HORIZONTAL)
        parsed_sizer.Add(
            wx.StaticText(self, label="Parsed result:"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            5,
        )
        self.parsed_ctrl = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.parsed_ctrl.SetToolTip(
            "The machine-readable RESULT= line used to populate GUI fields."
        )
        parsed_sizer.Add(self.parsed_ctrl, 1, wx.EXPAND)
        sizer.Add(parsed_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self.output_ctrl = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2
        )
        self.output_ctrl.SetFont(
            wx.Font(
                10,
                wx.FONTFAMILY_TELETYPE,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        sizer.Add(self.output_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.SetSizer(sizer)
        self._refresh_provider_controls()

    def _rename_legacy_ai_labels(self):
        """Rename notebook/buttons created by older modules without touching APIs."""
        notebook = self.GetParent()
        if isinstance(notebook, wx.Notebook):
            for index in range(notebook.GetPageCount()):
                if notebook.GetPage(index) is self or notebook.GetPageText(index) == "Claude":
                    notebook.SetPageText(index, "AI")
        root = self.routing_dialog
        if root is None:
            return

        def walk(window):
            for child in window.GetChildren():
                if isinstance(child, wx.Button) and child.GetLabel() == "Ask Claude":
                    child.SetLabel("Ask AI")
                    tooltip = child.GetToolTipText()
                    if tooltip:
                        child.SetToolTip(tooltip.replace("Claude", "the selected AI provider"))
                walk(child)

        walk(root)

    # --------------------------------------------------------- provider/model

    def _selected_provider_id(self):
        index = self.provider_choice.GetSelection()
        return PROVIDER_CHOICES[index][1] if index >= 0 else "claude"

    def _on_provider_changed(self, _event):
        if self._runner is not None and self._runner.is_running():
            wx.MessageBox(
                "Cancel the current AI run before changing provider.",
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )
            self.set_provider_value(self._provider_id)
            return
        self.set_provider_value(self._selected_provider_id())

    def _refresh_provider_controls(self, model_value=None, effort_value=None):
        self._model_values = list(self._provider.model_choices)
        self.model_choice.SetItems([label for label, _value in self._model_values])
        self.set_model_value(model_value)

        self.effort_choice.SetItems(list(self._provider.effort_choices))
        self.set_effort_value(effort_value)
        self.effort_choice.SetToolTip(
            f"Reasoning effort for {self._provider.display_name}. Default uses CLI configuration."
        )
        self.status_label.SetLabel(self._provider.availability_text())
        self.status_label.Wrap(300)
        self._update_action_enablement()
        self.Layout()

    def _update_action_enablement(self):
        available = self._provider.available
        running = self._runner is not None and self._runner.is_running()
        self.plan_btn.Enable(available and self.routing_dialog is not None and not running)
        self.review_btn.Enable(available and not running)
        self.diagnose_btn.Enable(available and not running)
        self.run_plan_btn.Enable(
            available and bool(self._plan_steps) and self._plan_executor is None and not running
        )

    def get_provider_value(self):
        return self._provider_id

    def set_provider_value(self, value):
        provider_ids = [provider_id for _label, provider_id in PROVIDER_CHOICES]
        if value not in provider_ids:
            value = choose_initial_provider("claude")
        old_model = self.get_model_value() if hasattr(self, "model_choice") else None
        old_effort = self.get_effort_value() if hasattr(self, "effort_choice") else None
        self._provider_id = value
        set_active_provider(value)
        self._provider = create_provider(value)
        self._runner = (
            AIProviderRunner(self._provider, self._append_transcript, self._on_done)
            if self._provider.available
            else None
        )
        if hasattr(self, "provider_choice"):
            self.provider_choice.SetSelection(provider_ids.index(value))
            self._refresh_provider_controls(old_model, old_effort)
        self._log(f"AI provider: {self._provider.display_name}")

    def get_model_value(self):
        if not hasattr(self, "model_choice"):
            return None
        text = self.model_choice.GetValue().strip()
        if not text or text == "Default":
            return None
        for label, value in self._model_values:
            if text == label:
                return value
        return text

    def set_model_value(self, value):
        if not hasattr(self, "model_choice"):
            return
        if not value:
            self.model_choice.SetValue("Default")
            return
        for label, candidate in self._model_values:
            if value == candidate or value == label:
                self.model_choice.SetValue(label)
                return
        self.model_choice.SetValue(str(value))

    def get_effort_value(self):
        if not hasattr(self, "effort_choice") or self.effort_choice.GetSelection() < 0:
            return None
        value = self.effort_choice.GetStringSelection()
        return None if value == "Default" else value

    def set_effort_value(self, value):
        if not hasattr(self, "effort_choice"):
            return
        choices = list(self._provider.effort_choices)
        selected = value if value in choices else "Default"
        self.effort_choice.SetSelection(choices.index(selected))

    # -------------------------------------------------------------- persistence

    def get_plan_state(self):
        return {
            "provider": self.get_provider_value(),
            "model": self.get_model_value(),
            "effort": self.get_effort_value(),
            "output": self.output_ctrl.GetValue(),
            "steps": self._plan_steps,
            "items": [
                self.plan_list.GetString(index)
                for index in range(self.plan_list.GetCount())
            ],
            "checked": list(self.plan_list.GetCheckedItems()),
        }

    def restore_plan_state(self, state):
        if not isinstance(state, dict):
            return
        if state.get("provider"):
            self.set_provider_value(state["provider"])
        if "model" in state:
            self.set_model_value(state.get("model"))
        if "effort" in state:
            self.set_effort_value(state.get("effort"))
        if state.get("output"):
            self.output_ctrl.SetValue(state["output"])
        steps = state.get("steps") or []
        items = state.get("items") or []
        if steps and len(items) == len(steps):
            self._plan_steps = steps
            self.plan_list.Set(items)
            self.plan_list.SetCheckedItems(
                [
                    index
                    for index in state.get("checked", [])
                    if 0 <= index < len(steps)
                ]
            )
        self._update_action_enablement()

    # ------------------------------------------------------------------ running

    def _board_path_or_warn(self):
        return board_path_for_analysis(self.board_filename)

    def _skill(self, name):
        return self._provider.skill_reference(name)

    def _start_run(self, prompt, kind, intro):
        if self._runner is None:
            wx.MessageBox(
                self._provider.availability_text(),
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self._pending_kind = kind
        self.plan_btn.Disable()
        self.review_btn.Disable()
        self.diagnose_btn.Disable()
        self.run_plan_btn.Disable()
        self.provider_choice.Disable()
        self.cancel_btn.Enable()
        self.parsed_ctrl.SetValue("")
        if kind == "plan":
            self._plan_steps = []
            self.plan_list.Set([])
            self.output_ctrl.SetValue(intro + "\n\n")
        else:
            if self.output_ctrl.GetValue().strip():
                self.output_ctrl.AppendText("\n" + "=" * 60 + "\n\n")
            self.output_ctrl.AppendText(intro + "\n\n")
        self._elapsed_seconds = 0
        self.elapsed_label.SetLabel("0s")
        self._elapsed_timer.Start(1000)
        model = self.get_model_value()
        effort = self.get_effort_value()
        self._log(
            f"{self._provider.display_name}: {intro.splitlines()[0]}"
            + (f" | model={model}" if model else "")
            + (f" | effort={effort}" if effort else "")
        )
        self._runner.run(prompt, model=model, effort=effort)

    def _on_review(self, _event):
        if self._runner is None or self._runner.is_running():
            return
        board = self._board_path_or_warn()
        if board is None:
            return
        prompt = (
            f"{self._skill('review-routed-board')} {board} — analysis only; do not "
            "modify files. End with exactly RESULT=PASS or RESULT=FAIL."
        )
        self._start_run(
            prompt,
            "review",
            f"Running {self._skill('review-routed-board')} on {os.path.basename(board)} ...\n"
            "(DRC + connectivity + board review; typically a few minutes)",
        )

    def _on_diagnose(self, _event):
        if self._runner is None or self._runner.is_running():
            return
        board = self._board_path_or_warn()
        if board is None:
            return
        log_text = ""
        if self.routing_dialog is not None and hasattr(self.routing_dialog, "log_text"):
            log_text = self.routing_dialog.log_text.GetValue()
        if not log_text.strip():
            wx.MessageBox(
                "The Log tab is empty. Run a routing operation first.",
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )
            return
        descriptor, log_path = tempfile.mkstemp(
            prefix="kicadrt_gui_log_", suffix=".txt"
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", errors="replace") as handle:
            handle.write(log_text)
        prompt = (
            f"{self._skill('diagnose-routing-failures')} {board} — the routing log "
            f"is at {log_path}. Analysis only; do not modify files. End with exactly "
            "RESULT=<one-line recommended fix, or 'no failures found'>."
        )
        self._start_run(
            prompt,
            "diagnose",
            f"Running {self._skill('diagnose-routing-failures')} on "
            f"{os.path.basename(board)} + the Log tab ...",
        )

    def _on_plan(self, _event):
        if self._runner is None or self._runner.is_running():
            return
        if self._plan_executor is not None:
            wx.MessageBox(
                "A plan is currently executing. Stop it first.",
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )
            return
        board = self._board_path_or_warn()
        if board is None:
            return
        from .claude_plan import PLAN_RESULT_SCHEMA

        prompt = (
            f"{self._skill('plan-pcb-routing')} {board} — plugin-compatible plan "
            "mode: analyze and plan only; do not execute routing commands or modify "
            f"files. End with exactly one line of the form {PLAN_RESULT_SCHEMA}"
        )
        self._start_run(
            prompt,
            "plan",
            f"Running {self._skill('plan-pcb-routing')} on "
            f"{os.path.basename(board)} ...\n"
            "(board analysis + datasheet lookups; typically several minutes)",
        )

    def _append_transcript(self, text):
        if self:
            self.output_ctrl.AppendText(text)

    def _on_done(self, result_text, error):
        if not self:
            return
        self._elapsed_timer.Stop()
        self.gauge.SetValue(0)
        self.provider_choice.Enable()
        self.cancel_btn.Disable()
        kind, self._pending_kind = self._pending_kind, None

        if error:
            hint = self._provider.auth_error_hint(error)
            if self.output_ctrl.GetValue().rstrip().endswith(error.strip()):
                appended = hint
            else:
                appended = f"\n{error}{hint}"
            if appended:
                self.output_ctrl.AppendText(appended + "\n")
            self._log(f"{self._provider.display_name}: {error}")
            self._update_action_enablement()
            return

        self.output_ctrl.AppendText(
            f"\n--- done in {self.elapsed_label.GetLabel()} ---\n"
        )
        parsed = extract_result_line(result_text)
        if parsed is not None:
            self.parsed_ctrl.SetValue(
                parsed if len(parsed) < 200 else parsed[:200] + "..."
            )
            self._log(
                f"{self._provider.display_name}: done in {self._elapsed_seconds}s"
            )
        else:
            self.parsed_ctrl.SetValue("(no RESULT= line found)")
            self._log(
                f"{self._provider.display_name}: done in {self._elapsed_seconds}s, "
                "no RESULT= line"
            )
        if kind == "plan":
            self._handle_plan_result(parsed)
        self._update_action_enablement()

    # ---------------------------------------------------------------- planning

    def _handle_plan_result(self, value):
        from .claude_plan import (
            apply_step_params,
            apply_step_selection,
            parse_plan_result,
            step_label,
        )

        if value is None:
            self.output_ctrl.AppendText(
                "\nNo RESULT= plan line found - nothing to apply.\n"
            )
            return
        steps, errors = parse_plan_result(value)
        for message in errors:
            self.output_ctrl.AppendText(f"plan: {message}\n")
            self._log(f"AI plan: {message}")
        if steps is None:
            self.output_ctrl.AppendText("\nPlan was unusable - nothing applied.\n")
            return

        self._plan_steps = steps
        self.plan_list.Set(
            [step_label(index + 1, step) for index, step in enumerate(steps)]
        )
        self.plan_list.SetCheckedItems(range(len(steps)))
        notes = []
        for step in steps:
            try:
                notes += apply_step_params(step, self.routing_dialog)
                notes += apply_step_selection(step, self.routing_dialog)
            except Exception as exc:
                notes.append(f"applying {step['action']}: {exc}")
        for note in notes:
            self.output_ctrl.AppendText(f"plan: {note}\n")
            self._log(f"AI plan: {note}")
        self.output_ctrl.AppendText(
            f"\nPlan loaded: {len(steps)} step(s). Parameters were applied to the "
            "tabs - review them, uncheck unwanted steps, then press 'Run Selected "
            "Steps'.\n"
        )
        self.run_plan_btn.Enable()
        self._log(f"AI plan: {len(steps)} steps loaded")

    def _on_run_selected(self, _event):
        from .claude_plan import PlanExecutor

        if self._plan_executor is not None or not self._plan_steps:
            return
        if self._runner is not None and self._runner.is_running():
            return
        indices = list(self.plan_list.GetCheckedItems())
        if not indices:
            wx.MessageBox(
                "No steps are checked.",
                "AI Assistant",
                wx.OK | wx.ICON_WARNING,
            )
            return
        self.run_plan_btn.Disable()
        self.plan_btn.Disable()
        self.stop_plan_btn.Enable()
        self._plan_executor = PlanExecutor(
            self.routing_dialog,
            self._plan_steps,
            indices,
            on_status=self._on_plan_step_status,
            on_finished=self._on_plan_finished,
            log=self._log,
        )
        self._plan_executor.start()

    def _on_stop_plan(self, _event):
        if self._plan_executor is not None:
            self._plan_executor.stop()
            self.stop_plan_btn.Disable()
            self._log("AI plan: stop requested (after current step)")

    def _on_plan_step_status(self, index, status):
        if not self:
            return
        from .claude_plan import step_label

        mark = {"running": "> ", "done": "[ok] ", "failed": "[FAIL] "}[status]
        self.plan_list.SetString(
            index, mark + step_label(index + 1, self._plan_steps[index])
        )
        if status == "done":
            self.plan_list.Check(index, False)

    def _on_plan_finished(self, completed, aborted_reason):
        self._plan_executor = None
        if not self:
            return
        self.stop_plan_btn.Disable()
        self._update_action_enablement()
        if aborted_reason:
            message = f"AI plan: stopped after {completed} step(s): {aborted_reason}"
        else:
            message = f"AI plan: all {completed} selected step(s) completed"
        self.output_ctrl.AppendText(f"\n{message}\n")
        self._log(message)

    # ---------------------------------------------------------------- helpers

    def _on_cancel(self, _event):
        if self._runner is not None:
            self._runner.cancel()
        self.cancel_btn.Disable()
        self._log(f"{self._provider.display_name}: cancel requested")

    def _on_elapsed_tick(self, _event):
        if not self:
            return
        self._elapsed_seconds += 1
        minutes, seconds = divmod(self._elapsed_seconds, 60)
        self.elapsed_label.SetLabel(
            f"{minutes}m {seconds:02d}s" if minutes else f"{seconds}s"
        )
        self.gauge.Pulse()

    def _log(self, message):
        if self.log_callback:
            self.log_callback(message)


# New provider-neutral aliases for new code while preserving old imports.
AISkillRunner = AIProviderRunner
AISkillDialog = ClaudeSkillDialog
AITab = ClaudeTab

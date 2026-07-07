"""Unit tests for the provider layer; does not require wxPython or KiCad."""

import unittest

from kicad_routing_plugin.ai_providers import (
    KNOWN_SKILLS,
    PROVIDER_TYPES,
    ClaudeProvider,
    CodexProvider,
    ProviderStreamState,
    create_provider,
)


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_exposes_both_plugin_providers(self):
        self.assertEqual(set(PROVIDER_TYPES), {"claude", "codex"})
        self.assertIsInstance(
            create_provider("claude", executable="claude"), ClaudeProvider
        )
        self.assertIsInstance(
            create_provider("codex", executable="codex"), CodexProvider
        )

    def test_plane_mapping_skill_is_known_to_prompt_converter(self):
        self.assertIn("recommend-plane-mappings", KNOWN_SKILLS)


class ClaudeProviderTests(unittest.TestCase):
    def test_build_command_preserves_existing_cli_contract(self):
        provider = ClaudeProvider(executable="/tools/claude")
        command = provider.build_command(
            "/review-routed-board board.kicad_pcb",
            model="claude-sonnet-4-6",
            effort="high",
            allowed_tools="Read,Bash",
        )
        self.assertEqual(
            command[0:3],
            ["/tools/claude", "-p", "/review-routed-board board.kicad_pcb"],
        )
        self.assertIn("stream-json", command)
        self.assertIn("--allowedTools", command)
        self.assertIn("claude-sonnet-4-6", command)
        self.assertEqual(command[-2:], ["--effort", "high"])

    def test_result_event_becomes_final_text(self):
        provider = ClaudeProvider(executable="claude")
        state = ProviderStreamState()
        transcript = provider.format_event(
            {"type": "result", "is_error": False, "result": "report\nRESULT=PASS"},
            state,
        )
        self.assertIsNone(transcript)
        self.assertEqual(state.final_text, "report\nRESULT=PASS")
        result, error = provider.finish(state, "", 0)
        self.assertEqual(result, "report\nRESULT=PASS")
        self.assertIsNone(error)


class CodexProviderTests(unittest.TestCase):
    def test_build_command_uses_read_only_json_exec(self):
        provider = CodexProvider(executable="/tools/codex")
        command = provider.build_command(
            "/plan-pcb-routing board.kicad_pcb and inspect /tmp/router.log",
            model="gpt-test",
            effort="xhigh",
        )
        self.assertEqual(command[:3], ["/tools/codex", "exec", "--json"])
        self.assertIn("read-only", command)
        self.assertIn("--search", command)
        self.assertIn("gpt-test", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertIn("$plan-pcb-routing", command[-1])
        self.assertIn("/tmp/router.log", command[-1])

    def test_only_known_slash_skills_are_rewritten(self):
        provider = CodexProvider(executable="codex")
        prompt = provider.normalize_prompt(
            "/review-routed-board board.kicad_pcb; read /tmp/run.txt and "
            "/unknown-command"
        )
        self.assertTrue(prompt.startswith("$review-routed-board"))
        self.assertIn("/tmp/run.txt", prompt)
        self.assertIn("/unknown-command", prompt)

    def test_plane_mapping_prompt_is_rewritten(self):
        provider = CodexProvider(executable="codex")
        prompt = provider.normalize_prompt(
            "/recommend-plane-mappings board.kicad_pcb"
        )
        self.assertEqual(prompt, "$recommend-plane-mappings board.kicad_pcb")

    def test_completed_agent_message_is_final_text(self):
        provider = CodexProvider(executable="codex")
        state = ProviderStreamState()
        transcript = provider.format_event(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "analysis\nRESULT=PASS"},
            },
            state,
        )
        self.assertEqual(transcript, "analysis\nRESULT=PASS\n")
        self.assertEqual(state.final_text, "analysis\nRESULT=PASS")
        result, error = provider.finish(state, "", 0)
        self.assertEqual(result, "analysis\nRESULT=PASS")
        self.assertIsNone(error)

    def test_reasoning_content_is_not_exposed(self):
        provider = CodexProvider(executable="codex")
        state = ProviderStreamState()
        transcript = provider.format_event(
            {
                "type": "item.started",
                "item": {"type": "reasoning", "text": "private reasoning"},
            },
            state,
        )
        self.assertEqual(transcript, "  -> reasoning...\n")
        self.assertNotIn("private reasoning", transcript)

    def test_turn_failure_is_reported(self):
        provider = CodexProvider(executable="codex")
        state = ProviderStreamState()
        transcript = provider.format_event(
            {"type": "turn.failed", "error": {"message": "authentication required"}},
            state,
        )
        self.assertIn("authentication required", transcript)
        result, error = provider.finish(state, "", 1)
        self.assertIsNone(result)
        self.assertEqual(error, "authentication required")
        self.assertIn("codex login", provider.auth_error_hint(error))


if __name__ == "__main__":
    unittest.main()

"""Tests for the brain engine. Run from the vault root:

    python3 -m unittest discover -s scripts/tests -v

Each run copies the vault to a temporary folder and works there, so the real
vault is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="brain-test-"))
VAULT = TMP / "vault"
shutil.copytree(SRC, VAULT, symlinks=True, ignore=shutil.ignore_patterns(".git", ".brain", "__pycache__", "audit-log.jsonl"))
os.environ["BRAIN_VAULT"] = str(VAULT)
os.environ["BRAIN_AGENT"] = "unittest"
sys.path.insert(0, str(VAULT / "scripts"))

from brainlib import audit, context, health, policy, writer  # noqa: E402
from brainlib.facts import Fact, overlaps, parse_facts  # noqa: E402
from brainlib.hermes import parse_tool_calls  # noqa: E402
from brainlib.index import open_index  # noqa: E402
from brainlib.tools import by_name, openai_schema  # noqa: E402
from brainlib.vault import parse_frontmatter, set_frontmatter_fields, slugify  # noqa: E402

for d in ("00-inbox", "20-people", "40-drafts", "60-journal", "90-archive"):
    (VAULT / d).mkdir(exist_ok=True)
writer.create_note("project", "Motor controller", "Brushless motor controller board for the rover.")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def run_hook(name: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(VAULT / ".claude" / "hooks" / name)],
                          input=json.dumps(payload), capture_output=True, text=True)


class Frontmatter(unittest.TestCase):
    def test_round_trip_keeps_other_lines(self):
        text = "---\ntype: note\ntags:\n  - a\n  - b\nsummary: x\n---\n# T\nbody\n"
        fm, body, had = parse_frontmatter(text)
        self.assertTrue(had)
        self.assertEqual(fm["tags"], ["a", "b"])
        out = set_frontmatter_fields(text, {"summary": "new: value", "updated": "2026-11-09"})
        fm2, body2, _ = parse_frontmatter(out)
        self.assertEqual(fm2["summary"], "new: value")
        self.assertEqual(fm2["tags"], ["a", "b"])
        self.assertEqual(fm2["updated"], "2026-11-09")
        self.assertEqual(body2, body)

    def test_slugify(self):
        self.assertEqual(slugify("Dana's Motor-Controller v2!"), "danas-motor-controller-v2")


class Policy(unittest.TestCase):
    def test_secrets(self):
        for s in ["sk-ant-abcdefghijklmnopqrstuvwxyz123", "AKIAABCDEFGHIJKLMNOP", "4111 1111 1111 1111",
                  "password: hunter2abc", "ghp_" + "a" * 36, "-----BEGIN RSA PRIVATE KEY-----"]:
            self.assertIsNotNone(policy.find_secret(s), s)
        for s in ["api_key=api_key_from_env(name)", "date 2026-11-09", "phone 555-123-4567",
                  "order 2026 1109 0851 23"]:
            self.assertIsNone(policy.find_secret(s), s)

    def test_commands(self):
        root = VAULT
        blocked = ["rm a.md", "ls && rm -rf x", "git rm a.md", "git push --force", "git reset --hard",
                   "sudo ls", "curl http://x", "find . -delete", "echo x > .claude/settings.json",
                   "mv 10-notes/a.md /home/elsewhere/", "git clean -fd", "find . -name x -exec rm {} ;",
                   "ls | xargs -n 1 rm", "env FOO=1 rm a", "bash -c 'rm a.md'", "git -C . rm a.md",
                   "git push origin +main", "timeout 5 curl x", "sed -i s/a/b/ .claude/hooks/guard.py",
                   "cp x scripts/brainlib/policy.py"]
        for c in blocked:
            self.assertIsNotNone(policy.check_command(c, str(root), root), c)
        allowed = ["ls", "git mv 10-notes/a.md 90-archive/a.md", f"mv {root}/10-notes/a.md {root}/90-archive/",
                   "cat .claude/settings.json", "python3 scripts/brain.py search firmware", "grep -r rmdir .",
                   "echo rm is blocked", "git log --format=%H -- rm.md", "grep curl README.md",
                   "find . -name '*.md'", "sed -n 1,5p .claude/hooks/guard.py"]
        for c in allowed:
            self.assertIsNone(policy.check_command(c, str(root), root), c)

    def test_protected_paths(self):
        for p in [".claude/hooks/guard.py", ".claude/settings.json", "scripts/brainlib/policy.py",
                  ".githooks/pre-commit", "CLAUDE.local.md", ".env"]:
            self.assertIsNotNone(policy.check_write_path(str(VAULT / p)), p)
        self.assertIsNone(policy.check_write_path(str(VAULT / "10-notes" / "a.md")))


class Facts(unittest.TestCase):
    def test_parse_and_as_of(self):
        facts = parse_facts("## Facts\n- A | works at | X | 2023 | 2025\n- A | works at | Y | 2025\n- bad line\n")
        self.assertEqual(len(facts), 2)
        self.assertTrue(facts[0].true_on("2024-06"))
        self.assertFalse(facts[0].true_on("2025-03"))
        self.assertTrue(facts[1].true_on("2026-01-01"))

    def test_handover_is_not_conflict(self):
        a, b = Fact("A", "p", "X", "2023", "2025-01"), Fact("A", "p", "Y", "2025-01")
        self.assertFalse(overlaps(a, b))
        self.assertTrue(overlaps(Fact("A", "p", "X", "2023"), b))


class Writes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = by_name()
        cls.t["brain_create_note"].call({
            "type": "person", "title": "Dana Reyes", "summary": "Robotics engineer who reviews motor designs.",
            "sections": {"Facts": "- Dana Reyes | works at | Acme | 2024 |"}, "related": ["how-this-vault-works"]})

    def test_create_registers_in_index(self):
        self.assertIn("[[dana-reyes]]", (VAULT / "_meta" / "index.md").read_text())

    def test_duplicate_refused(self):
        out = self.t["brain_create_note"].call({"type": "note", "title": "Dana Reyes", "summary": "x"})
        self.assertTrue(out.startswith("Refused"), out)

    def test_policy_on_writes(self):
        out = self.t["brain_capture"].call({"text": "my key AKIAABCDEFGHIJKLMNOP"})
        self.assertTrue(out.startswith("Refused"), out)
        out = self.t["brain_capture"].call({"text": "dash — here"})
        self.assertTrue(out.startswith("Refused"), out)

    def test_unknown_related_refused(self):
        out = self.t["brain_create_note"].call({"type": "note", "title": "Z", "summary": "z", "related": ["nope"]})
        self.assertIn("not found", out)

    def test_decision_logged_newest_first(self):
        self.t["brain_log_decision"].call({"title": "Pick MCU", "decision": "Use STM32G4.", "why": "Timers."})
        log = (VAULT / "50-decisions" / "decisions.md").read_text()
        first = [l for l in log.splitlines() if l.startswith("- 20")][0]
        self.assertIn("pick-mcu", first)

    def test_update_and_supersede(self):
        self.t["brain_create_note"].call({"type": "note", "title": "Old idea", "summary": "Old."})
        self.t["brain_create_note"].call({"type": "note", "title": "New idea", "summary": "New."})
        out = self.t["brain_update_note"].call({"note": "old-idea", "set": {"superseded_by": "new-idea"}})
        self.assertIn("updated", out)
        text = (VAULT / "10-notes" / "old-idea.md").read_text()
        self.assertIn("status: superseded", text)
        self.assertIn('superseded_by: "[[new-idea]]"', text)

    def test_archive_moves_never_deletes(self):
        self.t["brain_create_note"].call({"type": "note", "title": "Retire me", "summary": "Bye."})
        self.t["brain_archive"].call({"note": "retire-me", "reason": "test"})
        self.assertFalse((VAULT / "10-notes" / "retire-me.md").exists())
        self.assertIn("status: archived", (VAULT / "90-archive" / "10-notes" / "retire-me.md").read_text())

    def test_journal_appends(self):
        writer.journal("first")
        writer.journal("second")
        text = next((VAULT / "60-journal").glob("20*.md")).read_text()
        self.assertLess(text.index("first"), text.index("second"))

    def test_audit_chain(self):
        ok, msg, n = audit.verify()
        self.assertTrue(ok, msg)
        self.assertGreater(n, 0)
        log = audit.log_path()
        lines = log.read_text().splitlines()
        tampered = lines[:]
        tampered[0] = tampered[0].replace("unittest", "someone")
        log.write_text("\n".join(tampered) + "\n")
        try:
            self.assertFalse(audit.verify()[0])
        finally:
            log.write_text("\n".join(lines) + "\n")


class SearchAndRecall(unittest.TestCase):
    def test_search_ranks_title_match_first(self):
        idx = open_index()
        try:
            hits = idx.search("motor controller")
        finally:
            idx.close()
        self.assertEqual(hits[0].stem, "motor-controller")

    def test_strict_recall_ignores_unrelated(self):
        self.assertEqual(context.recall("what is the weather like today"), "")
        self.assertIn("[[motor-controller]]", context.recall("status of the motor controller"))

    def test_wake_up_within_budget(self):
        pack = context.wake_up()
        self.assertLessEqual(len(pack), context.WAKE_UP_BUDGET + 40)
        self.assertIn("Memory protocol", pack)

    def test_health_has_no_errors(self):
        rep = health.run()
        self.assertEqual(rep.errors, 0, rep.as_dict())


class Hooks(unittest.TestCase):
    def test_claude_guard_blocks_rm(self):
        r = run_hook("guard.py", {"tool_name": "Bash", "tool_input": {"command": "rm 10-notes/x.md"}, "cwd": str(VAULT)})
        self.assertEqual(r.returncode, 2)

    def test_hermes_guard_scoped_to_vault(self):
        outside = run_hook("guard.py", {"hook_event_name": "pre_tool_call", "tool_name": "terminal",
                                        "tool_input": {"command": "rm -rf build"}, "cwd": str(TMP)})
        self.assertEqual(outside.returncode, 0)
        inside = run_hook("guard.py", {"hook_event_name": "pre_tool_call", "tool_name": "write_file",
                                       "tool_input": {"path": str(VAULT / "10-notes" / "a.md"),
                                                      "content": "AKIAABCDEFGHIJKLMNOP"}, "cwd": str(TMP)})
        self.assertEqual(inside.returncode, 2)

    def test_recall_hook_shapes(self):
        claude = run_hook("recall.py", {"hook_event_name": "UserPromptSubmit", "prompt": "motor controller status"})
        self.assertIn("[[motor-controller]]", claude.stdout)
        hermes = run_hook("recall.py", {"hook_event_name": "pre_llm_call",
                                        "extra": {"user_message": "motor controller status", "is_first_turn": True}})
        ctx = json.loads(hermes.stdout)["context"]
        self.assertIn("wake-up", ctx)
        self.assertIn("[[motor-controller]]", ctx)


class Transports(unittest.TestCase):
    def test_mcp_server_handshake_and_call(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "brain_search", "arguments": {"query": "motor"}}},
        ]
        r = subprocess.run([sys.executable, str(VAULT / "scripts" / "mcp_server.py"), "--read-only"],
                           input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True)
        out = [json.loads(l) for l in r.stdout.splitlines()]
        self.assertEqual([o["id"] for o in out], [1, 2, 3])
        names = [t["name"] for t in out[1]["result"]["tools"]]
        self.assertNotIn("brain_capture", names)  # read-only
        self.assertIn("motor-controller", out[2]["result"]["content"][0]["text"])

    def test_hermes_tool_call_parsing(self):
        calls = parse_tool_calls('<think>x</think><tool_call>\n{"name": "brain_recall", "arguments": {"query": "q"}}\n'
                                 '</tool_call><tool_call>{bad json}</tool_call>')
        self.assertEqual(calls, [{"name": "brain_recall", "arguments": {"query": "q"}}])

    def test_openai_schema_valid(self):
        for t in openai_schema():
            self.assertEqual(t["type"], "function")
            self.assertEqual(t["function"]["parameters"]["type"], "object")


if __name__ == "__main__":
    unittest.main()

"""Behavioral tests use synthetic packets and owned fake subprocesses, not a thesis."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_v2.py"
spec = importlib.util.spec_from_file_location("review_v2_under_test", SCRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def packet():
    return v.extract_packet(["Introduction\nMethod A [1]. Mathematical range [0,1].\n", "References\n[1] Smith. A title. 2024.\n"], "a" * 64)


def report(actor, inputs, findings=None):
    base = {"actor": actor, "pdf_sha256": "a"*64, "fresh_context": True,
            "inputs_used": ["inputs/" + name for name in v.snapshot(inputs)],
            "public_sources": ["https://example.org/work"], "limitations": [],
            "rationale": "The visible method and evidence support a bounded conclusion.", "findings": findings or []}
    if actor.startswith("R"):
        base.update(grade="A", recommendation=v.GRADES["A"], confidence="high", strengths=["Clearly defined question."],
                    whole_thesis="A method and evaluation answer the stated research question.",
                    gates={g: {"judgment": "Supported by the method and results.", "pages": [1], "finding_ids": []} for g in "ABCDEFGHI"})
    elif actor == "AI":
        base.update(signal="low", counterevidence="Specific factual prose.", disclaimer="Not an AI-use or authorship test.", prose_pages=[1])
    return base


def write_fixture(workspace, actor="R1", degree="doctorate"):
    inputs, outputs = workspace / "inputs", workspace / "outputs"
    inputs.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(exist_ok=True)
    (workspace / "scratch").mkdir(exist_ok=True)
    v.write_json(inputs / "packet.json", packet())
    v.write_json(inputs / "policy.json", {})
    (inputs / "review-v2.md").write_text("Rules", encoding="utf-8")
    (inputs / "thesis.pdf").write_bytes(b"fixture PDF bytes")
    (inputs / "pages").mkdir(exist_ok=True)
    for page in (1, 2):
        (inputs / "pages" / f"{page:04d}.png").write_bytes(b"fixture image bytes")
    r = report(actor, inputs)
    v.write_json(outputs / "report.json", r)
    if actor == ("R5" if degree == "doctorate" else "R3"):
        v.write_json(outputs / "pages.json", [{"page": p, "status": "clear", "observation": f"Actual content on page {p}.", "finding_ids": []} for p in (1, 2)])
        v.write_json(outputs / "bibliography.json", [{"id": "B0001", "sources": r["public_sources"], "finding_ids": [],
                    "fields": {field: {"rendered": field, "canonical": field, "status": "verified", "evidence": "Official record, field " + field} for field in v.BIB_FIELDS}}])
    if actor == ("R4" if degree == "doctorate" else "R3"):
        v.write_json(outputs / "citations.json", [
            {"id": "C0001", "kind": "citation", "reason": "Attached to named method.", "finding_ids": [], "sources": [
                {"reference": 1, "proposition": "Method A", "support": "direct", "url": r["public_sources"][0], "locator": "Section 2", "evidence": "Specific source quotation and boundary."}]},
            {"id": "C0002", "kind": "noncitation", "reason": "Closed numeric interval.", "finding_ids": [], "sources": []}])
    return r


class PacketTests(unittest.TestCase):
    def test_math_stays_visible_without_closed_grammar(self):
        p = packet()
        self.assertEqual([x["expected_sources"] for x in p["candidates"]], [[1], [0, 1]])
        self.assertEqual(len(p["bibliography"]), 1)

    def test_repeated_source_and_descending_range(self):
        self.assertEqual(v.expanded("[3-1,1]"), [3, 2, 1, 1])

    def test_unmatched_brackets_not_silently_dropped(self):
        p = v.extract_packet(["x [ and y ] ]", "References\n[1] One."], "b"*64)
        self.assertEqual(p["candidates"][0]["marker"], "]")

    def test_missing_bibliography_is_operational_stop(self):
        with self.assertRaisesRegex(v.ReviewError, "preparation stopped"):
            v.extract_packet(["No bibliography"], "b"*64)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_reviewer_and_ai_outputs(self):
        for actor in ["R1", "R2", "R3", "R4", "R5", "AI"]:
            workspace = self.root / actor
            write_fixture(workspace, actor)
            self.assertEqual(v.validate(workspace, actor, "doctorate")["report"]["actor"], actor)

    def test_master_combined_owner(self):
        write_fixture(self.root, "R3", "master")
        self.assertEqual(v.validate(self.root, "R3", "master")["coverage"], {"pages": 2, "bibliography": 1, "citations": 2})

    def test_grade_recommendation_mismatch(self):
        r = write_fixture(self.root)
        r["recommendation"] = "小修后可答辩"
        v.write_json(self.root / "outputs/report.json", r)
        with self.assertRaisesRegex(v.ReviewError, "recommendation"):
            v.validate(self.root, "R1", "doctorate")

    def test_peer_context_is_rejected(self):
        r = write_fixture(self.root)
        r["inputs_used"].append("../R2/report.json")
        v.write_json(self.root / "outputs/report.json", r)
        with self.assertRaisesRegex(v.ReviewError, "allowlist"):
            v.validate(self.root, "R1", "doctorate")

    def test_page_coverage_and_actual_view_receipt(self):
        r = write_fixture(self.root, "R5")
        r["inputs_used"].remove("inputs/pages/0002.png")
        v.write_json(self.root / "outputs/report.json", r)
        with self.assertRaisesRegex(v.ReviewError, "not inspected"):
            v.validate(self.root, "R5", "doctorate")

    def test_bibliography_missing_field(self):
        write_fixture(self.root, "R5")
        rows = v.read_json(self.root / "outputs/bibliography.json")
        del rows[0]["fields"]["authors"]
        v.write_json(self.root / "outputs/bibliography.json", rows)
        with self.assertRaisesRegex(v.ReviewError, "every bibliography field"):
            v.validate(self.root, "R5", "doctorate")

    def test_unavailable_does_not_become_verified(self):
        write_fixture(self.root, "R5")
        rows = v.read_json(self.root / "outputs/bibliography.json")
        rows[0]["fields"]["authors"].update(status="unverifiable", canonical="", evidence="Official endpoint HTTP 403")
        v.write_json(self.root / "outputs/bibliography.json", rows)
        self.assertEqual(v.validate(self.root, "R5", "doctorate")["unverifiable"], 1)

    def test_missing_citation_source_is_not_complete(self):
        write_fixture(self.root, "R4")
        rows = v.read_json(self.root / "outputs/citations.json")
        rows[0]["sources"] = []
        v.write_json(self.root / "outputs/citations.json", rows)
        with self.assertRaisesRegex(v.ReviewError, "cluster coverage"):
            v.validate(self.root, "R4", "doctorate")

    def test_ambiguous_candidate_is_explicitly_incomplete(self):
        write_fixture(self.root, "R4")
        rows = v.read_json(self.root / "outputs/citations.json")
        rows[1]["kind"] = "ambiguous"
        v.write_json(self.root / "outputs/citations.json", rows)
        self.assertEqual(v.validate(self.root, "R4", "doctorate")["unverifiable"], 1)

    def test_duplicate_json_keys_rejected(self):
        path = self.root / "bad.json"
        path.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(v.ReviewError, "duplicate"):
            v.read_json(path)

    def test_hash_drift_not_rebased(self):
        path = self.root / "input.txt"
        path.write_text("initial")
        snap = v.snapshot(self.root)
        path.write_text("changed")
        with self.assertRaises(v.IntegrityError):
            v.same_snapshot(self.root, snap)

    def test_official_mapping(self):
        v.check_grade({"grade": "通过", "recommendation": "可答辩"}, [], {"grade_map": {"通过": "可答辩"}})


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def execute(self, program, seconds=1, idle=1, prompt=b""):
        return v.execute([sys.executable, "-B", "-u", "-c", program], prompt, self.root,
                         self.root / "log.jsonl", self.root / "err.txt", seconds=seconds, idle_seconds=idle, poll=0.01)

    def test_hanging_process_is_terminated(self):
        result = self.execute("import time; time.sleep(30)", seconds=.3, idle=10)
        self.assertEqual(result["reason"], "wall_timeout")
        self.assertFalse(v.is_alive(result["pid"]))
        self.assertLess(result["elapsed_seconds"], 3)

    def test_idle_reconnect_does_not_reset_progress(self):
        result = self.execute("import time,json\nwhile True:\n print(json.dumps({'type':'error','message':'reconnecting'}),flush=True);time.sleep(.03)", seconds=2, idle=.3)
        self.assertEqual(result["reason"], "idle_timeout")

    def test_stdin_block_is_bounded(self):
        result = self.execute("import time;time.sleep(30)", seconds=.3, idle=10, prompt=b"x"*4000000)
        self.assertEqual(result["reason"], "wall_timeout")

    def test_completed_tools_count_as_progress(self):
        result = self.execute("import json,time\nfor i in range(5):\n print(json.dumps({'type':'item.completed','item':{'type':'command_execution','status':'completed'}}),flush=True);time.sleep(.1)", seconds=2, idle=.3)
        self.assertIsNone(result["reason"])
        self.assertEqual(result["exit_code"], 0)

    def test_normal_failure_exits_without_waiting_for_deadline(self):
        result = self.execute("raise SystemExit(7)", seconds=5, idle=5)
        self.assertEqual(result["exit_code"], 7)
        self.assertLess(result["elapsed_seconds"], 2)


class TransportTests(unittest.TestCase):
    def check(self, extra):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            events = [{"type": "thread.started", "thread_id": "fresh"}, {"type": "turn.started"}, *extra,
                      {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}}, {"type": "turn.completed"}]
            path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
            v.transport_ok(path)

    def test_recovered_stream_is_not_whole_round_failure(self):
        self.check([{"type": "error", "message": "WebSocket reconnect"}])

    def test_nested_model_is_rejected(self):
        with self.assertRaisesRegex(v.ReviewError, "nested model"):
            self.check([{"type": "item.completed", "item": {"type": "command_execution", "command": "codex exec -"}}])

    def test_task_api_is_rejected(self):
        with self.assertRaisesRegex(v.ReviewError, "task access"):
            self.check([{"type": "item.started", "item": {"type": "mcp_tool_call", "tool": "read_thread"}}])

    def test_unknown_schema_stops(self):
        with self.assertRaisesRegex(v.ReviewError, "unrecognized"):
            self.check([{"type": "surprise"}])


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = {"schema": v.VERSION, "status": "ready", "spent_seconds": 0,
                      "limits": {**v.DEFAULT_LIMITS, "round_seconds": 10}, "degree": "doctorate",
                      "actors": {actor: {"status": "pending", "attempts": []} for actor in ["R1", "R2", "C"]}}
        v.write_json(self.root / "state.json", self.state)

    def tearDown(self):
        self.temp.cleanup()

    def test_local_failure_preserves_completed_peer_and_retry_budget(self):
        calls = []
        def fake(root, state, actor, attempt, deadline, auth):
            calls.append(actor)
            return {"status": "failed", "error": "test failure"} if actor == "R1" else {"status": "accepted"}
        with patch.object(v, "runtime_identity"):
            result = v.run(self.root, launcher=fake)
            self.assertEqual(result["actors"]["R2"]["status"], "accepted")
            self.assertEqual(calls.count("C"), 0)
            v.run(self.root, actor_retry="R1", launcher=fake)
            self.assertEqual(calls.count("R2"), 1)
            self.assertEqual(calls.count("R1"), 2)
            with self.assertRaisesRegex(v.ReviewError, "attempt budget"):
                v.run(self.root, actor_retry="R1", launcher=fake)

    def test_run_does_not_automatically_retry_failed_actor(self):
        self.state["actors"]["R1"]["status"] = "failed"
        self.state["actors"]["R2"]["status"] = "failed"
        v.write_json(self.root / "state.json", self.state)
        with patch.object(v, "runtime_identity"), patch.object(v, "launch_actor") as launch:
            v.run(self.root, launcher=launch)
            launch.assert_not_called()

    def test_budget_persists_across_invocations(self):
        self.state["spent_seconds"] = 11
        v.write_json(self.root / "state.json", self.state)
        with patch.object(v, "runtime_identity"):
            with self.assertRaisesRegex(v.ReviewError, "budget exhausted"):
                v.run(self.root)

    def test_live_orphan_is_not_duplicated(self):
        self.state["actors"]["R1"].update(status="running", attempts=[{"status": "running"}])
        v.write_json(self.root / "attempts/R1/1/pid.json", {"pid": os.getpid()})
        with self.assertRaisesRegex(v.ReviewError, "orphan child"):
            v.recover_interrupted(self.root, self.state)

    def test_crash_consumes_attempt_and_elapsed_budget(self):
        self.state["actors"]["R1"].update(status="running", attempts=[{"status": "running"}])
        self.state["session_started"] = time.time() - 3
        v.recover_interrupted(self.root, self.state)
        self.assertEqual(self.state["actors"]["R1"]["status"], "interrupted")
        self.assertGreaterEqual(self.state["spent_seconds"], 3)
        self.assertEqual(len(self.state["actors"]["R1"]["attempts"]), 1)

    def test_live_supervisor_lock_refuses_second_runner(self):
        with v.round_lock(self.root):
            with self.assertRaisesRegex(v.ReviewError, "supervisor"):
                with v.round_lock(self.root):
                    self.fail("second runner entered")

    def test_uncommitted_promotion_is_preserved_outside_accepted(self):
        self.state["actors"]["R1"].update(status="running", attempts=[{"status": "running"}])
        target = self.root / "accepted/R1"
        target.mkdir(parents=True)
        (target / "report.json").write_text("{}")
        (self.root / "attempts/R1/1").mkdir(parents=True)
        v.recover_interrupted(self.root, self.state)
        self.assertFalse(target.exists())
        self.assertTrue((self.root / "attempts/R1/1/uncommitted-output/report.json").exists())


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = {"schema": v.VERSION, "status": "ready_to_summarize", "degree": "doctorate",
                      "spent_seconds": 0, "limits": dict(v.DEFAULT_LIMITS), "actors": {}}
        for actor in ["R1", "R2", "R3", "R4", "R5", "AI"]:
            workspace = self.root / "fixtures" / actor
            write_fixture(workspace, actor)
            result = v.validate(workspace, actor, "doctorate")
            v.shutil.copytree(workspace / "outputs", self.root / "accepted" / actor)
            self.state["actors"][actor] = {"status": "accepted", "attempts": [], "coverage": result["coverage"], "unverifiable": 0}
        v.shutil.copytree(self.root / "fixtures/R1/inputs", self.root / "packet")
        self.chair_ws = self.root / "fixtures/C"
        v.shutil.copytree(self.root / "packet", self.chair_ws / "inputs")
        v.shutil.copytree(self.root / "accepted", self.chair_ws / "inputs/accepted")
        selection = v.acceptance_selection(self.root / "accepted", "doctorate", packet())
        v.write_json(self.chair_ws / "inputs/acceptance.json", selection)
        self.chair = report("C", self.chair_ws / "inputs")
        self.chair.update(grade="A", recommendation=v.GRADES["A"], quality_complete=True, decisions=[],
                          acceptance=[{"id": r["id"], "status": "pass", "basis": "Specific rendered page/source supports the reviewer judgment."} for r in selection])
        v.write_json(self.chair_ws / "outputs/report.json", self.chair)

    def tearDown(self):
        self.temp.cleanup()

    def deliver(self):
        result = v.validate(self.chair_ws, "C", "doctorate")
        v.shutil.copytree(self.chair_ws / "outputs", self.root / "accepted/C")
        self.state["actors"]["C"] = {"status": "accepted", "attempts": [], "coverage": result["coverage"], "unverifiable": 0}
        v.write_json(self.root / "state.json", self.state)
        with patch.object(v, "runtime_identity"):
            return v.summarize(self.root)

    def test_complete_current_round_materializes_all_reports_and_summary(self):
        result = self.deliver()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(len(list((self.root / "delivery").glob("*-report.md"))), 7)
        summary = Path(result["summary"]).read_text(encoding="utf-8")
        self.assertIn("本轮审查与验收完成", summary)
        self.assertIn(self.chair["rationale"], summary)
        self.assertEqual(v.read_json(self.root / "delivery/coverage.json")["coverage"]["citations"], [2, 2])

    def test_missing_acceptance_never_passes(self):
        self.chair["acceptance"].pop()
        v.write_json(self.chair_ws / "outputs/report.json", self.chair)
        with self.assertRaisesRegex(v.ReviewError, "coverage"):
            v.validate(self.chair_ws, "C", "doctorate")

    def test_failed_semantic_check_is_not_claimed_complete(self):
        self.chair["acceptance"][0]["status"] = "fail"
        self.chair["quality_complete"] = False
        v.write_json(self.chair_ws / "outputs/report.json", self.chair)
        result = self.deliver()
        self.assertEqual(result["status"], "incomplete_quality")
        self.assertIn("不得声称", Path(result["summary"]).read_text(encoding="utf-8"))

    def test_false_semantic_completion_is_rejected(self):
        self.chair["acceptance"][0]["status"] = "fail"
        v.write_json(self.chair_ws / "outputs/report.json", self.chair)
        with self.assertRaisesRegex(v.ReviewError, "cannot hide"):
            v.validate(self.chair_ws, "C", "doctorate")

    def test_unavailable_source_blocks_full_verification_claim_not_grade(self):
        self.state["actors"]["R5"]["unverifiable"] = 1
        result = self.deliver()
        self.assertEqual(result["status"], "incomplete_quality")
        self.assertIn("同意答辩", Path(result["summary"]).read_text(encoding="utf-8"))

    def test_incomplete_panel_cannot_make_summary(self):
        self.state["actors"]["R1"]["status"] = "failed"
        v.write_json(self.root / "state.json", self.state)
        with patch.object(v, "runtime_identity"):
            with self.assertRaisesRegex(v.ReviewError, "unfinished panel"):
                v.summarize(self.root)

    def test_clean_reviewer_prompt_contains_no_peer_or_old_round(self):
        prompt = v.build_prompt("R1", "doctorate", ["inputs/thesis.pdf"], sys.executable)
        self.assertNotIn("inputs/accepted", prompt)
        self.assertNotIn("20260831", prompt)
        self.assertIn("Do not delegate", prompt)

    def test_sampler_does_not_expand_to_duplicate_full_audit(self):
        selection = v.acceptance_selection(self.root / "accepted", "doctorate", packet())
        self.assertEqual(len(selection), 11)  # six verdicts, five audit samples

    def test_targeted_quality_repair_keeps_other_frozen_reviewers(self):
        self.chair.update(quality_complete=False, repair_actors=["R4"])
        self.chair["acceptance"][0]["status"] = "fail"
        v.write_json(self.chair_ws / "outputs/report.json", self.chair)
        self.deliver()
        state = v.load_state(self.root)
        for actor in state["actors"]:
            state["actors"][actor]["attempts"] = [{"status": "accepted"}]
        v.write_json(self.root / "state.json", state)
        before = v.digest(self.root / "accepted/R5/report.json")
        calls = []
        def fake(root, state, actor, attempt, deadline, auth):
            calls.append(actor)
            return {"status": "failed", "error": "bounded test failure"}
        with patch.object(v, "runtime_identity"):
            v.run(self.root, actor_retry="R4", launcher=fake)
        self.assertEqual(calls, ["R4"])
        self.assertEqual(v.digest(self.root / "accepted/R5/report.json"), before)
        self.assertTrue((self.root / "retired/R4-1/report.json").exists())
        self.assertFalse((self.root / "accepted/C").exists())
        self.assertFalse((self.root / "delivery").exists())


if __name__ == "__main__":
    unittest.main()

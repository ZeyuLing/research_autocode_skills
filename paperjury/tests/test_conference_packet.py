import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("packet", Path(__file__).parents[1] / "scripts" / "conference_packet.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "packet"
        self.root.mkdir()
        (self.root / "pages").mkdir()
        p.write(self.root / "paper.pdf", "fixture")
        p.write(self.root / "pages/page-001.txt", "Paper evidence here.")
        self.rules = {"venue": "ICLR", "year": 2027, "retrieved_at": "2026-09-13", "sources": [{"url": "https://example.org"}],
                      "form_status": "historical_fallback", "meta_score": {"official": False},
                      "fallback": {"source_year": 2026, "sources": ["https://example.org"], "unverified_fields": ["rating"], "disclosure": "provisional"},
                      "required_fields": ["summary", "rating", "flag_for_ethics_review"], "score_fields": {"rating": {
                          "allowed": [0, 2, 4, 6, 8, 10], "labels": {str(n): f"Label {n}" for n in [0, 2, 4, 6, 8, 10]},
                          "provenance": ["https://example.org"], "status": "fallback"}}}
        p.write(self.root / "rules.json", json.dumps(self.rules))
        self.sha = p.digest(self.root / "paper.pdf")
        self.rules_sha = p.digest(self.root / "rules.json")
        p.write(self.root / "manifest.json", json.dumps({"page_count": 1, "paper_sha256": self.sha,
                "round_id": "new-round", "rules_sha256": self.rules_sha, "reviewer_roster": ["R1"],
                "files": {str(f.relative_to(self.root)).replace("\\", "/"): p.digest(f)
                          for f in self.root.rglob("*") if f.is_file()}}))
        self.review = {"reviewer_id": "R1", "paper_sha256": self.sha, "round_id": "new-round", "rules_sha256": self.rules_sha,
                       "summary": "Summary", "rating": 6, "rating_label": "Label 6", "rating_justification": "Evidence", "flag_for_ethics_review": False,
                       "coverage": {"pages_read": [1], "sections": ["Summary"], "figures_tables_inspected": [], "limitations": []},
                       "evidence": [{"page": 1, "quote": "Paper evidence"}]}
        self.path = Path(self.temp.name) / "review.json"

    def check(self):
        p.write(self.path, json.dumps(self.review))
        return p.validate_review(self.root, self.path)

    def test_valid(self):
        self.assertEqual(self.check(), [])

    def test_unlisted_score_rejected(self):
        self.review["rating"] = 5
        self.assertTrue(any("invalid score" in e for e in self.check()))

    def test_missing_pages_and_fabricated_quote(self):
        self.review["coverage"]["pages_read"] = []
        self.review["evidence"][0]["quote"] = "Made up"
        errors = self.check()
        self.assertTrue(any("coverage" in e for e in errors))
        self.assertTrue(any("quote" in e for e in errors))

    def test_mutated_input_rejected(self):
        p.write(self.root / "paper.pdf", "modified")
        with self.assertRaises(ValueError):
            self.check()

    def test_meta_receives_complete_unedited_review(self):
        self.check()
        text = p.meta_prompt(self.root, self.root.parent / "meta", [self.path])
        self.assertIn(self.path.read_text(encoding="utf-8"), text)
        self.assertNotIn("author-private-fact", text)

    def test_undisclosed_fallback_rejected(self):
        del self.rules["fallback"]
        with self.assertRaises(ValueError):
            p.validate_rules(self.rules)

    def test_prior_round_and_rules_rejected(self):
        self.review.update(round_id="old-round", rules_sha256="obsolete")
        self.assertEqual(sum("identity mismatch" in e for e in self.check()), 2)

    def test_duplicate_reviews_rejected(self):
        self.check()
        with self.assertRaises(ValueError):
            p.meta_prompt(self.root, self.root.parent / "meta", [self.path, self.path])

    def test_unmanifested_notes_rejected(self):
        p.write(self.root / "pages/prior-notes.txt", "author-private-fact")
        with self.assertRaises(ValueError):
            self.check()

    def test_empty_and_contradictory_fields(self):
        self.review.update(summary="", rating_label="Reject", rating_justification=" ")
        self.assertGreaterEqual(len(self.check()), 3)

    def test_null_coverage_returns_errors(self):
        self.review["coverage"] = None
        self.assertTrue(self.check())

    def test_contradictory_current_form_rejected(self):
        self.rules["form_status"] = "verified_current"
        del self.rules["fallback"]
        with self.assertRaises(ValueError):
            p.validate_rules(self.rules)

    def test_unknown_field_status_rejected(self):
        self.rules["score_fields"]["rating"]["status"] = "looks fine"
        with self.assertRaises(ValueError):
            p.validate_rules(self.rules)

    def test_empty_nested_fields_rejected(self):
        self.review.update(summary=[None], rating_justification={"reason": None})
        self.review["coverage"]["sections"] = [""]
        self.assertGreaterEqual(len(self.check()), 3)

    def test_internal_output_and_prompt_rejected(self):
        self.check()
        with self.assertRaises(ValueError):
            p.reviewer_prompt(self.root, "R1", "Background", self.root / "R1")
        with self.assertRaises(ValueError):
            p.meta_prompt(self.root, self.root / "meta", [self.path])
        with self.assertRaises(ValueError):
            p.reviewer_prompt(self.root, "R1", "Background", self.root.parent / "R1", self.root / "prompt.txt")
        with self.assertRaises(ValueError):
            p.meta_prompt(self.root, self.root.parent / "meta", [self.path], self.root / "prompt.txt")

    def test_malformed_meta_input_id_rejected(self):
        self.review["reviewer_id"] = {}
        p.write(self.path, json.dumps(self.review))
        with self.assertRaisesRegex(ValueError, "reviewer_id"):
            p.meta_prompt(self.root, self.root.parent / "meta", [self.path])

    def test_meta_validation(self):
        meta = {k: self.review[k] for k in ("paper_sha256", "round_id", "rules_sha256", "coverage", "evidence")}
        meta.update(final_rating=6, rating_label="Label 6", reviewer_ids=["R1"], score_status="simulation_summary")
        for key in ("decision", "decisive_reasons", "agreements", "disagreements", "reviewer_assessment", "ordered_priorities", "uncertainties", "meta_review_zh"):
            meta[key] = "Declared content"
        path = self.root.parent / "meta.json"
        p.write(path, json.dumps(meta))
        self.assertEqual(p.validate_meta(self.root, path), [])
        meta.update(final_rating=5, score_status="official")
        p.write(path, json.dumps(meta))
        self.assertGreaterEqual(len(p.validate_meta(self.root, path)), 2)
        meta["reviewer_ids"] = [{}]
        meta["meta_review_zh"] = [None]
        p.write(path, json.dumps(meta))
        errors = p.validate_meta(self.root, path)
        self.assertTrue(any("roster" in error for error in errors))
        self.assertTrue(any("meta_review_zh" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

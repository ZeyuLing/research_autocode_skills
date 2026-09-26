import importlib.util
import copy
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


class EvidenceFirstTests(unittest.TestCase):
    def setUp(self):
        PacketTests.setUp(self)
        self.card = {
            "reviewer_id": "R1", "background": "Methods researcher with experience in controlled studies.",
            "contribution_lens": "Explanatory mechanisms with well-defined scope.",
            "evidence_lens": "Interventions that distinguish proposed explanations.",
            "uncertainty_policy": "Separate missing peripheral detail from unsupported central claims.",
            "scope_policy": "A bounded result can matter if its stated scope is supported.",
            "counterweight": "A distinctive mechanism still needs sound evidence.",
        }

    def enable_protocol(self, cards=None):
        cards = cards or [self.card]
        p.write(self.root / "criteria.json", json.dumps(p.substantive_rules(self.rules)))
        manifest = p.read_json(self.root / "manifest.json")
        manifest.update(review_protocol=p.PROTOCOL, reviewer_roster=[c["reviewer_id"] for c in cards],
                        reviewer_profile_sha256={c["reviewer_id"]: p.object_digest(c) for c in cards})
        manifest["files"]["criteria.json"] = p.digest(self.root / "criteria.json")
        p.write(self.root / "manifest.json", json.dumps(manifest))

    def assessment(self, card=None):
        card = card or self.card
        report = {key: copy.deepcopy(self.review[key]) for key in
                  ("paper_sha256", "round_id", "rules_sha256", "coverage", "evidence", "summary")}
        report.update(reviewer_id=card["reviewer_id"], reviewer_profile_sha256=p.object_digest(card),
                      strengths="A supported result.", weaknesses="Scope remains bounded.", questions="none",
                      claim_assessment="The experiment supports the stated bounded claim.",
                      profile_application="The control is relevant to interpreting the mechanism.",
                      decision_factors=[{"id": "F1", "direction": "support", "criterion": "soundness",
                                         "statement": "The control supports the bounded claim.", "evidence_indices": [0]}])
        return report

    def seal_review(self, card=None, rating=6):
        card = card or self.card
        out = self.root.parent / card["reviewer_id"]
        assessment = self.assessment(card)
        p.write(out / "assessment.json", json.dumps(assessment))
        prompt = p.score_prompt(self.root, card["reviewer_id"], out)
        self.assertIn(p.digest(out / "assessment.json"), prompt)
        choices = sorted(self.rules["score_fields"]["rating"]["allowed"])
        index = choices.index(rating)
        neighbors = choices[max(0, index - 1):index] + choices[index + 1:index + 2]
        report = copy.deepcopy(assessment)
        report.update(rating=rating, rating_label=f"Label {rating}", rating_justification="Bounded evidence fits this label.",
                      flag_for_ethics_review=False, assessment_sha256=p.digest(out / "assessment.json"),
                      score_reasoning={"decisive_factor_ids": ["F1"], "tradeoff": "The bounded contribution outweighs peripheral uncertainty.",
                                       "confidence_reason": "The protocol is described, but transfer remains unknown.",
                                       "adjacent_choices": [{"rating": n, "why_not": "This label fits the evidence less well."} for n in neighbors]})
        path = out / "review.json"
        p.write(path, json.dumps(report))
        return path, report

    def test_titles_alone_do_not_create_diverse_profiles(self):
        second = dict(self.card, reviewer_id="R2", background="A senior professor.")
        with self.assertRaisesRegex(ValueError, "two substantive axes"):
            p.validate_panel({"reviewers": [self.card, second]}, ["R1", "R2"])
        second.update(contribution_lens="Useful empirical findings.", evidence_lens="Matched comparisons.")
        self.assertEqual(len(p.validate_panel({"reviewers": [self.card, second]}, ["R1", "R2"])), 2)

    def test_profile_cannot_add_target_score(self):
        with self.assertRaises(ValueError):
            p.validate_profile(dict(self.card, target_rating=8))

    def test_initial_prompt_hides_numeric_menu_and_other_profiles(self):
        self.enable_protocol()
        profile = self.root.parent / "profile.json"
        p.write(profile, json.dumps(self.card))
        text = p.assessment_prompt(self.root, "R1", profile, self.root.parent / "R1")
        self.assertNotIn("Label 6", text)
        self.assertNotIn('"allowed"', text)
        self.assertIn(self.card["counterweight"], text)
        p.write(profile, json.dumps(dict(self.card, evidence_lens="Changed after freeze")))
        with self.assertRaisesRegex(ValueError, "frozen role"):
            p.assessment_prompt(self.root, "R1", profile, self.root.parent / "R1")

    def test_new_protocol_cannot_use_one_shot_scoring(self):
        self.enable_protocol()
        with self.assertRaisesRegex(ValueError, "assessment-prompt"):
            p.reviewer_prompt(self.root, "R1", "Background", self.root.parent / "R1")

    def test_scores_and_unanchored_factors_rejected_in_assessment(self):
        self.enable_protocol()
        report = self.assessment()
        report["rating"] = 6
        report["decision_factors"][0]["evidence_indices"] = [99]
        path = self.root.parent / "assessment.json"
        p.write(path, json.dumps(report))
        errors = p.validate_assessment(self.root, path)
        self.assertTrue(any("unscored" in error for error in errors))
        self.assertTrue(any("evidence indices" in error for error in errors))

    def test_valid_two_pass_review_and_scale_endpoints(self):
        self.enable_protocol()
        for rating in (0, 6, 10):
            with self.subTest(rating=rating):
                path, _ = self.seal_review(rating=rating)
                self.assertEqual(p.validate_review(self.root, path), [])

    def test_bound_assessment_cannot_change_to_match_rating(self):
        self.enable_protocol()
        path, _ = self.seal_review()
        assessment_path = path.parent / "assessment.json"
        report = p.read_json(assessment_path)
        report["weaknesses"] = "A new concern added after seeing the labels."
        p.write(assessment_path, json.dumps(report))
        self.assertTrue(any("assessment" in error for error in p.validate_review(self.root, path)))
        with self.assertRaisesRegex(ValueError, "changed after scoring"):
            p.score_prompt(self.root, "R1", path.parent)

    def test_score_pass_preserves_findings_and_cites_existing_factors(self):
        self.enable_protocol()
        path, report = self.seal_review()
        report["strengths"] = "Different claim"
        report["score_reasoning"]["decisive_factor_ids"] = ["UNKNOWN"]
        p.write(path, json.dumps(report))
        errors = p.validate_review(self.root, path)
        self.assertTrue(any("frozen assessment field" in error for error in errors))
        self.assertTrue(any("decisive_factor_ids" in error for error in errors))

    def test_adjacent_choices_use_real_scale_neighbors(self):
        self.enable_protocol()
        path, report = self.seal_review()
        report["score_reasoning"]["adjacent_choices"] = [{"rating": 5, "why_not": "Not allowed"}]
        p.write(path, json.dumps(report))
        self.assertTrue(any("adjacent permitted" in error for error in p.validate_review(self.root, path)))

    def test_same_scores_are_valid_and_exact_copies_are_only_diagnostics(self):
        second = dict(self.card, reviewer_id="R2", contribution_lens="Practical value.", evidence_lens="Transfer studies.")
        self.enable_protocol([self.card, second])
        first_path, _ = self.seal_review()
        second_path, _ = self.seal_review(second)
        diagnostic = p.audit_panel(self.root, [first_path, second_path])
        self.assertTrue(diagnostic["valid"])
        self.assertTrue(diagnostic["all_ratings_equal"])
        self.assertTrue(diagnostic["exact_reasoning_matches"])
        self.assertEqual(diagnostic["rating_counts"], {"6": 2})
        text = p.meta_prompt(self.root, self.root.parent / "meta", [first_path, second_path])
        self.assertIn(first_path.read_text(encoding="utf-8"), text)
        self.assertIn(second_path.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()

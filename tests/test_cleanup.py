"""Unit-Tests fuer keymic.cleanup."""
from __future__ import annotations

import unittest
from unittest import mock

from keymic import cleanup as tc


class TestPostprocess(unittest.TestCase):
    def setUp(self):
        self.cfg = tc.CleanupConfig(
            remove_fillers=True,
            filler_words=["aehm", "halt", "quasi"],
            auto_capitalize=True,
            auto_punctuate=False,
        )

    def test_filler_removal(self):
        out = tc.postprocess("Also aehm das ist halt quasi ein Test", self.cfg)
        self.assertEqual(out, "Also das ist ein test")

    def test_filler_case_insensitive(self):
        cfg = tc.CleanupConfig(
            remove_fillers=True, filler_words=["aehm", "halt", "quasi"],
            auto_capitalize=False, auto_punctuate=False,
        )
        out = tc.postprocess("AEHM halt QUASI", cfg)
        self.assertEqual(out, "")

    def test_filler_only_whole_words(self):
        cfg = tc.CleanupConfig(
            remove_fillers=True, filler_words=["aehm", "halt", "quasi"],
            auto_capitalize=True, auto_punctuate=False,
        )
        out = tc.postprocess("Das ist haltbar", cfg)
        self.assertEqual(out, "Das ist haltbar")

    def test_capitalize(self):
        cfg = tc.CleanupConfig(
            remove_fillers=False, filler_words=[],
            auto_capitalize=True, auto_punctuate=False,
        )
        self.assertEqual(tc.postprocess("hallo welt", cfg), "Hallo welt")

    def test_no_capitalize(self):
        cfg = tc.CleanupConfig(
            remove_fillers=False, filler_words=[],
            auto_capitalize=False, auto_punctuate=False,
        )
        self.assertEqual(tc.postprocess("hallo", cfg), "hallo")

    def test_empty_input(self):
        cfg = tc.CleanupConfig(
            remove_fillers=True, filler_words=["aehm"],
            auto_capitalize=True, auto_punctuate=False,
        )
        self.assertEqual(tc.postprocess("", cfg), "")

    def test_punctuation_added(self):
        cfg = tc.CleanupConfig(
            remove_fillers=False, filler_words=[],
            auto_capitalize=False, auto_punctuate=True,
        )
        self.assertEqual(tc.postprocess("ohne punkt", cfg), "ohne punkt.")

    def test_punctuation_not_doubled(self):
        cfg = tc.CleanupConfig(
            remove_fillers=False, filler_words=[],
            auto_capitalize=False, auto_punctuate=True,
        )
        self.assertEqual(tc.postprocess("schon da.", cfg), "schon da.")


class TestAIPostprocess(unittest.TestCase):
    def setUp(self):
        self.cfg = tc.CleanupConfig(
            remove_fillers=True,
            filler_words=["aehm", "halt"],
            auto_capitalize=True,
            auto_punctuate=False,
            ai_postprocess=True,
            ai_model="openai/gpt-oss-20b",
            ai_endpoint="https://example.test/v1/chat/completions",
            ai_timeout_s=5.0,
            ai_custom_dict=["cachyOS", "ydotool"],
            ai_skip_if_clean=True,
        )

    def test_config_defaults_present(self):
        cfg = tc.CleanupConfig()
        self.assertTrue(cfg.ai_postprocess)
        self.assertEqual(cfg.ai_model, "llama-3.3-70b-versatile")
        self.assertEqual(cfg.ai_endpoint, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(cfg.ai_timeout_s, 15.0)
        self.assertEqual(cfg.ai_custom_dict, [])
        self.assertTrue(cfg.ai_skip_if_clean)

    def test_disabled_returns_text_unchanged(self):
        cfg = tc.CleanupConfig(ai_postprocess=False)
        fake_session = mock.MagicMock()
        out = tc.ai_postprocess("aehm hallo welt", cfg, "fake-key",
                                 session=fake_session)
        self.assertEqual(out, "aehm hallo welt")
        fake_session.post.assert_not_called()

    def test_skip_when_clean(self):
        fake_session = mock.MagicMock()
        stats = {}
        cfg = tc.CleanupConfig(
            ai_postprocess=True, filler_words=["aehm", "halt"], ai_skip_if_clean=True,
        )
        out = tc.ai_postprocess("hallo welt wie geht es dir",
                                 cfg, "fake-key",
                                 session=fake_session, stats=stats)
        self.assertEqual(out, "hallo welt wie geht es dir")
        fake_session.post.assert_not_called()
        self.assertEqual(stats["skipped"], 1)

    def test_calls_api_when_filler_present(self):
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": "Hallo Welt, wie geht es dir?"}}]
        }
        fake_session = mock.MagicMock()
        fake_session.post.return_value = fake_resp

        stats = {}
        cfg = tc.CleanupConfig(
            ai_postprocess=True,
            filler_words=["aehm", "halt"],
            ai_model="openai/gpt-oss-20b",
            ai_endpoint="https://example.test/v1/chat/completions",
            ai_timeout_s=5.0,
            ai_custom_dict=["cachyOS", "ydotool"],
            ai_skip_if_clean=True,
        )
        out = tc.ai_postprocess("aehm hallo welt", cfg, "fake-key",
                                 session=fake_session, stats=stats)
        self.assertEqual(out, "Hallo Welt, wie geht es dir?")
        args, kwargs = fake_session.post.call_args
        self.assertEqual(args[0], "https://example.test/v1/chat/completions")
        body = kwargs["json"]
        self.assertEqual(body["model"], "openai/gpt-oss-20b")
        self.assertEqual(body["temperature"], 0.0)
        sys_msg = body["messages"][0]["content"]
        self.assertIn("cachyOS", sys_msg)
        self.assertIn("ydotool", sys_msg)
        self.assertEqual(body["messages"][1]["content"], "aehm hallo welt")
        self.assertEqual(stats["ai_calls"], 1)
        self.assertNotIn("skipped", stats)

    def test_network_error_falls_back(self):
        fake_session = mock.MagicMock()
        fake_session.post.side_effect = ConnectionError("netz weg")
        stats = {}
        cfg = tc.CleanupConfig(
            ai_postprocess=True, filler_words=["aehm", "halt"], ai_skip_if_clean=True,
        )
        out = tc.ai_postprocess("aehm hallo", cfg, "fake-key",
                                 session=fake_session, stats=stats)
        self.assertEqual(out, "aehm hallo")
        self.assertEqual(stats["ai_errors"], 1)

    def test_api_error_status_falls_back(self):
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 500
        fake_resp.text = "boom"
        fake_session = mock.MagicMock()
        fake_session.post.return_value = fake_resp
        stats = {}
        cfg = tc.CleanupConfig(
            ai_postprocess=True, filler_words=["aehm", "halt"], ai_skip_if_clean=True,
        )
        out = tc.ai_postprocess("aehm hallo", cfg, "fake-key",
                                 session=fake_session, stats=stats)
        self.assertEqual(out, "aehm hallo")
        self.assertEqual(stats["ai_errors"], 1)

    def test_skip_disabled_always_calls(self):
        fake_resp = mock.MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [{"message": {"content": "sauberer satz"}}]
        }
        fake_session = mock.MagicMock()
        fake_session.post.return_value = fake_resp
        cfg = tc.CleanupConfig(
            ai_postprocess=True, filler_words=["aehm", "halt"], ai_skip_if_clean=False,
            ai_model="openai/gpt-oss-20b",
            ai_endpoint="https://example.test/v1/chat/completions",
            ai_timeout_s=5.0,
        )
        out = tc.ai_postprocess("hallo welt", cfg, "fake-key",
                                 session=fake_session)
        self.assertEqual(out, "sauberer satz")
        fake_session.post.assert_called_once()


class TestModeParameter(unittest.TestCase):
    def setUp(self):
        tc.MODE_PROMPTS.clear()
        tc.MODE_PROMPTS.update({
            "strukturiert": "strukturiert prompt",
            "formell": "formell prompt",
        })

    def test_postprocess_with_strukturiert_mode(self):
        cfg = tc.CleanupConfig(
            remove_fillers=True,
            filler_words=["aehm", "halt"],
            auto_capitalize=True,
            auto_punctuate=True,
        )
        out = tc.postprocess("aehm hallo welt", cfg, mode="strukturiert")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "Hallo welt.")

    def test_register_mode_prompt_overrides_default(self):
        tc.register_mode_prompt("foo", "foo prompt content")
        self.assertIn("foo", tc.MODE_PROMPTS)
        self.assertEqual(tc.MODE_PROMPTS["foo"], "foo prompt content")

    def test_unknown_mode_falls_back_to_normal(self):
        cfg = tc.CleanupConfig(
            remove_fillers=True,
            filler_words=["aehm"],
            auto_capitalize=True,
            auto_punctuate=False,
        )
        out = tc.postprocess("aehm test text", cfg, mode="unknown_mode_xyz")
        self.assertIsInstance(out, str)
        self.assertEqual(out, "Test text")


class TestWordBoundary(unittest.TestCase):
    def test_replace_simple(self):
        self.assertEqual(tc.re_sub_word("foo halt bar", "halt"), "foo  bar")

    def test_no_substring_replace(self):
        self.assertEqual(tc.re_sub_word("haltbar", "halt"), "haltbar")

    def test_replace_at_start(self):
        self.assertEqual(tc.re_sub_word("halt foo", "halt"), " foo")

    def test_replace_at_end(self):
        self.assertEqual(tc.re_sub_word("foo halt", "halt"), "foo ")

    def test_multiple_occurrences(self):
        self.assertEqual(tc.re_sub_word("halt a halt b", "halt"), " a  b")


class TestCleanupPublicAPI(unittest.TestCase):
    """Tests for the public tc.cleanup() entry point."""

    def test_cleanup_default_keeps_fillers(self):
        """User-Wunsch: Füllwörter wie 'so', 'halt', 'quasi' NICHT entfernen."""
        out = tc.cleanup("So, halt testen wir mal", use_ai=False)
        assert "So" in out
        assert "halt" in out
        assert "testen wir mal" in out

    def test_cleanup_default_normalizes_whitespace(self):
        out = tc.cleanup("hallo   welt", use_ai=False)
        assert out == "Hallo welt."

    def test_cleanup_default_capitalizes_first_letter(self):
        out = tc.cleanup("hallo welt", use_ai=False)
        assert out.startswith("H")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Test MoltWorld Python bot: reply-to-other logic, no generic opener, JSON parse."""
import os
import sys
from unittest import main, TestCase
from unittest.mock import patch

# Run from repo root; agent_template lives under agents/
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENTS_ROOT = os.path.join(REPO_ROOT, "agents")
if AGENTS_ROOT not in sys.path:
    sys.path.insert(0, AGENTS_ROOT)
os.chdir(REPO_ROOT)

os.environ.setdefault("AGENT_ID", "MalicorSparky2")
os.environ.setdefault("DISPLAY_NAME", "MalicorSparky2")
os.environ.setdefault("WORLD_API_BASE", "https://www.theebie.de")

import agent_template.moltworld_bot as bot


class TestBot(TestCase):
    def test_is_other_bot(self):
        self.assertTrue(bot._is_other_bot("Sparky1Agent", "MalicorSparky2"))
        self.assertTrue(bot._is_other_bot("MalicorSparky2", "Sparky1Agent"))
        self.assertFalse(bot._is_other_bot("MalicorSparky2", "MalicorSparky2"))
        self.assertFalse(bot._is_other_bot("Sparky1Agent", "Sparky1Agent"))
        self.assertFalse(bot._is_other_bot("TestBot", "MalicorSparky2"))

    def test_extract_json(self):
        self.assertEqual(bot._extract_json('{"kind": "chat_say", "text": "Hi"}'), {"kind": "chat_say", "text": "Hi"})
        self.assertEqual(bot._extract_json('  {"kind": "noop"}  '), {"kind": "noop"})
        self.assertEqual(bot._extract_json('Here is: {"kind": "chat_say", "text": "Let\'s go!"}'), {"kind": "chat_say", "text": "Let's go!"})
        self.assertIsNone(bot._extract_json("no json"))

    def test_run_one_step_noop_when_last_from_us(self):
        with patch.object(bot, "get_chat_recent", return_value=[
            {"sender_id": "MalicorSparky2", "sender_name": "MalicorSparky2", "text": "I said this"}
        ]), patch.object(bot, "llm_chat") as mock_llm:
            result = bot.run_one_step()
            self.assertEqual(result, "noop")
            mock_llm.assert_not_called()

    def test_run_one_step_sent_when_reply(self):
        sent = []
        with patch.object(bot, "get_chat_recent", return_value=[
            {"sender_id": "Sparky1Agent", "sender_name": "Sparky1Agent", "text": "Any place in mind?"}
        ]), patch.object(bot, "chat_send", side_effect=lambda t: sent.append(t) or True), \
             patch.object(bot, "llm_chat", return_value='{"kind": "chat_say", "text": "Let\'s explore here first."}'):
            result = bot.run_one_step()
            self.assertEqual(result, "sent")
            self.assertEqual(len(sent), 1)
            self.assertTrue("explore" in sent[0].lower() or "here" in sent[0].lower())

    def test_run_one_step_noop_from_llm(self):
        sent = []
        with patch.object(bot, "get_chat_recent", return_value=[
            {"sender_id": "Sparky1Agent", "sender_name": "Sparky1Agent", "text": "Hello!"}
        ]), patch.object(bot, "chat_send", side_effect=lambda t: sent.append(t) or True), \
             patch.object(bot, "llm_chat", return_value='{"kind": "noop"}'):
            result = bot.run_one_step()
            self.assertEqual(result, "noop")
            self.assertEqual(len(sent), 0)


if __name__ == "__main__":
    main(argv=[__file__, "-v"])

#!/usr/bin/env python3
"""Test that MoltWorld turn payload instructs both agents to reply to each other (no generic openers).
   Runs the same logic as run_moltworld_pull_and_wake.sh payload builder with mock world JSON."""
import json
import os
import sys
import time

def build_turn_message(world: dict, agent_id: str, agent_name: str) -> str:
    """Mirrors the compact payload built in run_moltworld_pull_and_wake.sh."""
    chat = world.get("recent_chat") or []
    last = chat[-5:]
    now_sec = time.time()
    last_msg = last[-1] if last else {}
    last_sender = (last_msg.get("sender_id") or last_msg.get("sender_name") or "").strip()
    last_text = (last_msg.get("text") or "").strip()
    other_bot = "MalicorSparky2" if (agent_id or "").strip() == "Sparky1Agent" else "Sparky1Agent"
    reply_to_other = (last_sender == other_bot and last_text)
    last_from_us = bool(agent_id and (last_msg.get("sender_id") or "").strip() == agent_id)

    lines = [
        f"You are {agent_name}. Tools only: first world_state, then chat_say or go_to/world_action. No plain-text reply.",
    ]
    if reply_to_other:
        lines.extend([
            f'TASK — The other agent just said: "{last_text[:280]}"',
            "Your ONLY job this turn is to reply to that: reference their words, answer the question, or comment. Do NOT fetch_url or web_fetch first when replying—reply to what they said. Reply in chat_say that directly replies to the message in TASK above.",
            "Avoid: generic greeting ('Hello there!', 'Good idea! I'm in.' when they asked something specific). Instead: if they asked 'what kind of fun?' say what kind; if 'where do we start?' give one concrete step (e.g. 'How about the board?').",
        ])
    lines.append("")
    lines.append("recent_chat (latest last):")
    for i, m in enumerate(last):
        sender = m.get("sender_name") or m.get("sender_id") or "?"
        text = (m.get("text") or "").strip()
        suffix = ""
        if i == len(last) - 1:
            try:
                created_at = m.get("created_at")
                created_sec = float(created_at) if created_at else 0
                if created_sec:
                    age_min = int((now_sec - created_sec) / 60)
                    suffix = f" ({age_min} min ago)" if age_min >= 1 else ""
                if agent_id and (m.get("sender_id") or "").strip() == agent_id:
                    suffix = " (from you)" if not suffix else suffix + ", from you"
            except (TypeError, ValueError):
                pass
        lines.append(f"  {sender}: {text}{suffix}")

    if last_from_us:
        lines.extend([
            "",
            "Last message from you → world_state only this turn; do not call chat_say (avoids double-post).",
        ])
    else:
        is_narrator = "Sparky1" in agent_name or agent_name == "Sparky1Agent"
        if reply_to_other:
            lines.append("")
            lines.append("LAST: chat_say must directly reply to the message in TASK above. No generic greeting.")
        if is_narrator and not reply_to_other:
            lines.extend([
                "",
                "No other-agent message to reply to: call world_state then fetch_url/web_fetch a real URL, then chat_say with 1–2 sentence summary or question from that page (not 'Got it!').",
            ])
        else:
            lines.extend([
                "",
                "world_state then chat_say. If last message asks about a webpage → web_fetch then summarize. If question (math/time) → answer in chat_say. If from Sparky1Agent → respond to what they said (concrete suggestion if they asked 'where do we start?'). If from you or old → short varied opener. Human unanswerable → 'I don't know how to answer this, sorry.'",
            ])
        lines.append("Vary wording; do not repeat the same phrase you or the other agent used recently.")
    return "\n".join(lines)


def main():
    # Case 1: Sparky1Agent replying to MalicorSparky2
    world_sparky2_last = {
        "recent_chat": [
            {"sender_id": "Sparky1Agent", "text": "Ready for some fun?"},
            {"sender_id": "MalicorSparky2", "text": "Yes! What kind of fun do you have in mind?", "created_at": time.time() - 60},
        ]
    }
    msg1 = build_turn_message(world_sparky2_last, "Sparky1Agent", "Sparky1Agent")
    assert "TASK — The other agent just said" in msg1, "Sparky1 payload must contain TASK with other agent message"
    assert "Your ONLY job this turn is to reply to that" in msg1, "Payload must require replying to that message"
    assert "chat_say that directly replies to the message in TASK above" in msg1, "Narrator must be told to reply to TASK"
    assert "Do NOT fetch_url or web_fetch first when replying" in msg1, "Narrator must not fetch when replying"
    assert "LAST:" in msg1, "Payload must end with LAST reminder"
    print("Sparky1 replying to Sparky2: OK")

    # Case 2: MalicorSparky2 replying to Sparky1Agent
    world_sparky1_last = {
        "recent_chat": [
            {"sender_id": "MalicorSparky2", "text": "Sure."},
            {"sender_id": "Sparky1Agent", "text": "Want to try a quick math puzzle? How much is 3+2?", "created_at": time.time() - 30},
        ]
    }
    msg2 = build_turn_message(world_sparky1_last, "MalicorSparky2", "MalicorSparky2")
    assert "TASK — The other agent just said" in msg2, "Sparky2 payload must contain TASK with other agent message"
    assert "Your ONLY job this turn is to reply to that" in msg2, "Payload must require replying to that message"
    assert "LAST:" in msg2, "Payload must end with LAST reminder"
    print("Sparky2 replying to Sparky1: OK")

    # Case 3: Last message from self — no chat_say this turn (avoid double-posting)
    world_self_last = {
        "recent_chat": [
            {"sender_id": "MalicorSparky2", "text": "Hi."},
            {"sender_id": "Sparky1Agent", "text": "Hello there!", "created_at": time.time() - 120},
        ]
    }
    msg3 = build_turn_message(world_self_last, "Sparky1Agent", "Sparky1Agent")
    assert "QUOTE from MalicorSparky2" not in msg3, "When last from self, no QUOTE from other agent"
    assert "You MUST reply to the QUOTE only" not in msg3, "When last from self, no reply-to-QUOTE requirement"
    assert "do not call chat_say" in msg3 or "Do NOT call chat_say" in msg3, "When last from self, must instruct no chat_say"
    assert "world_state only" in msg3, "When last from self, must say world_state only"
    assert "fetch_url" not in msg3 and "web_fetch" not in msg3, "When last from self, no fetch requirement (we skip chat_say)"
    print("Sparky1 last from self (no reply-to-other): OK")

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

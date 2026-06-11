#!/usr/bin/env python3
"""
Interactive test harness for the v11 Clarifier (conversational).

Runs ONE case (image + short request) against a Doubao VISION endpoint, prints each
assistant message, and loops: while the reply is a question you answer as the user (it
re-runs with history); when the reply ends with the marker [[TASK_READY]] it stops — that
final message is the task brief, which you score by hand against the workplan.

Setup:
    pip install openai
    export ARK_API_KEY=...                          # Volcano 火山方舟 key
    export ARK_VISION_MODEL=ep-xxxx                  # a DOUBAO VISION endpoint/model (DeepSeek has no vision)
    # optional: export ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
    # optional: export CLARIFIER_PROMPT=clarifier_system_prompt_v11.md
    # optional: export KB_CONTEXT=kb_compiled/context_spec.md

Run:
    python test_clarifier.py path/to/siriusred.png "统计图片中胶原纤维的面积"
"""
import base64
import os
import sys
from pathlib import Path

from openai import OpenAI  # pip install openai

BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
API_KEY = os.environ.get("ARK_API_KEY")
MODEL = os.environ.get("ARK_VISION_MODEL", "<set ARK_VISION_MODEL to your doubao vision endpoint>")
PROMPT_PATH = Path(os.environ.get("CLARIFIER_PROMPT", "clarifier_system_prompt_v11.md"))
KB_PATH = Path(os.environ.get("KB_CONTEXT", "kb_compiled/context_spec.md"))
READY_MARKER = "[[TASK_READY]]"


def data_url(image_path: str) -> str:
    raw = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lstrip(".").lower() or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}.get(ext, "png")
    return f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"


def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{{KB_CONTEXT}}", KB_PATH.read_text(encoding="utf-8"))


def run_case(image_path: str, request: str):
    if not API_KEY:
        sys.exit("Set ARK_API_KEY and ARK_VISION_MODEL first.")
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_url(image_path)}},
            {"type": "text", "text": request},
        ]},
    ]

    turn = 0
    while True:
        turn += 1
        reply = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0
        ).choices[0].message.content
        print(f"\n────────── clarifier · turn {turn} ──────────\n{reply}")

        if READY_MARKER in reply:
            print(f"\n══════ TASK BRIEF FINAL (after {turn} turn(s)) ══════")
            print("→ Score this brief against the workplan's ground-truth card.")
            print(f"→ Turn count {turn} is your question-discipline signal (fewer = better, "
                  "as long as the brief is correct).")
            return reply

        answer = input("\nReply as the user (or 'q' to stop): ").strip()
        if answer.lower() == "q":
            return reply
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": answer})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python test_clarifier.py <image_path> [request]")
    img = sys.argv[1]
    req = sys.argv[2] if len(sys.argv) > 2 else input("short request (user's language): ")
    run_case(img, req)
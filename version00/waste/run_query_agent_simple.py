#!/usr/bin/env python3
"""
Minimal runner for NetworkQueryAgent.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from agents.query_agent import NetworkQueryAgent


def main() -> int:
    load_dotenv()

    project_key_path = Path(__file__).parent / "project_js_key.json"
    if project_key_path.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(project_key_path))

    question = " ".join(sys.argv[1:]).strip()
    if not question:
        question = input("Question: ").strip()
        if not question:
            print("No question provided.")
            return 1

    agent = NetworkQueryAgent()
    try:
        result = agent.ask(question)
        print(json.dumps(result, indent=2))
    finally:
        agent.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

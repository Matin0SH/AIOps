"""
Simple Demo Script for Network Query Agent
Copy-paste this into a Jupyter notebook or run directly
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path().absolute().parent))

from agents.query_agent import NetworkQueryAgent


def main():
    """Interactive query agent demo"""
    print("="*70)
    print("NETWORK QUERY AGENT - INTERACTIVE MODE")
    print("="*70)
    print("Ask questions in natural language about your network!")
    print("Type 'exit' or 'quit' to stop\n")

    # Initialize agent
    print("[INIT] Loading agent...")
    agent = NetworkQueryAgent()
    print("[OK] Agent ready!\n")

    # Interactive loop
    while True:
        # Get user question
        question = input("\n💬 Your question: ").strip()

        if question.lower() in ['exit', 'quit', 'q']:
            print("\n👋 Goodbye!")
            break

        if not question:
            continue

        try:
            # Ask the agent (with explanation and sample results)
            result = agent.ask(question, explain=True, show_samples=10)

            # Results are automatically displayed by the agent
            # You can also access them programmatically:
            # - result['count']: number of results
            # - result['results']: all result records
            # - result['explanation']: AI-generated explanation
            # - result['cypher']: the generated Cypher query

            if 'error' in result:
                print(f"\n❌ Error: {result['error']}")

        except Exception as e:
            print(f"\n❌ Exception: {e}")

    # Cleanup
    agent.close()


if __name__ == "__main__":
    main()

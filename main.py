# main.py

"""
Strud AI Application Entry Point
Initializes core backend services and launches the modern CLI UI layer.
"""

from config import CACHE_DIR, MODEL
from llm_client import LLMClient
from Science.Biology.biology_engine import BiologyEngine
from cli import StrudCLI


def main() -> None:
    """
    Main entry point for Strud AI.
    """
    # Ensure cache directory exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize backend services
    client = LLMClient(model=MODEL)
    engine = BiologyEngine(llm_client=client, model=MODEL)

    # Launch CLI application layer
    cli = StrudCLI(llm_client=client, biology_engine=engine, model=MODEL)
    cli.run()


if __name__ == "__main__":
    main()
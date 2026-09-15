# cli/input_handler.py

"""
Strud AI Input Handler
Responsible for prompt_toolkit integration, command history, auto-completion,
keyboard navigation, and prompt rendering.
"""

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML


# ============================================================
# COMMAND AUTOCOMPLETER
# ============================================================

COMMANDS = ["/help", "/clear", "/status", "/vision", "/image", "/debug", "/quit"]

slash_completer = WordCompleter(
    COMMANDS,
    sentence=True,
    ignore_case=True,
)

# Custom PromptToolkit Style
prompt_style = Style.from_dict({
    "prompt.icon": "cyan bold",
    "prompt.label": "cyan bold",
})


# ============================================================
# INPUT HANDLER CLASS
# ============================================================

class StrudInputHandler:
    """
    Manages terminal user input using PromptToolkit.
    Provides command completion, arrow-key history, and clean prompt formatting.
    """

    def __init__(self):
        self.history = InMemoryHistory()
        self.session = PromptSession(
            history=self.history,
            completer=slash_completer,
            style=prompt_style,
        )

    def get_input(self) -> str:
        """
        Prompt the user for input.
        Returns cleaned input string.
        Raises KeyboardInterrupt or EOFError on exit shortcuts.
        """
        formatted_prompt = HTML('<prompt.icon> You › </prompt.icon>')
        
        user_input = self.session.prompt(formatted_prompt)
        return user_input.strip()

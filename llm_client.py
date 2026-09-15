# llm_client.py

import requests
from typing import Optional


from config import (
    MODEL,
    LM_STUDIO_BASE_URL,
    CHAT_ENDPOINT,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    LLM_TIMEOUT,
)

DEFAULT_BASE_URL = LM_STUDIO_BASE_URL
DEFAULT_MODEL = MODEL
DEFAULT_TEMPERATURE = LLM_TEMPERATURE
DEFAULT_MAX_TOKENS = LLM_MAX_TOKENS
REQUEST_TIMEOUT = LLM_TIMEOUT


# ============================================================
# LLM CLIENT
# ============================================================

class LLMClient:
    """
    Client for communicating with a local LM Studio server.

    Responsibilities:
        - Connect to LM Studio
        - Send chat messages
        - Receive model responses
        - Handle basic connection/API errors

    It does NOT:
        - Search the textbook
        - Decide whether a question is Biology
        - Calculate retrieval confidence
        - Build Biology prompts
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: int = REQUEST_TIMEOUT,
    ):

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

        self.chat_endpoint = (
            f"{self.base_url}/chat/completions"
        )

    # ========================================================
    # CONNECTION CHECK
    # ========================================================

    def is_available(self) -> bool:
        """
        Checks whether LM Studio is running and responding.
        """

        try:

            response = requests.get(
                f"{self.base_url}/models",
                timeout=5,
            )

            return response.ok

        except requests.RequestException:

            return False

    # ========================================================
    # GET AVAILABLE MODELS
    # ========================================================

    def get_models(self) -> list[str]:
        """
        Returns the models currently available in LM Studio.
        """

        try:

            response = requests.get(
                f"{self.base_url}/models",
                timeout=10,
            )

            response.raise_for_status()

            data = response.json()

            return [
                model.get("id", "")
                for model in data.get("data", [])
                if model.get("id")
            ]

        except requests.RequestException:

            return []

        except (ValueError, TypeError):

            return []

    # ========================================================
    # CHAT
    # ========================================================

    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Sends a conversation to LM Studio and returns
        the model's text response.
        """

        selected_model = model or self.model

        selected_temperature = (
            self.temperature
            if temperature is None
            else temperature
        )

        selected_max_tokens = (
            self.max_tokens
            if max_tokens is None
            else max_tokens
        )

        payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": selected_temperature,
            "max_tokens": selected_max_tokens,
            "stream": False,
        }

        try:

            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=self.timeout,
            )

            response.raise_for_status()

        except requests.ConnectionError:

            raise RuntimeError(
                "Could not connect to LM Studio. "
                "Make sure LM Studio is running and "
                "the local server is started."
            )

        except requests.Timeout:

            raise RuntimeError(
                "LM Studio took too long to respond. "
                "The model may still be loading or generating."
            )

        except requests.HTTPError as error:

            status_code = (
                error.response.status_code
                if error.response is not None
                else "unknown"
            )

            try:
                error_detail = error.response.json()
            except Exception:
                error_detail = error.response.text

            raise RuntimeError(
                f"LM Studio API error ({status_code}): "
                f"{error_detail}"
            )

        except requests.RequestException as error:

            raise RuntimeError(
                f"Could not communicate with LM Studio: {error}"
            )

        # ----------------------------------------------------
        # Parse response
        # ----------------------------------------------------

        try:

            data = response.json()

        except ValueError:

            raise RuntimeError(
                "LM Studio returned an invalid JSON response."
            )

        # ----------------------------------------------------
        # Validate response structure
        # ----------------------------------------------------

        try:

            content = data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError):

            raise RuntimeError(
                "LM Studio returned an unexpected response format."
            )

        if not content:

            raise RuntimeError(
                "The model returned an empty response."
            )

        return str(content).strip()


# ============================================================
# DEFAULT CLIENT
# ============================================================

_default_client = LLMClient()


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Simple function for code that doesn't need to create
    its own LLMClient instance.
    """

    return _default_client.chat(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ============================================================
# CONNECTION HELPER
# ============================================================

def check_lm_studio() -> bool:
    """
    Quickly checks whether LM Studio is available.
    """

    return _default_client.is_available()


# ============================================================
# MODEL HELPER
# ============================================================

def get_available_models() -> list[str]:
    """
    Returns models currently loaded/available through LM Studio.
    """

    return _default_client.get_models()
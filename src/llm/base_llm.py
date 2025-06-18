from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseLLM(ABC):
    """Abstract base class for Large Language Model clients."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def generate_text(
        self, prompt: str, max_tokens: int = 1500, temperature: float = 0.7, **kwargs
    ) -> str:
        """Generate text based on a given prompt."""
        pass

    @abstractmethod
    def analyze_text(self, text: str, prompt_template: str, **kwargs) -> Dict[str, Any]:
        """Analyze text using a specific prompt template to extract structured data."""
        pass

    def _prepare_prompt(self, template: str, **kwargs) -> str:
        """Helper function to format a prompt string with provided arguments."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"Missing key in prompt template: {e}. Provided kwargs: {kwargs.keys()}"
            )

    def get_provider_name(self) -> str:
        """Returns the name of the LLM provider (e.g., 'openai', 'google')."""
        return self.__class__.__name__.lower().replace("llm", "")

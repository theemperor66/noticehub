import groq
import json
from typing import Any, Dict, Optional

from src.llm.base_llm import BaseLLM
from src.config import settings
from src.utils.logger import logger


class GroqLLM(BaseLLM):
    """Groq API client implementation using groq-python library."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(
            api_key=api_key or settings.groq_api_key,
            model_name=model_name or settings.llm_model,
        )
        if not self.api_key:
            raise ValueError(
                "Groq API key is required. Set GROQ_API_KEY in .env or pass directly."
            )
        self.base_url = base_url or "https://api.groq.com"
        self.client = groq.Groq(api_key=self.api_key, base_url=self.base_url)
        logger.info(
            f"Groq LLM initialized with model: {self.model_name} using base_url: {self.base_url}"
        )

    def generate_text(
        self, prompt: str, max_tokens: int = 2000, temperature: float = 0.2, **kwargs
    ) -> str:
        """Generate text using the Groq API."""
        try:
            logger.debug(f"Sending prompt to Groq: {prompt[:100]}...")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            text_response = response.choices[0].message.content.strip()
            logger.debug(f"Received response from Groq: {text_response[:100]}...")
            return text_response
        except Exception as e:
            logger.error(f"Error during Groq text generation: {e}")
            raise

    def analyze_text(self, text: str, prompt_template: str, **kwargs) -> Dict[str, Any]:
        """Analyze text to extract structured data using Groq, expecting JSON output."""
        if "json" not in prompt_template.lower():
            logger.warning(
                "Prompt template for analyze_text does not explicitly mention JSON output. This might lead to parsing errors."
            )

        full_prompt = self._prepare_prompt(
            template=prompt_template, text_to_analyze=text, **kwargs
        )

        try:
            raw_response = self.generate_text(full_prompt)
            if raw_response.startswith("```json"):
                raw_response = raw_response.strip("```json\n")
            if raw_response.startswith("```"):
                raw_response = raw_response.strip("```\n")
            return json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from Groq: {e}")
            logger.error(f"Raw response was: {raw_response}")
            return {
                "error": "Failed to parse JSON response",
                "raw_response": raw_response,
            }
        except Exception as e:
            logger.error(f"Error during text analysis with Groq LLM: {e}")
            return {
                "error": str(e),
                "raw_response": "Error before JSON parsing or during generation",
            }

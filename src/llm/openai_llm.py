import openai
import json
from typing import Any, Dict, Optional
from src.llm.base_llm import BaseLLM
from src.config import settings
from src.utils.logger import logger


class OpenAILLM(BaseLLM):
    """OpenAI GPT client implementation."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        super().__init__(
            api_key=api_key or settings.openai_api_key,
            model_name=model_name or settings.llm_model,
        )
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY in .env or pass directly."
            )
        openai.api_key = self.api_key
        logger.info(f"OpenAI LLM initialized with model: {self.model_name}")

    def generate_text(
        self, prompt: str, max_tokens: int = 2000, temperature: float = 0.2, **kwargs
    ) -> str:
        """Generate text using the OpenAI API."""
        try:
            logger.debug(
                f"Sending prompt to OpenAI: {prompt[:100]}..."
            )  # Log snippet of prompt
            response = openai.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            text_response = response.choices[0].message.content.strip()
            logger.debug(f"Received response from OpenAI: {text_response[:100]}...")
            return text_response
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while calling OpenAI API: {e}")
            raise

    def analyze_text(self, text: str, prompt_template: str, **kwargs) -> Dict[str, Any]:
        """Analyze text to extract structured data using OpenAI, expecting JSON output."""
        # Ensure the prompt instructs the model to return JSON
        if not "json" in prompt_template.lower():
            logger.warning(
                "Prompt template for analyze_text does not explicitly mention JSON output. This might lead to parsing errors."
            )

        full_prompt = self._prepare_prompt(
            template=prompt_template, text_to_analyze=text, **kwargs
        )

        try:
            # Forcing JSON mode if available and model supports it (e.g. gpt-3.5-turbo-1106+)
            # Check your OpenAI model version for JSON mode support
            json_mode_supported_models = [
                "gpt-4-turbo-preview",
                "gpt-3.5-turbo-1106",
                "gpt-4-0125-preview",
                "gpt-4-1106-preview",
            ]
            if self.model_name in json_mode_supported_models:
                logger.info(f"Using JSON mode for model {self.model_name}")
                raw_response = self.generate_text(
                    full_prompt, response_format={"type": "json_object"}
                )
            else:
                logger.info(
                    f"Model {self.model_name} may not support JSON mode directly. Relying on prompt engineering."
                )
                raw_response = self.generate_text(full_prompt)

            # Clean the response: Sometimes models wrap JSON in ```json ... ```
            if raw_response.startswith("```json"):
                raw_response = raw_response.strip("```json\n")
            if raw_response.startswith("```"):
                raw_response = raw_response.strip("```\n")

            parsed_json = json.loads(raw_response)
            return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response from LLM: {e}")
            logger.error(f"Raw response was: {raw_response}")
            # Fallback or error handling strategy, e.g., return a dict with an error field
            return {
                "error": "Failed to parse JSON response",
                "raw_response": raw_response,
            }
        except Exception as e:
            logger.error(f"Error during text analysis with LLM: {e}")
            return {
                "error": str(e),
                "raw_response": "Error before JSON parsing or during generation",
            }


# Example Usage (for testing purposes)
if __name__ == "__main__":
    # Ensure .env is loaded if you're running this file directly
    # from dotenv import load_dotenv
    # load_dotenv()

    if not settings.openai_api_key:
        logger.error("OPENAI_API_KEY not found. Please set it in your .env file.")
    else:
        try:
            llm_client = OpenAILLM()
            sample_prompt = "What is the capital of France?"
            logger.info(f"Testing generate_text with prompt: '{sample_prompt}'")
            response_text = llm_client.generate_text(sample_prompt, max_tokens=50)
            logger.info(f"LLM Response: {response_text}")

            # Test analyze_text
            email_content_sample = """
            Subject: Urgent Maintenance Alert - Service Alpha Outage
            Dear User,
            Please be advised that Service Alpha will experience an unexpected outage starting from 
            2025-05-20 10:00 UTC until 2025-05-20 12:00 UTC due to critical system failure.
            We apologize for any inconvenience.
            The Support Team
            """

            extraction_prompt_template = """
            Extract the following information from the email content provided below. 
            Return the information as a JSON object with the following keys: 
            'service_name', 'start_time', 'end_time', 'notification_type', 'summary'.
            Ensure dates and times are in 'YYYY-MM-DD HH:MM UTC' format.
            If a field is not found, use null for its value.
            
            Email content:
            ---BEGIN EMAIL CONTENT---
            {text_to_analyze}
            ---END EMAIL CONTENT---
            
            JSON Output:
            """

            logger.info("Testing analyze_text for structured data extraction...")
            extracted_data = llm_client.analyze_text(
                email_content_sample, extraction_prompt_template
            )
            logger.info(
                f"Extracted Data (JSON): {json.dumps(extracted_data, indent=2)}"
            )

        except ValueError as ve:
            logger.error(f"Initialization error: {ve}")
        except Exception as e:
            logger.error(f"An error occurred during the LLM client test: {e}")

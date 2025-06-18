from typing import Any, Dict, Optional
import json # For the fallback analyze_text
from src.llm.base_llm import BaseLLM
from src.config import settings
from src.utils.logger import logger

# Ensure you have the google-generativeai library installed
# pip install google-generativeai

try:
    import google.generativeai as genai
except ImportError:
    logger.warning("google-generativeai library not found. GeminiLLM will not be available.")
    genai = None

class GeminiLLM(BaseLLM):
    """Google Gemini client implementation."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        super().__init__(
            api_key=api_key or settings.google_api_key,
            model_name=model_name or settings.llm_model # Ensure your .env has a GOOGLE_LLM_MODEL or similar
        )
        if not genai:
            raise ImportError("google-generativeai library is required for GeminiLLM but not installed.")
        if not self.api_key:
            raise ValueError("Google API key is required for Gemini. Set GOOGLE_API_KEY in .env or pass directly.")
        
        genai.configure(api_key=self.api_key)
        if not self.model_name:
            raise ValueError("Gemini model name is required. Set LLM_MODEL in .env or pass model_name directly.")
        # Example: model_name could be 'gemini-1.0-pro' or 'gemini-1.5-pro-latest'
        # Ensure the model name in .env or passed is compatible with Gemini API
        self.gen_model = genai.GenerativeModel(self.model_name)
        logger.info(f"Google Gemini LLM initialized with model: {self.model_name}")

    def generate_text(self, prompt: str, max_tokens: int = 2000, temperature: float = 0.7, **kwargs) -> str:
        """Generate text using the Google Gemini API."""
        if not genai:
            return "Error: google-generativeai library not available."
        try:
            logger.debug(f"Sending prompt to Gemini: {prompt[:100]}...")
            # For Gemini, configuration for generation is often done via GenerationConfig
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                # top_p=kwargs.get('top_p'), # Example of other params
                # top_k=kwargs.get('top_k')
            )
            response = self.gen_model.generate_content(prompt, generation_config=generation_config)
            text_response = response.text.strip()
            logger.debug(f"Received response from Gemini: {text_response[:100]}...")
            return text_response
        except Exception as e:
            logger.error(f"Error during Gemini text generation: {e}", exc_info=True)
            return f"Error: Could not generate text due to {type(e).__name__}"

    def extract_notification_data(self, email_body: str, max_tokens: int = 2048, temperature: float = 0.5) -> str:
        """Extracts structured notification data from email body using a specific prompt.

        Args:
            email_body: The plain text content of the email.
            max_tokens: Maximum tokens for the response.
            temperature: The temperature for generation.

        Returns:
            A string, which is expected to be a JSON object containing the extracted data.
        """
        if not genai:
            return '{"error": "google-generativeai library not available."}'

        prompt = f"""Analyze the following email notification content and extract the specified information.
Return the information as a VALID JSON object. Do not include any explanatory text before or after the JSON.

The JSON object should have the following fields:
- "time_window": An object with "start_time" and "end_time". Dates/times should be in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS+/-HH:MM) if possible. If only a date is available, use YYYY-MM-DD. If specific times are not mentioned, try to infer reasonable defaults (e.g., start of day, end of day for full-day maintenances) or use null if truly unknown.
- "affected_services": A list of strings, where each string is an affected service name. Be as specific as possible from the text.
- "notification_type": A string representing the type of notification. Choose from: "planned_maintenance", "unplanned_outage", "emergency_maintenance", "service_update", "security_bulletin", "general_information", "other". If unsure, use "other".
- "severity": A string representing the perceived severity. Choose from: "critical", "high", "medium", "low", "informational", "unknown". This might be subjective; use "unknown" if not clearly stated or inferable.
- "summary": A concise, one to two sentence summary of the core message of the notification, extracted or generated from the email content.

Example of a desired JSON output format:
{{ "time_window": {{ "start_time": "2024-05-20T08:00:00Z", "end_time": "2024-05-20T12:00:00Z" }}, "affected_services": ["Payment Gateway API", "Customer Portal"], "notification_type": "planned_maintenance", "severity": "medium", "summary": "Scheduled maintenance for Payment Gateway and Customer Portal to improve performance."}}

If a field cannot be determined from the text, use null for its value (e.g., "end_time": null) or an empty list for "affected_services" if none are mentioned.
Ensure the output is ONLY the JSON object.

Email Content to Analyze:
{email_body}

Make sure to return only the JSON object.
""" # Ensure this closing triple quote is indented by 8 spaces

        try:
            logger.debug(f"Sending data extraction prompt to Gemini. Email body length: {len(email_body)}")
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=temperature
            )
            response = self.gen_model.generate_content(prompt, generation_config=generation_config)
            json_response_string = response.text.strip()
            
            if not (json_response_string.startswith('{') and json_response_string.endswith('}')):
                logger.warning(f"Gemini response does not appear to be a JSON object. Raw response: {json_response_string[:200]}...")

            logger.debug(f"Received data extraction response from Gemini: {json_response_string[:200]}...")
            return json_response_string
        except Exception as e:
            logger.error(f"Error during Gemini data extraction: {e}", exc_info=True)
            # Check for specific Gemini API feedback if available
            if hasattr(e, 'response') and hasattr(e.response, 'prompt_feedback') and e.response.prompt_feedback.block_reason:
                 logger.error(f"Prompt blocked by Gemini: {e.response.prompt_feedback.block_reason}")
                 return f'{{ "error": "Prompt blocked by Gemini: {e.response.prompt_feedback.block_reason}" }}'
            return f'{{ "error": "Could not extract data due to {type(e).__name__}: {str(e)}" }}'

    def analyze_text(self, text: str, prompt_template: str, **kwargs) -> Dict[str, Any]:
        """(Fallback) Analyze text using a specific prompt template to extract structured data.
           This is a more generic version. For notification extraction, use extract_notification_data.
        """
        logger.warning("analyze_text is being used as a fallback for GeminiLLM. For specific notification extraction, prefer extract_notification_data.")
        if not genai:
            return {"error": "google-generativeai library not available."}

        custom_prompt = self._prepare_prompt(prompt_template, text=text, **kwargs)
        response_str = self.generate_text(custom_prompt) # Uses the existing generate_text method
        
        try:
            # Attempt to parse the response as JSON. This is optimistic.
            return json.loads(response_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse analyze_text response from Gemini as JSON. Response: {response_str}")
            return {"error": "Failed to parse response as JSON from analyze_text", "raw_response": response_str}

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Ensure .env is loaded
    from dotenv import load_dotenv
    load_dotenv()

    if not settings.google_api_key:
        logger.error("GOOGLE_API_KEY not found. Please set it in your .env file to test GeminiLLM.")
    elif not genai:
        logger.error("google-generativeai library not installed. Cannot test GeminiLLM.")
    else:
        try:
            # Make sure your .env has LLM_MODEL set to your desired Gemini model (e.g., 'gemini-1.0-pro')
            llm_client = GeminiLLM() # Uses LLM_MODEL from .env via settings
            
            sample_prompt = "Tell me a fun fact about the Roman Empire."
            logger.info(f"Testing Gemini generate_text with prompt: '{sample_prompt}'")
            response_text = llm_client.generate_text(sample_prompt, max_tokens=100)
            logger.info(f"Gemini LLM Response: {response_text}")

            # Test analyze_text (similar to OpenAI example)
            email_content_sample = """
            Subject: Service Beta - Scheduled Maintenance
            Dear Valued Customer,
            Service Beta will undergo scheduled maintenance on 2025-06-15 from 02:00 AM to 04:00 AM PST.
            This is to improve performance and reliability.
            Thank you for your understanding.
            Customer Support
            """
            
            extraction_prompt_template = """
            Extract service_name, start_time, end_time, notification_type, and a brief summary 
            from the following email content. Return as a JSON object. 
            Convert times to UTC if a timezone is specified. Default to UTC if not specified. 
            Use 'YYYY-MM-DD HH:MM UTC' format for times. Use 'maintenance' or 'outage' for notification_type.
            
            Email content:
            {text}
            
            JSON Output:
            """
            
            logger.info("Testing Gemini analyze_text for structured data extraction...")
            extracted_data = llm_client.analyze_text(email_content_sample, extraction_prompt_template)
            # import json # make sure json is imported for the example print # Already imported at top level
            logger.info(f"Gemini Extracted Data (JSON): {json.dumps(extracted_data, indent=2)}")

        except ValueError as ve:
            logger.error(f"Initialization error: {ve}")
        except Exception as e:
            logger.error(f"An error occurred during the Gemini LLM client test: {e}")

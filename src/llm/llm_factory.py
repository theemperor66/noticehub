from src.llm.base_llm import BaseLLM
from src.llm.openai_llm import OpenAILLM
from src.llm.gemini_llm import GeminiLLM # Assuming you might add this
from src.config import settings
from src.utils.logger import logger

class LLMFactory:
    @staticmethod
    def get_llm_client(provider_name: str = None, api_key: str = None, model_name: str = None) -> BaseLLM:
        """Factory method to get an LLM client based on the provider name."""
        provider = provider_name or settings.llm_provider.lower()
        
        logger.info(f"Attempting to create LLM client for provider: {provider}")

        if provider == "openai":
            return OpenAILLM(
                api_key=api_key or settings.openai_api_key,
                model_name=model_name or settings.llm_model
            )
        elif provider == "google" or provider == "gemini":
            # Ensure you have GOOGLE_API_KEY and potentially a specific GOOGLE_LLM_MODEL in .env
            # For Gemini, model_name might be 'gemini-pro', 'gemini-1.5-pro-latest' etc.
            # The llm_model from settings might be generic like 'gpt-3.5-turbo' 
            # so you might need a separate setting for Gemini's model or pass it explicitly.
            gemini_model = model_name # Or a specific setting like settings.google_llm_model
            if provider == "gemini" and not gemini_model and "gemini" not in (settings.llm_model or ""):
                 # Default to a common gemini model if 'gemini' is provider but no specific model given
                 gemini_model = 'gemini-pro' 
            elif not gemini_model: # if provider is 'google' and model is not specified
                gemini_model = settings.llm_model # Use general llm_model if it seems like a Gemini one

            try:
                return GeminiLLM(
                    api_key=api_key or settings.google_api_key,
                    model_name=gemini_model 
                )
            except ImportError as e:
                logger.error(f"Failed to import GeminiLLM: {e}. Make sure 'google-generativeai' is installed.")
                raise
            except ValueError as e:
                 logger.error(f"ValueError for GeminiLLM: {e}. Check API key and model name.")
                 raise

        # Add other providers here as elif blocks
        # elif provider == "anthropic":
        #     return AnthropicLLM(api_key=api_key or settings.anthropic_api_key, model_name=model_name or settings.llm_model)
        
        else:
            logger.error(f"Unsupported LLM provider: {provider}")
            raise ValueError(f"Unsupported LLM provider: {provider}. Supported: 'openai', 'google'/'gemini'.")

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Load .env variables for testing
    # from dotenv import load_dotenv
    # load_dotenv()

    logger.info("Testing LLMFactory...")

    # Test OpenAI client creation
    if settings.openai_api_key:
        try:
            logger.info("Attempting to create OpenAI client...")
            openai_client = LLMFactory.get_llm_client(provider_name="openai")
            logger.info(f"Successfully created OpenAI client: {openai_client.get_provider_name()}, Model: {openai_client.model_name}")
            # You could add a simple generation test here if desired
            # logger.info(f"OpenAI test: {openai_client.generate_text('Say hi', max_tokens=10)}")
        except Exception as e:
            logger.error(f"Failed to create or test OpenAI client: {e}")
    else:
        logger.warning("OpenAI API key not set. Skipping OpenAI client test in factory.")

    # Test Google/Gemini client creation
    if settings.google_api_key:
        try:
            logger.info("Attempting to create Google/Gemini client...")
            # Assuming llm_provider in .env might be 'google' and llm_model='gemini-pro'
            # Or explicitly:
            # gemini_client = LLMFactory.get_llm_client(provider_name="gemini", model_name="gemini-pro")
            gemini_client = LLMFactory.get_llm_client(provider_name="google") # Will use settings.llm_provider and settings.llm_model
            logger.info(f"Successfully created Google/Gemini client: {gemini_client.get_provider_name()}, Model: {gemini_client.model_name}")
            # logger.info(f"Gemini test: {gemini_client.generate_text('Say hello', max_tokens=10)}")
        except Exception as e:
            logger.error(f"Failed to create or test Google/Gemini client: {e}")
    else:
        logger.warning("Google API key not set. Skipping Google/Gemini client test in factory.")

    # Test with an unsupported provider
    try:
        logger.info("Attempting to create an unsupported client...")
        unsupported_client = LLMFactory.get_llm_client(provider_name="unsupported_provider")
    except ValueError as e:
        logger.info(f"Correctly caught error for unsupported provider: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when testing unsupported provider: {e}")

import os
import logging
import httpx
import openai
import anthropic
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

# It's good practice to configure logging at the start of your file
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class APIClient:
    """A client to manage API calls to various AI providers."""
    def __init__(self):
        """
        Initializes API clients from environment variables.
        Fails gracefully if a key is not found, allowing use of other providers.
        """
        # --- Google ---
        try:
            google_api_key = os.environ.get("GOOGLE_API_KEY")
            if google_api_key:
                genai.configure(api_key=google_api_key)
                self.genai = genai
                logger.info("Google API client configured.")
            else:
                self.genai = None
                logger.warning("GOOGLE_API_KEY not found. Google provider is disabled.")
        except Exception as e:
            logger.error(f"Failed to configure Google API client: {e}")
            self.genai = None

        # --- OpenAI ---
        try:
            if os.environ.get("OPENAI_API_KEY"):
                self.openai_client = openai.OpenAI() # The client reads the key automatically
                logger.info("OpenAI API client configured.")
            else:
                self.openai_client = None
                logger.warning("OPENAI_API_KEY not found. OpenAI provider is disabled.")
        except Exception as e:
            logger.error(f"Failed to configure OpenAI API client: {e}")
            self.openai_client = None

        # --- Anthropic ---
        try:
            if os.environ.get("ANTHROPIC_API_KEY"):
                self.anthropic_client = anthropic.Anthropic() # The client reads the key automatically
                logger.info("Anthropic API client configured.")
            else:
                self.anthropic_client = None
                logger.warning("ANTHROPIC_API_KEY not found. Anthropic provider is disabled.")
        except Exception as e:
            logger.error(f"Failed to configure Anthropic API client: {e}")
            self.anthropic_client = None

        # --- X.AI (Grok) ---
        self.xai_api_key = os.environ.get("GROK_API_KEY") # Using GROK_API_KEY to match the SDK
        self.xai_base_url = "https://api.x.ai/v1"
        if self.xai_api_key:
            logger.info("X.AI API key loaded.")
        else:
            logger.warning("GROK_API_KEY not found. X.AI provider is disabled.")


    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def call_model(self, provider, model_name, prompt):
        """
        Calls the specified AI model provider with the given prompt, with retries.
        """
        logger.info(f"Calling provider: '{provider}', model: '{model_name}'")

        if provider == 'google':
            if not self.genai:
                raise ValueError("Google API is not configured. Check GOOGLE_API_KEY.")
            model = self.genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response.text

        elif provider == 'openai':
            if not self.openai_client:
                raise ValueError("OpenAI API is not configured. Check OPENAI_API_KEY.")
            response = self.openai_client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that generates SQL queries for retail analytics."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            return response.choices[0].message.content

        elif provider == 'anthropic':
            if not self.anthropic_client:
                raise ValueError("Anthropic API is not configured. Check ANTHROPIC_API_KEY.")
            message = self.anthropic_client.messages.create(
                model=model_name,
                max_tokens=2000,
                temperature=0.1,
                system="You are a helpful assistant that generates SQL queries.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text

        elif provider == 'xai':
            if not self.xai_api_key:
                raise ValueError("X.AI API is not configured. Check GROK_API_KEY.")
            headers = {
                "Authorization": f"Bearer {self.xai_api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that generates SQL queries."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 2000
            }
            try:
                with httpx.Client() as client:
                    response = client.post(
                        f"{self.xai_base_url}/chat/completions",
                        headers=headers,
                        json=data,
                        timeout=30.0
                    )
                response.raise_for_status() # Raises an exception for 4XX/5XX responses
                result = response.json()
                return result['choices'][0]['message']['content']
            except httpx.RequestError as e:
                logger.error(f"An error occurred while requesting from X.AI API: {e}")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"X.AI API returned an error response: {e.response.status_code} - {e.response.text}")
                raise

        else:
            raise ValueError(f"Unknown or unsupported provider: {provider}")

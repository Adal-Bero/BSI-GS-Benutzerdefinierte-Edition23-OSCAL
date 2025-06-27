import asyncio
import json
import logging
from typing import Dict, Any

import vertexai
from jsonschema import validate, ValidationError
from vertexai.generative_models import (
    GenerativeModel,
    GenerationConfig,
    FinishReason,
)

from config import GCP_PROJECT_ID

# Logger setup is handled in the main script, we just get it here.
logger = logging.getLogger(__name__)

# --- Model Configuration ---
MODEL_NAME = "gemini-1.5-pro-001"
MAX_OUTPUT_TOKENS = 8192
RETRY_ATTEMPTS = 5
MAX_CONCURRENT_REQUESTS = 10

# Initialize Vertex AI
try:
    vertexai.init(project=GCP_PROJECT_ID)
    logger.info("Vertex AI initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize Vertex AI: {e}", exc_info=True)
    raise


def load_prompt_and_schema(prompt_path: str, schema_path: str) -> tuple[str, dict]:
    """Loads a prompt and a JSON schema from local files."""
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt = f.read()
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        return prompt, schema
    except FileNotFoundError as e:
        logger.error(f"Could not find a required file: {e.filename}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Could not parse JSON schema file at {schema_path}: {e}")
        raise


# Load prompt and schema once on module import
PRACTICE_PROMPT, PRACTICE_STUB_SCHEMA = load_prompt_and_schema(
    "prompts/practice_prompt.txt",
    "schemas/practice_stub.schema.json"
)


async def generate_with_retry(model: GenerativeModel, prompt: str, generation_config: GenerationConfig) -> Any:
    """Makes a request to the Gemini model with exponential backoff retry logic."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = await model.generate_content_async(
                contents=prompt,
                generation_config=generation_config,
            )

            if not response.candidates:
                finish_reason_str = response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else "UNKNOWN"
                logger.warning(f"Attempt {attempt + 1}: No candidates returned. Finish Reason: {finish_reason_str}")
                raise ValueError(f"No candidates returned from the model. Reason: {finish_reason_str}")

            finish_reason = response.candidates[0].finish_reason
            if finish_reason != FinishReason.OK:
                logger.warning(f"Attempt {attempt + 1}: Model finished with non-OK reason: {finish_reason.name}")
                if finish_reason in [FinishReason.SAFETY, FinishReason.RECITATION]:
                     logger.error(f"Generation stopped permanently due to {finish_reason.name}. Cannot retry.")
                     return None
                raise ValueError(f"Model returned a non-OK finish reason: {finish_reason.name}")

            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-4].strip()
            
            return json.loads(raw_text)

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Attempt {attempt + 1}/{RETRY_ATTEMPTS}: Failed to process model response. Error: {e}")
            if attempt + 1 == RETRY_ATTEMPTS:
                logger.error("All retry attempts failed to get a valid response.")
                return None
            await asyncio.sleep(2 ** attempt)

        except Exception as e:
            logger.error(f"Unexpected error during model generation on attempt {attempt + 1}: {e}", exc_info=True)
            if attempt + 1 == RETRY_ATTEMPTS:
                logger.error("All retry attempts failed due to unexpected errors.")
                return None
            await asyncio.sleep(2 ** attempt)
    return None


async def generate_practice_for_control(control: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Generates the 'practice' part for a single control by classifying it.

    Args:
        control: The control object dictionary.

    Returns:
        The generated and validated 'practice' part as a dictionary, or None on failure.
    """
    control_id = control.get("id", "Unknown ID")
    try:
        # Pre-filter data to create a minimal input for the model
        control_stub = {
            "id": control_id,
            "title": control.get("title"),
        }
        
        # Prepare the prompt with the stub and the schema
        prompt = (f"{PRACTICE_PROMPT}\n\n"
                  f"Control Data:\n{json.dumps(control_stub, indent=2)}\n\n"
                  f"Schema for your JSON response:\n{json.dumps(PRACTICE_STUB_SCHEMA, indent=2)}")

        # Configure and call the model
        model = GenerativeModel(MODEL_NAME)
        generation_config = GenerationConfig(
            max_output_tokens=MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
            temperature=0.1, # Lower temperature for classification
        )

        logger.debug(f"Generating practice for control ID: {control_id}")
        model_output = await generate_with_retry(model, prompt, generation_config)

        if not model_output:
            logger.error(f"Failed to get a valid response from model for control ID: {control_id}")
            return None

        # Validate the output against the stub schema
        validate(instance=model_output, schema=PRACTICE_STUB_SCHEMA)
        logger.info(f"Successfully generated and validated practice for control ID: {control_id}")

        return model_output

    except ValidationError as e:
        logger.error(f"Schema validation failed for control ID {control_id}: {e.message}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error in generate_practice_for_control for ID {control_id}: {e}", exc_info=True)
        return None
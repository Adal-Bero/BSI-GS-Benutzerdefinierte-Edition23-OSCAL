import asyncio
import json
import logging
import os
import re
import sys
import textwrap
import uuid
from typing import Any, Dict, List, Optional

import jsonschema

from google.cloud import storage

from google import genai
from google.genai.types import (
    GenerateContentConfig,
    GoogleSearch,
    HttpOptions,
    Tool,
)


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

class Config:
    """Load & validate all configuration from environment variables."""

    def __init__(self):
        # Core GCP
        self.gcp_project_id: str = self._req("GCP_PROJECT_ID")

        # GCS paths
        self.bucket_name: str = self._req("BUCKET_NAME")
        self.source_prefix: str = self._req("SOURCE_PREFIX")
        self.output_prefix: str = self._req("OUTPUT_PREFIX")
        self.existing_json_gcs_path: str = self._req("EXISTING_JSON_GCS_PATH")

        # Other flags
        self.test_mode: bool = os.getenv("TEST", "false").lower() == "true"

        # Derived
        self.output_filename = os.path.basename(self.existing_json_gcs_path)
        self.output_gcs_path = os.path.join(self.output_prefix, self.output_filename)

        logging.info("Configuration loaded.")
        if self.test_mode:
            logging.warning("--- TEST MODE ENABLED ---")

    @staticmethod
    def _req(var: str) -> str:
        val = os.getenv(var)
        if not val:
            logging.error(f"FATAL: Required env var '{var}' is missing.")
            sys.exit(1)
        return val


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if root.hasHandlers():
        root.handlers.clear()

    h = logging.StreamHandler(sys.stdout)
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    root.addHandler(h)

    for noisy in ("google.auth", "urllib3", "google.api_core", "google.genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# -----------------------------------------------------------------------------
# Cloud Storage helpers
# -----------------------------------------------------------------------------

def download_json_from_gcs(client: storage.Client, bucket: str, path: str) -> Optional[Dict]:
    try:
        blob = client.bucket(bucket).blob(path)
        if not blob.exists():
            logging.error(f"GCS file not found: gs://{bucket}/{path}")
            return None
        return json.loads(blob.download_as_string())
    except Exception as exc:
        logging.error(f"Failed downloading gs://{bucket}/{path}: {exc}")
        return None


def upload_json_to_gcs(client: storage.Client, bucket: str, path: str, data: Dict):
    try:
        client.bucket(bucket).blob(path).upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json"
        )
        logging.info(f"Uploaded JSON → gs://{bucket}/{path}")
    except Exception as exc:
        logging.error(f"Upload failed (gs://{bucket}/{path}): {exc}")
        raise


def list_gcs_blobs(client: storage.Client, bucket: str, prefix: str) -> List[storage.Blob]:
    return [b for b in client.list_blobs(bucket, prefix=prefix) if b.name.endswith(".json")]


# -----------------------------------------------------------------------------
# OSCAL helpers
# -----------------------------------------------------------------------------

def find_item_by_id_recursive(node: Any, target_id: str) -> Optional[Dict]:
    if isinstance(node, dict):
        if node.get("id") == target_id:
            return node
        for val in node.values():
            res = find_item_by_id_recursive(val, target_id)
            if res:
                return res
    elif isinstance(node, list):
        for sub in node:
            res = find_item_by_id_recursive(sub, target_id)
            if res:
                return res
    return None


def find_parent_baustein(node: Any, control_id: str) -> Optional[Dict]:
    if isinstance(node, dict):
        if node.get("class") == "baustein" and any(c.get("id") == control_id for c in node.get("controls", [])):
            return node
        for val in node.values():
            res = find_parent_baustein(val, control_id)
            if res:
                return res
    elif isinstance(node, list):
        for sub in node:
            res = find_parent_baustein(sub, control_id)
            if res:
                return res
    return None


def get_prose_from_control(control: Dict) -> List[Dict[str, str]]:
    prose: List[Dict[str, str]] = []
    for ml_part in control.get("parts", []):
        if ml_part.get("name") == "maturity-level-description":
            for content in ml_part.get("parts", []):
                if "prose" in content and "id" in content:
                    prose.append({"part_id": content["id"], "prose": content["prose"]})
    return prose


def ensure_prose_part_ids(catalog: Dict):
    added = 0
    for group in catalog.get("catalog", {}).get("groups", []):
        for baustein in group.get("groups", []):
            if baustein.get("class") != "baustein":
                continue
            for ctrl in baustein.get("controls", []):
                for ml_part in ctrl.get("parts", []):
                    if ml_part.get("name") == "maturity-level-description":
                        for content in ml_part.get("parts", []):
                            if "prose" in content and "id" not in content and "name" in content:
                                content["id"] = f"{ml_part['id']}-{content['name']}"
                                added += 1
    logging.info(f"Sanitised prose IDs → added {added} missing IDs.")


# -----------------------------------------------------------------------------
# Gemini helpers
# -----------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    return m.group(1) if m else text


async def get_gemini_enrichment(
    input_stub: Dict,
    prompt_template: str,
    output_schema: Dict,
) -> Optional[Dict]:

        full_prompt = textwrap.dedent(f"""
        {prompt_template}

        Here is the JSON object with the data to analyze:
        ```json
        {json.dumps(input_stub, indent=2, ensure_ascii=False)}
        ```

        Your response MUST be a single JSON object that validates against this schema:
        ```json
        {json.dumps(output_schema, indent=2)}
        ```
        """)

        for attempt in range(5):
            try:
                resp = await client.aio.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=full_prompt,
                    config=GenerateContentConfig(
                        response_mime_type="application/json",
                        tools=[
                            # Use Google Search Tool
                            Tool(google_search=GoogleSearch())
                        ],
                    ),
                )

                if resp.candidates[0].finish_reason.name not in {"STOP", "MAX_TOKENS"}:
                    raise RuntimeError(f"finish_reason={resp.candidates[0].finish_reason.name}")

                payload = json.loads(_extract_json(resp.text))
                jsonschema.validate(payload, output_schema)
                return payload
            except Exception as exc:
                logging.warning(f"Gemini attempt {attempt + 1}/5 failed: {exc}")
                if attempt == 4:
                    return None
                await asyncio.sleep(2 ** attempt)

        return None


# -----------------------------------------------------------------------------
# Control‑level coroutine
# -----------------------------------------------------------------------------

async def process_control(
    control_id: str,
    catalog: Dict,
    prompt: str,
    schema: Dict,
    sem: asyncio.Semaphore,
    lock: asyncio.Lock,
) -> List[Dict]:
    async with sem:
        ctrl = find_item_by_id_recursive(catalog, control_id)
        baustein = find_parent_baustein(catalog.get("catalog"), control_id)
        if not ctrl or not baustein:
            logging.warning(f"Control '{control_id}' not found → skipped.")
            return []

        prose = get_prose_from_control(ctrl)
        if not prose:
            return []

        stub = {
            "baustein_context": {"id": baustein["id"], "title": baustein["title"]},
            "control_context": {"id": ctrl["id"], "title": ctrl["title"]},
            "prose_to_evaluate": prose,
        }

        result = await get_gemini_enrichment(stub, prompt, schema)
        if not result:
            return []

        async with lock:
            for item in result.get("enriched_prose", []):
                part = find_item_by_id_recursive(catalog, item["part_id"])
                if part:
                    part["prose_qs"] = item["prose_qs"]

            new_controls = result.get("suggested_new_controls", [])
            if new_controls:
                baustein.setdefault("controls", []).extend(new_controls)
            return new_controls


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------

async def main():
    cfg = Config()
    setup_logging()

    # Clients & model setup
    try:
        storage_client = storage.Client(project=cfg.gcp_project_id)
        # Client is now global, no need to pass it all the time
        global client
        client = genai.Client(
            http_options=HttpOptions(api_version="v1"),
            vertexai=True,
            project=cfg.gcp_project_id,
            location='us-central1'
        )

    except Exception as exc:
        logging.error(f"Client init failed: {exc}")
        return

    # --------------------------------------------------------------
    # Load local assets (prompts & schemas)
    # --------------------------------------------------------------
    try:
        with open("prompts/quality_check_prompt.txt", "r", encoding="utf-8") as fp:
            prompt_template = fp.read()
        with open("schemas/gemini_output_stub_schema.json", "r", encoding="utf-8") as fp:
            output_schema = json.load(fp)
        with open("schemas/bsi_gk_2023_oscal_schema.json", "r", encoding="utf-8") as fp:
            final_schema = json.load(fp)
    except FileNotFoundError as exc:
        logging.error(f"Missing asset: {exc}")
        return

    # --------------------------------------------------------------
    # Load primary catalog
    # --------------------------------------------------------------
    catalog = download_json_from_gcs(storage_client, cfg.bucket_name, cfg.existing_json_gcs_path)
    if not catalog:
        logging.error("Could not load source catalog.")
        return

    ensure_prose_part_ids(catalog)

    component_blobs = list_gcs_blobs(storage_client, cfg.bucket_name, cfg.source_prefix)
    if cfg.test_mode:
        component_blobs = component_blobs[:3]
        logging.warning(f"TEST MODE: processing {len(component_blobs)} component file(s)")

    sem = asyncio.Semaphore(10)
    lock = asyncio.Lock()

    for blob in component_blobs:
        logging.info(f"--- Component {blob.name} ---")
        comp_data = download_json_from_gcs(storage_client, cfg.bucket_name, blob.name)
        if comp_data is None:
            continue

        tasks: List[asyncio.Task] = []
        for component in comp_data.get("component-definition", {}).get("components", []):
            for impl in component.get("control-implementations", []):
                control_ids = [req["control-id"] for req in impl.get("implemented-requirements", [])]
                if cfg.test_mode:
                    control_ids = control_ids[: max(1, len(control_ids) // 10)]
                for cid in control_ids:
                    task = asyncio.create_task(
                        
                        process_control(cid, catalog, prompt_template, output_schema, sem, lock)
                    )
                    tasks.append(task)

        if not tasks:
            logging.info("No controls to process in component — skipped.")
            continue

        results = await asyncio.gather(*tasks)
        new_controls = [ctrl for sub in results for ctrl in sub]

        if new_controls:
            logging.info(f"Adding {len(new_controls)} new controls to component {blob.name}")
            try:
                first_impl = comp_data["component-definition"]["components"][0]["control-implementations"][0]
                first_impl.setdefault("implemented-requirements", [])
                for nc in new_controls:
                    first_impl["implemented-requirements"].append({
                        "uuid": str(uuid.uuid4()),
                        "control-id": nc["id"],
                        "description": "AI-suggested control addressing identified gap."
                    })
                out_path = os.path.join(cfg.output_prefix, os.path.basename(blob.name))
                upload_json_to_gcs(storage_client, cfg.bucket_name, out_path, comp_data)
            except (KeyError, IndexError) as exc:
                logging.error(f"Failed to add new controls to component {blob.name}: {exc}")
        else:
            logging.info("No new controls generated for this component.")

    # --------------------------------------------------------------
    # Validate & upload final catalog
    # --------------------------------------------------------------
    logging.info("Validating final catalog…")
    try:
        jsonschema.validate(instance=catalog, schema=final_schema)
        logging.info("Final catalog valid.")
    except jsonschema.exceptions.ValidationError as exc:
        logging.error(f"FATAL: Final catalog invalid: {exc.message}")
        return

    upload_json_to_gcs(storage_client, cfg.bucket_name, cfg.output_gcs_path, catalog)
    logging.info("--- Pipeline finished successfully ---")


if __name__ == "__main__":
    asyncio.run(main())

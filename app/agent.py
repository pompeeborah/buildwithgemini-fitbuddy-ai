# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import re
import requests
from zoneinfo import ZoneInfo
from google import genai
from google.cloud import firestore
from google.cloud import storage

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .a2ui_utils import a2ui_callback

# Hardcoded constants (required for Agent Platform compatibility)
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-e82d983c2fc0"
STORAGE_BUCKET_NAME = "qwiklabs-gcp-02-e82d983c2fc0-static-assets-bucket"

# Load agent engine resource name from deployment_metadata.json if available
agent_engine_resource_name = None
metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
if os.path.exists(metadata_path):
    try:
        with open(metadata_path, "r") as f:
            meta = json.load(f)
            agent_engine_resource_name = meta.get("remote_agent_runtime_id")
    except Exception:
        pass

if not agent_engine_resource_name:
    agent_engine_resource_name = "projects/74511823636/locations/us-east1/reasoningEngines/2093415163704115200"

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)




def search_exercises(target_muscle: str = "", category: str = "") -> list[dict]:
    """Search the exercise catalog stored in Firestore by target muscle or category.

    Args:
        target_muscle: Optional filter for target muscle group (e.g., 'Chest', 'Legs', 'Back').
        category: Optional filter for category (e.g., 'Strength', 'Cardio', 'Calisthenics').

    Returns:
        A list of dictionaries containing exercise details.
    """
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    query_ref = db.collection("exercises")
    docs = query_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        match_muscle = not target_muscle or target_muscle.lower() in data.get("target_muscle", "").lower()
        match_category = not category or category.lower() in data.get("category", "").lower()
        if match_muscle and match_category:
            results.append(data)
    return results


def add_exercise(name: str, category: str, target_muscle: str, default_sets: int = 3, default_reps: int = 10, description: str = "") -> str:
    """Add a new exercise doc to the Firestore exercise catalog.

    Args:
        name: Name of the exercise (e.g., 'Incline Dumbbell Press').
        category: Category of the exercise (e.g., 'Strength', 'Cardio').
        target_muscle: Primary muscle targeted (e.g., 'Chest', 'Shoulders').
        default_sets: Default recommended sets.
        default_reps: Default recommended reps per set.
        description: Description or form tips for the exercise.

    Returns:
        A string confirming successful creation of the exercise in Firestore.
    """
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    doc_id = name.lower().replace(" ", "_").replace("-", "_")
    doc_ref = db.collection("exercises").document(doc_id)
    exercise_data = {
        "id": doc_id,
        "name": name,
        "category": category,
        "target_muscle": target_muscle,
        "default_sets": default_sets,
        "default_reps": default_reps,
        "description": description,
    }
    doc_ref.set(exercise_data)
    return f"Successfully added exercise '{name}' ({doc_id}) to Firestore exercise catalog!"


def calculate_training_metrics(weight_lbs: float, reps: int, exercise_name: str = "Exercise") -> dict:
    """Calculate estimated 1RM (One Rep Max), warm-up weight progression, and training targets based on recent performance.

    Args:
        weight_lbs: Weight lifted in pounds (e.g. 185.0).
        reps: Repetitions completed (e.g. 8).
        exercise_name: Optional name of the exercise being calculated.

    Returns:
        A dictionary with estimated 1RM, warm-up set weights, and target weights for strength vs hypertrophy.
    """
    if reps <= 0 or weight_lbs <= 0:
        return {"error": "Weight and reps must be positive numbers."}

    # Epley 1RM formula: 1RM = w * (1 + r / 30)
    estimated_1rm = round(weight_lbs * (1.0 + reps / 30.0), 1)

    warmup_sets = [
        {"set": 1, "percentage": "50%", "weight_lbs": round(estimated_1rm * 0.50, 1), "reps": 8},
        {"set": 2, "percentage": "70%", "weight_lbs": round(estimated_1rm * 0.70, 1), "reps": 5},
        {"set": 3, "percentage": "85%", "weight_lbs": round(estimated_1rm * 0.85, 1), "reps": 3},
    ]

    training_zones = {
        "strength_heavy_3_to_5_reps": round(estimated_1rm * 0.87, 1),
        "hypertrophy_8_to_12_reps": round(estimated_1rm * 0.75, 1),
        "endurance_15_plus_reps": round(estimated_1rm * 0.60, 1),
    }

    return {
        "exercise": exercise_name,
        "input_weight_lbs": weight_lbs,
        "input_reps": reps,
        "estimated_1rm_lbs": estimated_1rm,
        "warmup_progression": warmup_sets,
        "training_zone_targets_lbs": training_zones,
    }


def fetch_online_exercise_info(term: str = "") -> list[dict]:
    """Fetch live public exercise data from the Wger open REST API.

    Args:
        term: Optional search term to filter exercise name or category (e.g., 'Kettlebell', 'Squat', 'Abs').

    Returns:
        A list of exercise dictionaries fetched from the public Wger API.
    """
    # Optional API key read from environment variable if configured
    api_key = os.getenv("WGER_API_KEY", "")

    url = "https://wger.de/api/v2/exerciseinfo/?limit=20"
    headers = {"User-Agent": "FitBuddyAI/1.0"}
    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            translations = item.get("translations", [])
            name = translations[0].get("name", "") if translations else ""
            desc_raw = translations[0].get("description", "") if translations else ""
            desc = re.sub(r"<[^<]+?>", "", desc_raw).strip()
            category = item.get("category", {}).get("name", "General")
            muscles = [m.get("name_en") or m.get("name") for m in item.get("muscles", [])]
            equipment = [e.get("name") for e in item.get("equipment", [])]

            if not term or term.lower() in name.lower() or term.lower() in category.lower():
                results.append({
                    "name": name,
                    "category": category,
                    "target_muscles": muscles,
                    "equipment": equipment,
                    "description": desc,
                })
        return results[:5]
    except Exception as e:
        return [{"error": f"Failed to fetch public exercise info: {str(e)}"}]


def geocode_address(address: str) -> dict:
    """Convert an address string into geographic coordinates (latitude and longitude) using the Geocoding API REST endpoint.

    Args:
        address: The location address to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'San Francisco, CA').

    Returns:
        A dictionary containing formatted_address, latitude, and longitude.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(address)}&key={api_key}"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            top_res = data["results"][0]
            loc = top_res["geometry"]["location"]
            return {
                "address": address,
                "formatted_address": top_res.get("formatted_address"),
                "latitude": loc["lat"],
                "longitude": loc["lng"],
            }
        return {"error": f"Geocoding failed with status: {data.get('status')}"}
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}


def find_nearby_places(place_type: str = "gym", address: str = "", latitude: float = 0.0, longitude: float = 0.0, radius_meters: float = 3000.0) -> list[dict]:
    """Find nearby places of a given type using Google Places API (New) REST endpoint.

    Args:
        place_type: Type of place to search for (e.g. 'gym', 'park', 'sports_complex').
        address: Optional address location (e.g., 'San Francisco, CA'). If provided, it is geocoded to obtain coordinates.
        latitude: Latitude coordinate (used if address is not provided).
        longitude: Longitude coordinate (used if address is not provided).
        radius_meters: Search radius in meters (default is 3000.0).

    Returns:
        A list of place dictionaries containing key fields (name, address, location).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is not configured."}]

    lat, lng = latitude, longitude
    if address:
        geo = geocode_address(address)
        if "latitude" in geo and "longitude" in geo:
            lat, lng = geo["latitude"], geo["longitude"]

    if lat == 0.0 and lng == 0.0:
        return [{"error": "Please provide a valid address or non-zero latitude and longitude."}]

    places_url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 5,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_meters,
            }
        },
    }

    try:
        resp = requests.post(places_url, json=payload, headers=headers, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for p in data.get("places", []):
            name = p.get("displayName", {}).get("text", "")
            formatted_address = p.get("formattedAddress", "")
            loc = p.get("location", {})
            results.append({
                "name": name,
                "address": formatted_address,
                "location": {
                    "latitude": loc.get("latitude"),
                    "longitude": loc.get("longitude"),
                },
            })
        return results
    except Exception as e:
        return [{"error": f"Failed to call Places API (New): {str(e)}"}]


async def generate_workout_image(prompt: str, tool_context: ToolContext) -> str:
    """Generate an image for a workout/fitness item using gemini-3.1-flash-lite-image in the global region.

    Saves the image as an artifact so it shows up in the Playground panel and uploads the bytes directly to Cloud Storage.

    Args:
        prompt: Description of the workout/exercise image to generate (e.g., 'Illustration of barbell bench press').
        tool_context: ADK ToolContext injected automatically.

    Returns:
        The public HTTPS URL of the uploaded image on Cloud Storage.
    """
    try:
        genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        if not response.candidates or not response.candidates[0].content.parts:
            return "Error: Model did not return any image content."

        part = response.candidates[0].content.parts[0]
        if not hasattr(part, "inline_data") or not part.inline_data:
            return "Error: Response part does not contain inline image data."

        img_bytes = part.inline_data.data
        mime_type = part.inline_data.mime_type or "image/jpeg"

        filename = f"workout_{int(datetime.datetime.now().timestamp())}.jpeg"

        # 1. Save artifact to Playground panel
        artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload same bytes directly to Cloud Storage (no local file write)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(img_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{STORAGE_BUCKET_NAME}/{filename}"
        return public_url
    except Exception as e:
        return f"Failed to generate and upload image: {str(e)}"


async def generate_workout_video(prompt: str, tool_context: ToolContext) -> str:
    """Generate a short video for a workout or exercise using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the video as an artifact with tool_context.save_artifact so it appears in the Playground's Artifacts panel,
    and uploads the video bytes directly to the public Cloud Storage bucket without writing to a local file.

    Args:
        prompt: Description of the exercise or workout video to generate (e.g., 'Demonstration of proper squat form').
        tool_context: ADK ToolContext injected automatically.

    Returns:
        The public HTTPS URL of the uploaded video on Cloud Storage.
    """
    try:
        genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        
        video_bytes = None
        
        # 1. Call Google Omni model via Interactions API
        try:
            interaction = genai_client.interactions.create(
                model="gemini-omni-flash-preview",
                input=prompt,
            )
            if hasattr(interaction, "output_video") and interaction.output_video:
                raw_data = getattr(interaction.output_video, "data", None)
                if raw_data:
                    video_bytes = base64.b64decode(raw_data) if isinstance(raw_data, str) else raw_data
        except Exception:
            pass

        # 2. Fallback to REST API if needed
        if not video_bytes:
            import google.auth
            import google.auth.transport.requests

            credentials, project = google.auth.default()
            auth_req = google.auth.transport.requests.Request()
            credentials.refresh(auth_req)

            url = f"https://aiplatform.googleapis.com/v1beta1/projects/{FIRESTORE_PROJECT_ID}/locations/global/interactions"
            headers = {
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "gemini-omni-flash-preview",
                "input": [
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()

            steps = data.get("steps", [])
            for step in steps:
                if step.get("type") == "model_output":
                    content = step.get("content", [])
                    for item in content:
                        if item.get("type") == "video" and item.get("data"):
                            video_bytes = base64.b64decode(item["data"])
                            break
            if not video_bytes and "output_video" in data:
                v_data = data["output_video"].get("data")
                if v_data:
                    video_bytes = base64.b64decode(v_data)

        if not video_bytes:
            return "Error: Could not extract video bytes from gemini-omni-flash-preview response."

        filename = f"workout_video_{int(datetime.datetime.now().timestamp())}.mp4"
        mime_type = "video/mp4"

        # 1. Save artifact so it shows up in Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes to public Cloud Storage bucket (no local file write)
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{STORAGE_BUCKET_NAME}/{filename}"
        return public_url

    except Exception as e:
        return f"Failed to generate and upload video: {str(e)}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=agent_engine_resource_name.split("/")[-1],
    )


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "FitBuddy AI, a personalized workout and fitness coaching assistant. "
        "CRITICAL SAFETY & PERSONALIZATION REQUIREMENT: Always track, remember, and respect all user allergies "
        "(including food allergies, drug allergies, and environmental allergies), dietary restrictions, injuries, and medical conditions. "
        "Always cross-check any exercise, nutrition, supplement, or workout advice against the user's known allergies and health limitations. "
        "Use search_exercises and add_exercise to view and manage the local exercise catalog stored in Firestore. "
        "Use fetch_online_exercise_info to query real-time external exercise information from the public Wger API. "
        "Use calculate_training_metrics to compute estimated 1RM, warm-up sets, and target training weights. "
        "Use geocode_address to convert location names into coordinates and find_nearby_places to locate gyms or fitness places. "
        "Use generate_workout_image to generate workout illustrations, save them as artifacts, and upload to Cloud Storage. "
        "Use generate_workout_video to generate workout demonstration videos using gemini-omni-flash-preview, save them as artifacts, and upload to Cloud Storage. "
        "Use code execution when needed to safely compute complex metrics or analyze data in a sandboxed Python environment."
    ),
    workflow_description="Analyze the request, call tools when needed to fetch real data or compute metrics, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        search_exercises,
        add_exercise,
        fetch_online_exercise_info,
        calculate_training_metrics,
        geocode_address,
        find_nearby_places,
        generate_workout_image,
        generate_workout_video,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)








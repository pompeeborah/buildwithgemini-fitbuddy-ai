# FitBuddy AI — Intelligent Workout & Fitness Coach

FitBuddy AI is an agentic workout and fitness coaching assistant built with **Google Agent Development Kit (ADK)** and deployed on **Vertex AI Agent Runtime**. FitBuddy AI provides personalized workout programming, 1RM strength calculations, exercise catalog search, location-based gym discovery, and multimodal exercise image and video generation.

---

## 🌟 Key Features & Tool Integrations

FitBuddy AI implements the following production-grade tools and Google Cloud services:

### 🧠 Cross-Session Long-Term Memory
- **Vertex AI Memory Bank Service**: Persists user preferences, fitness goals, medical history, injuries, and dietary allergies across sessions so recommendations are always personalized and safe.
- **PreloadMemoryTool**: Preloads past user session memories into the agent context at the start of conversations.

### 🗄️ Database & Catalog Management
- **Google Cloud Firestore**: Interacts with the `exercises` collection:
  - `search_exercises`: Searches exercises by target muscle group (e.g., Chest, Back, Legs) or category.
  - `add_exercise`: Adds custom exercise entries into the Firestore database with default sets, reps, and form guidance.

### 🧮 Fitness Calculations & Code Execution
- **`calculate_training_metrics`**: Computes estimated One-Rep Max (1RM) using the Epley formula:
  $$\text{1RM} = \text{Weight} \times \left(1 + \frac{\text{Reps}}{30}\right)$$
  Generates $50\%, 70\%, 85\%$ warm-up set progressions and target weight ranges for strength vs. hypertrophy.
- **Agent Engine Sandbox Code Executor**: Runs Python scripts in a sandboxed execution environment to analyze training data and compute complex formulas.

### 🎨 Multimodal Image & Video Generation
- **Google Cloud Storage (GCS)**: Public bucket integration for hosting generated media assets.
- **`generate_workout_image`**: Uses `gemini-3.1-flash-lite-image` in the `global` region to generate workout illustrations, save them as session artifacts, and upload directly to Cloud Storage.
- **`generate_workout_video`**: Uses Google's Omni model (`gemini-omni-flash-preview`) in the `global` region to generate exercise demonstration videos with embedded upbeat lo-fi background audio, save them as session artifacts, and upload directly to Cloud Storage.

### 🎨 Rich A2UI Card Rendering
- **A2UI Schema Manager (v0.8)**: Generates structured A2UI card layouts (`Card`, `Column`, `Row`, `Text`, `Image`) rendered directly in the custom web frontend.

### 🌐 External REST API Integrations
- **Wger Exercise API (`fetch_online_exercise_info`)**: Fetches external public exercise data.
- **Google Geocoding API (`geocode_address`)**: Converts location names into geographic coordinates.
- **Google Places API New (`find_nearby_places`)**: Finds nearby gyms, fitness centers, or sports complexes near the user's location.

---

## 🛠️ Architecture

```
[ Web Browser / Chat UI ]
         │
         ▼ (HTTP POST /chat)
[ FastAPI Proxy (frontend/main.py) ]
         │
         ▼ (A2A Protocol / gRPC)
[ Vertex AI Agent Runtime / Reasoning Engine ]
         │
         ├──► Vertex AI Memory Bank (Long-Term Memory)
         ├──► Google Cloud Firestore (Exercise Database)
         ├──► Google Cloud Storage (Static Assets Bucket)
         ├──► Gemini 3.1 Flash / Gemini Omni Models
         └──► Code Sandbox & External REST APIs
```

---

## 🚀 Local Setup & Running Instructions

### Prerequisites
- Python 3.11+
- Google Cloud SDK (`gcloud`) authenticated with an active GCP project.
- Active GCP environment with Firestore, Vertex AI Reasoning Engine, and Cloud Storage permissions.

### 1. Installation
Clone the repository and install dependencies into a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r frontend/requirements.txt
```

### 2. Environment Variables Configuration
Set the required environment variables:

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export AGENT_ENGINE_RESOURCE_NAME="projects/YOUR_PROJECT_NUMBER/locations/us-east1/reasoningEngines/YOUR_ENGINE_ID"
export AGENT_DIRECTORY="app"
export GOOGLE_MAPS_API_KEY="<your-google-maps-api-key>"
export WGER_API_KEY="<your-wger-api-key>"
```

### 3. Run Local Proxy & Frontend Server
Start the local FastAPI server:

```bash
cd frontend
python main.py
```

The application will start locally on port `8080`.

---

## ☁️ Deployment Instructions

### Deploy Agent to Vertex AI Reasoning Engine
```bash
agents-cli deploy
```

### Deploy Frontend Proxy to Cloud Run
```bash
gcloud run deploy fitbuddy-frontend \
  --source ./frontend \
  --region us-east1 \
  --quiet
```

---

## 📝 License
This project is licensed under the Apache License 2.0.

# ------------------------------------------------------
# Step 1: Load environment variables from .env file
# ------------------------------------------------------
# We use the python-dotenv package to automatically load
# variables like OPENROUTER_API_KEY, APP_REFERER, etc.
# from your local .env file into os.environ.
# This makes development and local testing much easier.
import requests
import os
from dotenv import load_dotenv
from fastapi import HTTPException
from app.utils.metrics import timer

load_dotenv()  # so local runs pick up .env

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY or not OPENROUTER_API_KEY.startswith("sk-or-"):
    raise RuntimeError("OPENROUTER_API_KEY missing or malformed.")


# ------------------------------------------------------
# Step 2: Import standard libraries and dependencies
# ------------------------------------------------------
# os → access environment variables
# requests → send HTTP requests to the OpenRouter API

# ------------------------------------------------------
# Step 3: Read the required API variables from environment
# ------------------------------------------------------
# These should all be set in your .env file (or docker-compose env_file)
OPENROUTER_BASE = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
APP_REFERER = os.getenv("APP_REFERER", "http://localhost:8000")
APP_TITLE = os.getenv("APP_TITLE", "AI Doctor App")

# Model comes from .env (MODEL=...). Default is OpenRouter's Free Models
# Router, which auto-selects from currently-available free models — resilient
# to individual :free models being retired (which is what broke this app:
# meta-llama/llama-3.3-70b-instruct:free was discontinued and returned 404).
DEFAULT_MODEL = os.getenv("MODEL", "openrouter/free")

# ------------------------------------------------------
# Step 4: Safety check — verify API key exists and is valid
# ------------------------------------------------------
# This helps catch missing or invalid keys early on startup.

# ------------------------------------------------------
# Step 5: Define the chat_completion function
# ------------------------------------------------------
# This function sends a POST request to OpenRouter's chat endpoint.
# It uses your LLM model (e.g. meta-llama/llama-3.3-70b-instruct:free)
# and returns the model’s response text.


def extract_medical_keywords(symptoms_text: str) -> list[str] | None:
    prompt = f"""
    Extract the key medical symptoms and conditions from this patient description.
    Return ONLY a comma-separated LIST of medical terms. Be concise and clinical.
    The result should be a list that contains string datatype.

    PATIENT DESCRIPTION:
    "{symptoms_text}"

    MEDICAL KEYWORDS:
    """
    try:
        response = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You are a medical transcription assistant. Extract only medical symptoms and conditions.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        keywords = response.strip()
        if "\n" in keywords:
            keywords = keywords.split("\n")[0]
        keywords = keywords.split(",")
        return keywords
    except Exception as e:
        print(f"LLM extraction failed: {e}")
        return None


def chat_completion(
    messages,
    model=None,
    temperature=0.5,
):
    model = model or DEFAULT_MODEL
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_REFERER,
        "X-Title": APP_TITLE,
    }

    payload = {
        "model": model,
        "messages": messages,
        # 400 was too small for the full advice JSON schema — the model's
        # output got truncated mid-JSON, which broke parsing downstream.
        "max_tokens": 2000,
        "temperature": temperature,
    }

    # Make the POST request to the API, timing how long the LLM takes to respond
    try:
        with timer("llm_latency_ms"):
            r = requests.post(
                f"{OPENROUTER_BASE}/chat/completions",
                json=payload,
                headers=headers,
                timeout=60,
            )
    except requests.RequestException as e:
        # Network failure/timeout: surface as a proper 502 (goes through the
        # normal exception handlers, so the response gets CORS headers)
        # instead of an unhandled exception -> bare 500 without CORS headers.
        print(f"❌ Could not reach OpenRouter: {e}")
        raise HTTPException(
            status_code=502, detail="Could not reach the AI service. Please try again."
        )

    if not r.ok:
        # If unauthorized, rate-limited, model retired, etc., print details
        print(f"❌ OpenRouter API error {r.status_code}: {r.text[:500]}")
        raise HTTPException(
            status_code=502,
            detail=f"AI service error ({r.status_code}). Please try again.",
        )

    # Return the model’s text output
    data = r.json()
    return data["choices"][0]["message"]["content"]

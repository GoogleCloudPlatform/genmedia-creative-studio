import os
import json
import asyncio
from google import genai
from google.genai import types

def get_gemini_client(project_id, location):
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location
    )

VARIATION_PROMPT_TEMPLATE = """
You are an expert creative director for a video production studio. 
Your task is to take a "Base Concept" and an optional "Reference Image" description, and produce exactly {count} subtle variations of this concept for video generation.

**Base Concept:** "{concept}"

**Requirements for Variations:**
1. Each variation must be a self-contained video prompt.
2. The core subject from the base concept MUST remain the central focus.
3. Vary the following elements subtly between variations:
   - **Lighting:** (e.g., golden hour, cinematic noir, high-key studio, neon-pulsing).
   - **Camera Work:** (e.g., slow zoom-in, orbiting gimbal shot, static macro, handheld shaky-cam).
   - **Atmosphere:** (e.g., misty morning, ethereal dust motes, clean minimalist, stormy/dramatic).
4. Each prompt should be descriptive and optimized for a high-quality video model like Veo.

Return your response ONLY as a JSON list of strings:
[
  "Prompt variation 1...",
  "Prompt variation 2...",
  ...
]
"""

async def generate_concept_variations(concept, count, project_id, location, model_name="gemini-3.5-flash-lite"):
    client = get_gemini_client(project_id, location)
    
    prompt = VARIATION_PROMPT_TEMPLATE.format(concept=concept, count=count)
    
    def _call(m):
        return client.models.generate_content(
            model=m,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

    try:
        response = await asyncio.to_thread(_call, model_name)
    except Exception as e:
        if model_name != "gemini-3.5-flash-lite":
            print(f"Model {model_name} failed ({e}), falling back to gemini-3.5-flash-lite...")
            response = await asyncio.to_thread(_call, "gemini-3.5-flash-lite")
        else:
            raise
    
    try:
        variations = json.loads(response.text)
        if isinstance(variations, list):
            return variations[:count]
        return [concept] * count # Fallback
    except Exception as e:
        print(f"Error parsing Gemini variations: {e}")
        return [concept] * count

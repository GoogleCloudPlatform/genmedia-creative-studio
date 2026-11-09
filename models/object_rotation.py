# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Model logic for the Object Rotation feature."""

import uuid
from common import authz
from common.analytics import get_logger
from config.firebase_config import FirebaseClient

db = FirebaseClient().get_client()
logger = get_logger(__name__)

def save_object_rotation_project(project: dict) -> dict:
    """
    Creates or updates an Object Rotation project document in Firestore.

    Args:
        project: A dictionary representing the project.

    Returns:
        The project dictionary, now with an 'id' if it was new.
    """
    # Server-side authorization: the recorded owner must be the server-derived
    # caller, and an existing project may only be overwritten by its owner.
    caller = authz.resolve_caller_email(fallback=project.get("user_email"))
    authz.authorize_attribution(
        project.get("user_email"),
        caller,
        resource="object rotation project",
    )

    is_new = "id" not in project or not project.get("id")
    if is_new:
        project["id"] = str(uuid.uuid4())

    doc_ref = db.collection("object_rotation_projects").document(project["id"])
    if not is_new:
        authz.authorize_existing_document(
            doc_ref,
            "user_email",
            caller,
            resource="object rotation project",
        )
    doc_ref.set(project)
    logger.info(f"Object Rotation project saved to Firestore with ID: {project['id']}")
    return project


import asyncio
from models.gemini import generate_image_from_prompt_and_images

async def _generate_single_view(prompt: str, image_uri: str, image_model: str) -> str:
    """Helper to generate one view and return the URI."""
    gcs_uris, _, _, _, _ = await asyncio.to_thread(
        generate_image_from_prompt_and_images,
        prompt=prompt,
        images=[image_uri],
        aspect_ratio="1:1", # Assuming a square aspect ratio for product views
        gcs_folder="object_rotation_views",
        model_name=image_model,
    )
    if not gcs_uris:
        raise Exception(f"Failed to generate view for prompt: {prompt}")
    return gcs_uris[0]

async def generate_product_views(product_description: str, image_uri: str, image_model: str) -> dict[str, str]:
    """Generates four views of a product concurrently."""
    logger.info(f"Generating four views for source image: {image_uri}")

    base_prompt = f"a high-quality, professional {{view}} view of the product, which is {product_description}, on a plain white background."

    views_to_generate = {
        "front": base_prompt.format(view="front"),
        "back": base_prompt.format(view="back"),
        "left": base_prompt.format(view="left"),
        "right": base_prompt.format(view="right"),
    }

    tasks = [
        _generate_single_view(prompt, image_uri, image_model) 
        for prompt in views_to_generate.values()
    ]

    generated_uris = await asyncio.gather(*tasks)

    result = dict(zip(views_to_generate.keys(), generated_uris))

    logger.info(f"Successfully generated four views: {result}")
    return result


from models.workflow_video import generate_workflow_reference_video


def generate_rotation_video(product_views: dict[str, str], video_model: str) -> str:
    """Generates a 360 rotation video from the front, back, and left views.

    ``video_model`` is a configured model name: a Gemini Omni model
    (reference-to-video) or a Veo model that supports reference images.
    """
    logger.info("Generating 360 rotation video from views.")

    if not all(k in product_views for k in ["front", "back", "left"]):
        raise ValueError("Missing required views (front, back, left) for video generation.")

    prompt = (
        "Create a seamless, 360-degree rotating video of the product. "
        "The provided images are keyframes for the front, back, and left views, in that order. "
        "The video should smoothly transition between these views to create a full rotation."
    )

    video_uri = generate_workflow_reference_video(
        model_name=video_model,
        reference_gcs_uris=[
            product_views["front"],
            product_views["back"],
            product_views["left"],
        ],
        prompt=prompt,
    )

    if not video_uri:
        raise Exception("Failed to generate rotation video.")

    return video_uri




---
title: "Veo 3 Character Consistency Demo"
---

This application demonstrates a workflow for generating a video of a person in a new scene while maintaining character consistency. It uses a series of Google AI models to analyze input images, generate a new scene with the person, and then create a video from that scene.

## How it Works

The application follows a multi-step process to generate the final video:

1.  **Image Analysis:** The workflow begins by analyzing a directory of input images of a person. It uses a multimodal model to generate a detailed facial profile and a natural language description for each image.

2.  **Image Generation:** The generated descriptions and a user-provided scene prompt are used to create a detailed prompt for Imagen. Imagen then generates a set of new images of the person in the desired scene.

3.  **Image Selection & Outpainting:** The application selects the best image from the generated set by comparing them to the original input images to ensure character likeness. This "best" image is then outpainted to create a wider scene, which is more suitable for video generation.

4.  **Video Generation:** The outpainted image is used as a reference for Veo. A video prompt is generated using a multimodal model, and then Veo creates an 8-second video based on the outpainted image and the new video prompt.

## Models Used

This demo uses the following Google AI models:

*   **Gemini 3.1 Pro Preview:** For image analysis, description generation, and video prompt generation.
*   **Imagen:** For generating the still images of the character in the new scene.
*   **Veo:** For generating the final video.

## How to Run

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/GoogleCloudPlatform/genmedia-creative-studio.git
    cd genmedia-creative-studio/experiments/veo3-character-consistency
    ```

2.  **Set up the Python environment and install dependencies:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure your environment:**
    *   Create a `.env` file by copying the `.env.example` file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file and add your Google Cloud project ID and the desired locations for the AI models.

4.  **Add your input images:**
    *   Place your input images of the person in the `input/` directory.

5.  **Run the application:**
    ```bash
    python main.py
    ```

## Configuration

You can modify the following files to change the application's behavior:

*   **`config.py`:** This file contains the configuration for the Google Cloud project, model names, and input/output directories.
*   **`main.py`:** You can change the `SCENARIO` variable in this file to define the scene you want to generate.
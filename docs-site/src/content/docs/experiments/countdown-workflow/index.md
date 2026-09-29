---
title: "AI-Powered Branded Countdown Video Generator"
---

This project is a powerful, two-stage Python pipeline that automates the creation of bespoke, branded countdown videos using a suite of Google's generative AI models.

## Features

*   **Style Analysis:** Analyzes any YouTube video segment to extract its visual style, serving as a creative template. This stage is optional.
*   **AI-Powered Scripting:** Automatically generates a structured video script tailored to a specific company's brand identity.
*   **Multi-Modal Generation:** Uses Imagen for initial scene images and Veo for generating continuous video clips.
*   **Intelligent Selection & Validation:** Employs Gemini to analyze multiple generated scenes, validate the presence of the correct countdown digit, and select the best candidate based on creative prompts.
*   **Automated Composition:** Assembles the final video with speed adjustments, fade-out transitions, and background music using `moviepy`.
*   **Pydantic Validation:** Ensures the data structures returned by the AI models are valid and reliable.

## How It Works

The system operates in two distinct stages, orchestrated by `main.py`:

### Stage 1: Style Analysis (Optional)

This stage reverse-engineers the creative style of a given YouTube video. It can be skipped by setting `SKIP_REVERSE_ENGINEERING=True` in `config.py`.

1.  **Download:** Downloads a specific time-ranged segment from a YouTube video using `yt-dlp`.
2.  **Chunk:** Splits the downloaded video into smaller, equal-duration chunks using `moviepy`.
3.  **Analyze:** Uses a multimodal AI model (Gemini 3.7 Flash) to process the video chunks and generate a detailed text file describing the visual style, scene composition, and overall aesthetic. This file becomes the creative brief for the next stage.

### Stage 2: Branded Video Generation

1.  **Adapt Script:** Takes a company name and the style analysis file as input. It uses a generative AI model (Gemini 3.7 Flash) to create a new, structured JSON script with creative prompts tailored to the company's brand.
2.  **Generate Scenes:** For each scene in the script:
    *   It generates an initial candidate image with **Imagen** for the very first scene.
    *   It generates multiple candidate video clips with **Veo**. To ensure continuity, each new video scene is generated using the last frame of the previously selected scene.
3.  **Validate and Select Best:**
    *   A selector model (Gemini 3.7 Flash) reviews the candidates to check if the countdown number is clearly visible.
    *   If no valid video is found, the generation is retried.
    *   Once validated, the model chooses the candidate that best fits the prompt.
4.  **Compose Video:** All the chosen video clips are assembled into a final MP4 file, sped up, and blended with a fade-out transition and background music.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd countdown-workflow
    ```

2.  **Install `uv`:** This project uses `uv` for package management. If you don't have it, install it:
    ```bash
    pip install uv
    ```

3.  **Create a virtual environment and install dependencies:**
    ```bash
    uv venv
    uv sync
    ```
    *Note: Make sure to activate the environment (`source .venv/bin/activate` on macOS/Linux or `.venv\Scripts\activate` on Windows).*

4.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file and add your Google Cloud Project ID and Location.
        ```
        GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
        GOOGLE_CLOUD_LOCATION="your-gcp-location"
        ```

## Usage

The entire pipeline is run from a single script.

Run the `main.py` script to generate the video.

```bash
uv run main.py
```

The script will create a new directory named `generated_company_video_<COMPANY_NAME>/` containing the final video and all the intermediate generated assets (scenes, frames, etc.).

## Configuration

You can configure the pipeline by editing the following files:

*   **`config.py`**:
    *   `SKIP_REVERSE_ENGINEERING`: Set to `True` to skip the style analysis and use the existing analysis file.
    *   Contains paths to output directories and AI model IDs.

*   **`main.py`**:
    *   **Stage 1 (Style Analysis):**
        *   `video_url`: The URL of the YouTube video to analyze.
        *   `start_time`, `end_time`: The time range of the video to download.
        *   `chunk_duration`: The duration of the video chunks for analysis.
    *   **Stage 2 (Video Generation):**
        *   `company_name_param`: The name of the company for the branded video.
        *   `countdown_start_param`: The number to start the countdown from.
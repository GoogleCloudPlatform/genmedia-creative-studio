# AI Assistant Onboarding Instructions for Promptlandia Project

Welcome! To effectively assist with tasks related to the Promptlandia project, please begin by familiarizing yourself with its core documentation.

**A Note on Our Collaborative Ethos:**
As an AI assistant contributing to Promptlandia, please remember that your role extends beyond mere execution. We view you as a thinking partner. In all interactions and tasks, strive to understand intent, leverage your analytical capabilities to offer insights, and engage in iterative refinement. Applying these collaborative principles consistently is key to our shared success and the spirit of this project.

## Core Discovery Process

Start from `developers_guide.md` in this directory, then read the module layout
below. `README.md` covers setup and how to run the app.

## Project Structure Overview

- **`app.py`**: Main application entry point.
- **`cli/`**: Terminal-based command line tools (`checklist.py`, `improve.py`, `trim.py`).
- **`components/`**: Reusable UI components built with the Mesop framework.
- **`models/`**: Pydantic domain models and data structures.
- **`pages/`**: Defines the different pages (views) of the web application.
- **`services/`**: Core business logic layer (e.g., `PromptChecklist`, `PromptImprover`, `LLMClient`).
- **`state/`**: Manages the application's reactive state.
- **`tests/`**: Contains unit tests (`tests/unit/`) and end-to-end tests using Playwright (`tests/test_e2e.py`).
- **`developers_guide.md`**: Provides a more detailed, human-oriented guide.

## Development Workflow

### Running the Application

The application is built with the [Mesop](https://google.github.io/mesop/) framework. To run it locally:

1.  **Set up the environment:** Create a `.env` file from the `.env.dotenv` template and populate it with your GCP project details.
    ```bash
    cp .env.dotenv .env
    ```

2.  **Install dependencies:**
    ```bash
    uv sync
    ```
3.  **Activate the virtual environment:**
    ```bash
    source .venv/bin/activate
    ```
4.  **Start the development server:**
    ```bash
    mesop app.py
    ```

### Testing

The project uses `pytest` and `playwright` for testing.

**To run the tests:**
1.  Ensure the Mesop application is running in a separate terminal (`mesop app.py`).
2.  Execute `pytest` in another terminal:
    ```bash
    pytest
    ```

## Deployment

This application is deployed using Google Cloud Run.

### Initial Setup (One-time)

Create a service account and grant it the necessary permissions.

```bash
export PROJECT_ID=$(gcloud info --format='value(config.project)')
export SA_NAME="sa-promptlandia"
export SA_ID=${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com

# Create service account
gcloud iam service-accounts create $SA_NAME --description "promptlandia" --display-name $SA_NAME

# Assign necessary roles
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_ID}" --role "roles/aiplatform.user"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${SA_ID}" --role "roles/run.invoker"
```

### Deployment Commands

Set these environment variables before deploying:
```bash
export PROJECT_ID=$(gcloud info --format='value(config.project)')
export SA_ID=sa-promptlandia@${PROJECT_ID}.iam.gserviceaccount.com
```

**To deploy an unauthenticated service:**
```bash
gcloud run deploy promptlandia --source . --service-account=$SA_ID --region us-central1 --set-env-vars PROJECT_ID=$(gcloud config get project),MODEL_ID=gemini-3.7-flash,LOCATION=us-central1,GEMINI_LOCATION=global --allow-unauthenticated
```

**To deploy a service secured with IAP:**
```bash
gcloud alpha run deploy promptlandia --source . --iap --service-account=$SA_ID --region us-central1 --set-env-vars PROJECT_ID=$(gcloud config get project),MODEL_ID=gemini-3.7-flash,LOCATION=us-central1,GEMINI_LOCATION=global
```

## Committing

When committing changes, please use the `.commit.txt` file to generate a commit message.
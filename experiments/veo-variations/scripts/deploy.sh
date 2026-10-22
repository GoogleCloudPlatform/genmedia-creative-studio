#!/bin/bash

# Veo Variations Studio - Cloud Run Deployment Script
# 
# This script automates the deployment of the Veo Variations Studio to Google 
# Cloud Run. It reads configuration directly from the `.env` file at the project 
# root, provisions necessary service accounts and IAM roles, builds the container 
# image using Cloud Build, and deploys it to Cloud Run.
#
# Optionally, it supports securing the Cloud Run service behind Identity-Aware 
# Proxy (IAP) by setting `USE_IAP=true`.

# ------------------------------------------------------------------------------
# 1. Load Environment Configuration
# ------------------------------------------------------------------------------
# Attempt to load variables from the `.env` file located in the parent directory.
# This prevents the need to hardcode sensitive or environment-specific values
# directly within this deployment script.
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading configuration from .env..."
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Warning: .env file not found. Falling back to default script values."
fi

# ------------------------------------------------------------------------------
# 2. Extract and Sanitize Variables
# ------------------------------------------------------------------------------
# Map the loaded `.env` variables to internal script variables. Provide fallback
# defaults just in case the `.env` file is missing or incomplete.
PROJECT_ID="${VEO_PROJECT_ID:-your-project-id}"
REGION="${VEO_LOCATION:-us-central1}"

# The deployment script requires the raw bucket name without the protocol prefix.
# Strip the `gs://` prefix if it was provided in the `.env` configuration.
BUCKET="${VEO_BUCKET:-your-gcs-bucket}"
BUCKET="${BUCKET#gs://}"

# Define static service and image naming conventions.
SERVICE_NAME="${SERVICE_NAME:-veo-variations-studio}"
SERVICE_ACCOUNT="veo-variations-sa@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Determine if the user requested IAP (Identity-Aware Proxy) protection.
# This toggles whether the service is deployed publicly or securely behind IAP.
USE_IAP="${USE_IAP:-false}"
# EAP_GROUP="${EAP_GROUP:-your-iap-access-group@example.com}"

echo " Deploying Veo Variations Studio to Cloud Run"

# ------------------------------------------------------------------------------
# 3. Provision IAM Service Account and Roles
# ------------------------------------------------------------------------------
# We create a dedicated service account to adhere to the principle of least privilege.
# This service account will be attached to the Cloud Run instance.
if ! gcloud iam service-accounts describe "${SERVICE_ACCOUNT}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating dedicated service account: ${SERVICE_ACCOUNT}..."
    gcloud iam service-accounts create veo-variations-sa \
        --display-name="Veo Variations Studio SA" \
        --project="${PROJECT_ID}"
fi

# Grant the service account the ability to invoke Vertex AI models (Veo generation).
echo "Granting aiplatform.user role to service account..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/aiplatform.user" \
    --condition=None --quiet >/dev/null

# Grant the service account Storage Object Admin access. 
# This is mandatory for mounting the GCS bucket via Cloud Storage FUSE and 
# downloading resulting MP4 assets.
echo "Granting storage.objectAdmin role to service account..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SERVICE_ACCOUNT}" \
    --role="roles/storage.objectAdmin" \
    --condition=None --quiet >/dev/null

# ------------------------------------------------------------------------------
# 4. Build and Push Container Image
# ------------------------------------------------------------------------------
echo "Building and Pushing Image via Cloud Build..."
# Navigate to the root directory containing the Dockerfile before building.
cd "$(dirname "$0")/.."
gcloud builds submit --tag "$IMAGE_NAME" --project "$PROJECT_ID" .

# ------------------------------------------------------------------------------
# 5. Determine Authentication Flags
# ------------------------------------------------------------------------------
# If USE_IAP is false (default), the service is deployed publicly so anyone can access it.
# If USE_IAP is true, we lock down the service and enable Identity-Aware Proxy.
AUTH_FLAGS=("--allow-unauthenticated")
if [ "$USE_IAP" = "true" ]; then
    echo "IAP is enabled. Service will not allow unauthenticated invocations."
    AUTH_FLAGS=("--no-allow-unauthenticated" "--iap")
fi

# ------------------------------------------------------------------------------
# 6. Deploy to Cloud Run
# ------------------------------------------------------------------------------
echo "Deploying to Cloud Run..."
gcloud beta run deploy "$SERVICE_NAME" \
  --image "$IMAGE_NAME" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --timeout 3600 \
  --memory 8Gi \
  --cpu 4 \
  --set-env-vars="VEO_PROJECT_ID=$PROJECT_ID,VEO_LOCATION=$REGION,VEO_BUCKET=gs://$BUCKET,VIDEO_DIR=/videos,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GEMINI_MODEL=${GEMINI_MODEL:-gemini-3.5-flash-lite},VEO_MODEL=${VEO_MODEL:-gemini-omni-1.1-flash-preview},OMNI_RESOLUTION=${OMNI_RESOLUTION:-360p}" \
  --add-volume=name=video-storage,type=cloud-storage,bucket="$BUCKET" \
  --add-volume-mount=volume=video-storage,mount-path=/videos \
  "${AUTH_FLAGS[@]}" \
  --service-account="${SERVICE_ACCOUNT}"

# ------------------------------------------------------------------------------
# 7. Configure IAP Access Policy
# ------------------------------------------------------------------------------
# If IAP is enabled AND a specific access group is defined, we grant that group
# the 'IAP-secured Web App User' role so they can access the protected service.
if [ "$USE_IAP" = "true" ] && [ -n "${EAP_GROUP}" ]; then
    echo "🔐 Configuring IAP Access for group: ${EAP_GROUP}..."
    gcloud beta iap web add-iam-policy-binding \
        --member="group:${EAP_GROUP}" \
        --role="roles/iap.httpsResourceAccessor" \
        --resource-type="cloud-run" \
        --region="$REGION" \
        --service="$SERVICE_NAME" \
        --project="$PROJECT_ID" \
        --condition=None \
        --quiet
fi

echo "Deployment Complete!"

#!/usr/bin/env bash
set -euo pipefail

: "${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT to your GCP project ID}"
REGION="${CLOUD_RUN_REGION:-us-central1}"
REPOSITORY="${ARTIFACT_REPOSITORY:-chatbot}"
SERVICE="${CLOUD_RUN_SERVICE:-chatbot}"
IMAGE="${ARTIFACT_IMAGE:-chatbot}"

command -v gcloud >/dev/null || { echo "gcloud CLI is required." >&2; exit 1; }

gcloud config set project "${GOOGLE_CLOUD_PROJECT}" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud artifacts repositories describe "${REPOSITORY}" --location="${REGION}" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker --location="${REGION}" \
    --description="Chatbot container images"

for secret in NVIDIA_API_KEY ALPHAVANTAGE_API_KEY LANGCHAIN_API_KEY; do
  gcloud secrets describe "${secret}" >/dev/null 2>&1 || {
    echo "Missing Secret Manager secret: ${secret}" >&2
    echo "Create it with: printf '%s' 'VALUE' | gcloud secrets create ${secret} --data-file=-" >&2
    exit 1
  }
done

PROJECT_NUMBER="$(gcloud projects describe "${GOOGLE_CLOUD_PROJECT}" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "${GOOGLE_CLOUD_PROJECT}" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-run.iam.gserviceaccount.com" \
  --role=roles/secretmanager.secretAccessor \
  --condition=None >/dev/null

gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions="_REGION=${REGION},_REPOSITORY=${REPOSITORY},_SERVICE=${SERVICE},_IMAGE=${IMAGE}" \
  .

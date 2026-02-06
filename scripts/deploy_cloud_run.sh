
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ID=btoproject-486405-486604
REGION=us-central1
SERVICE=week1-rag

# Build & deploy via Cloud Build (reproducible)
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE:latest

gcloud run deploy $SERVICE   --image gcr.io/$PROJECT_ID/$SERVICE:latest   --service-account=rag-svc-ac@btoproject-486405-486604.iam.gserviceaccount.com   --region=$REGION   --set-env-vars PROJECT_ID=$PROJECT_ID,REGION=$REGION,VERTEX_LOCATION=$REGION,VERTEX_INDEX_ID=projects/btoproject-486405-486604/locations/us-central1/indexes/rag-index,VERTEX_INDEX_ENDPOINT=projects/btoproject-486405-486604/locations/us-central1/indexEndpoints/PLACEHOLDER,DEPLOYED_INDEX_ID=rag-index-deployed,MODEL_VARIANT=gemini-2.0-flash-001   --allow-unauthenticated

URL=$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')
echo "Deployed: $URL"

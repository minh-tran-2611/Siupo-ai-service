#!/usr/bin/env bash
# Mở siupo-ai-service ra public (cho phép gọi không cần xác thực).
set -e
gcloud run services add-iam-policy-binding siupo-ai-service \
  --region=us-central1 \
  --member=allUsers \
  --role=roles/run.invoker
echo "=== DONE: đã mở public ==="

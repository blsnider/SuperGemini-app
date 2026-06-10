#!/usr/bin/env bash
# One-time GCP setup + deploy for tee-agent (§1).
# Prereqs: gcloud auth'd to project, Firestore in native mode already enabled.
set -euo pipefail

PROJECT="sis-sandbox-463113"
REGION="us-central1"
SERVICE="tee-agent"
TZ="America/Chicago"

# §0 BLOCKER — set this to ~60s BEFORE the confirmed release time.
# Placeholder assumes 6:00 AM release -> fire at 5:59 AM. CONFIRM FIRST.
SNIPE_CRON="59 5 * * *"

echo "== Secrets (create once; re-running 'add' versions is fine) =="
for s in foreup-username foreup-password tee-agent-scheduler-token \
         tee-agent-confirm-secret twilio-account-sid twilio-auth-token \
         twilio-from-number; do
  gcloud secrets describe "$s" --project "$PROJECT" >/dev/null 2>&1 \
    || gcloud secrets create "$s" --project "$PROJECT" --replication-policy automatic
done
echo "   -> add values with: echo -n 'VALUE' | gcloud secrets versions add NAME --data-file=-"

echo "== Build & deploy Cloud Run =="
gcloud run deploy "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --source . \
  --min-instances 0 --max-instances 1 \
  --memory 512Mi --timeout 360 \
  --no-allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=$PROJECT,TEE_AGENT_PHONE=+1701XXXXXXX,TEE_AGENT_CALENDAR_ID=primary"

URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format 'value(status.url)')
gcloud run services update "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --update-env-vars "TEE_AGENT_BASE_URL=$URL"

SA="tee-agent-invoker@$PROJECT.iam.gserviceaccount.com"
gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1 \
  || gcloud iam service-accounts create tee-agent-invoker --project "$PROJECT"
gcloud run services add-iam-policy-binding "$SERVICE" \
  --project "$PROJECT" --region "$REGION" \
  --member "serviceAccount:$SA" --role roles/run.invoker

TOKEN=$(gcloud secrets versions access latest --secret tee-agent-scheduler-token --project "$PROJECT")

echo "== Scheduler: sniper at T-60s before release (§3.1) =="
gcloud scheduler jobs create http tee-agent-snipe \
  --project "$PROJECT" --location "$REGION" \
  --schedule "$SNIPE_CRON" --time-zone "$TZ" \
  --uri "$URL/snipe" --http-method POST \
  --headers "X-TeeAgent-Token=$TOKEN" \
  --oidc-service-account-email "$SA" \
  --attempt-deadline 360s \
  || echo "(snipe job exists — update with 'gcloud scheduler jobs update')"

echo "== Scheduler: watchdog every 30 min (§4.1) =="
gcloud scheduler jobs create http tee-agent-watchdog \
  --project "$PROJECT" --location "$REGION" \
  --schedule "*/30 * * * *" --time-zone "$TZ" \
  --uri "$URL/watchdog" --http-method POST \
  --headers "X-TeeAgent-Token=$TOKEN" \
  --oidc-service-account-email "$SA" \
  --attempt-deadline 120s \
  || echo "(watchdog job exists)"

echo "== §4.4 dead-watchdog alert: log-based metric + alerting policy =="
echo "   The watchdog writes a heartbeat doc after every successful run."
echo "   Create a Cloud Monitoring alert on Cloud Scheduler job failures:"
echo "   Console -> Monitoring -> Alerting -> 'Cloud Scheduler Job' ->"
echo "   metric 'executions' filtered to status!=SUCCESS for tee-agent-watchdog,"
echo "   notification channel = your phone/email. This catches both HTTP"
echo "   failures and a dead service; the Firestore heartbeat is the audit trail."

echo "Done. Service: $URL  (dry_run is ON by default — flip in Firestore"
echo "tee_agent_config/preferences after a few clean release windows)"

# Deployment and demo

## Vercel Hobby frontend

Live sample: https://devflow-ai-demo.vercel.app (deployed 2026-09-30).

The verified Vercel team is `devflow-ai`, on the **Hobby** plan (no trial).
Deploy only the frontend directory, with its vercel.json. The build enables
VITE_DEMO_MODE=true and serves clearly labeled synthetic data. No backend URL,
private report, or provider credential is bundled.

```powershell
cd frontend
vercel --prod --yes --scope devflow-ai
```

Do not enable paid marketplace services or switch to Pro. The Hobby plan is for
personal/non-commercial use: [official plan details](https://vercel.com/docs/plans/hobby).
Vercel function invocations have [bounded durations](https://vercel.com/docs/functions/configuring-functions/duration).
The existing Celery consumer and Beat scheduler therefore need a separate running
host. Deploying this frontend does **not** satisfy the laptop-closed acceptance test.

## Backend deployment gate

A free backend host/account has not been selected or provisioned. No billable
resources are authorized. Once a suitable host is available, run the API, worker,
one scheduler, PostgreSQL, and Redis with persistent storage; apply Alembic
migrations before enabling deliveries. Supply DATABASE_URL, REDIS_URL,
GITHUB_APP_ID, mounted PEM, GITHUB_WEBHOOK_SECRET, and GEMINI_API_KEY privately.
Never copy local secrets into the frontend or build arguments.

Expose only the signed webhook over HTTPS. Keep dashboard/read routes private
until authentication and repository authorization exist. Configure exact frontend
CORS origin for any later authenticated deployment. Update the GitHub App webhook
only after the target is live and verified. Preserve the current working tunnel
until then.

## Acceptance evidence still required

Record a real PR URL, delivery ID, review ID, stored report, current commit SHA,
Check Run URL, and annotation. Verify duplicate replay, worker restart, provider
timeout, GitHub failure, clean/buggy PRs, and a new commit during processing.
Then turn off the laptop and repeat against cloud services. No live Check Run
screenshots or full-workflow video should be fabricated before this succeeds.

For a 60–90 second final demo, show a PR opening, authenticated delivery,
processing status, completed Check Run and annotation, then its dashboard report.
The current sample screenshot proves only frontend rendering.

# DevFlow AI dashboard

From the project root, `docker compose up -d --build` serves the local dashboard at
http://localhost:5173. Node is included in Docker; no host install is required.
For host development with Node 22.12+: `npm ci` then `npm run dev` in this directory.
Vite proxies /api to localhost:8000; Docker overrides the upstream to api:8000.

`npm run build` typechecks/builds; `npm run lint` lints. Browser tests use system
Chromium in Dockerfile.test (see ../docs/benchmarks.md for commands).
No credentials belong in frontend environment variables. The dashboard renders
finding text as plain text and exposes no mutation controls. This is development
only: do not tunnel dashboard/API read paths or publicly deploy without authentication
and repository authorization. CORS is not authorization.

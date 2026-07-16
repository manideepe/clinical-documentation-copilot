# ClarityNote frontend

An accessible React + TypeScript prototype for a treatment-plan-aware clinical documentation extension. The interface uses synthetic local records and is designed to demonstrate the workflow safely without paid services or real protected health information.

## What the prototype demonstrates

- Client search with EHR synchronization and duplicate-safe record identity cues
- Latest-treatment-plan selection with clearly distinct active and expired states
- Appointment setup and the required five appointment statuses
- All eight clinical note types from the project brief
- Seven structured, factual session inputs that remain editable
- Text and simulated voice-summary pathways with a five-minute voice minimum
- Automatic voice and generation lockout when the treatment plan is expired
- Grounded, editable note output with source-provenance cues
- Required clinician review, approval, secure-copy, completion, and audit states
- Graceful local-demo fallback if an EHR API is not configured or unavailable

## Run locally

Requirements: Node.js 20 or newer.

```bash
npm install
npm run dev
```

Then open the local address printed by Vite.

## Verify

```bash
npm run lint
npm run test
npm run build
```

The automated tests verify that all eight templates are present, expired plans block voice and AI generation while allowing factual summaries to be saved, and approval/copy controls enforce clinician review.

## Optional API connection

The development server proxies `/api` to the local FastAPI service and injects the documented development-only gateway assertions outside browser code. `VITE_API_BASE_URL` defaults to `/api/v1`. The client maps the backend `{ "items": [...] }` response into the view model; if the service is unavailable or has no synchronized clients, it intentionally falls back to two synthetic demo clients. A production deployment must replace the development proxy assertions with an approved identity gateway.

## Demo walkthrough

The default synthetic client, **Avery Morgan**, has an active plan. Edit the seven facts, generate a new draft, review it, approve it, and use the copy control.

Search for **Jordan Lee** to see the expired-plan path. Voice is unavailable, generation is not offered, and saving the facts changes the appointment to **Documentation Pending** while preserving the source text for a future plan activation.

## Scope and safety

This frontend is an interaction prototype, not a production EHR or medical device. Voice capture is simulated and does not request microphone access. Clipboard, authentication, authorization, encryption, audit immutability, and EHR synchronization require server-side enforcement before production use. Only synthetic demo data is included.

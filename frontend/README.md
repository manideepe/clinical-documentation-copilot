# ClarityNote frontend

An accessible React + TypeScript prototype for a treatment-plan-aware clinical documentation extension. The interface uses synthetic local records and is designed to demonstrate the workflow safely without paid services or real protected health information.

## What the prototype demonstrates

- Client search with EHR synchronization and duplicate-safe record identity cues
- Latest-treatment-plan selection with clearly distinct active and expired states
- Appointment setup and the required five appointment statuses
- All eight clinical note types from the project brief
- Seven structured, factual session inputs that remain editable
- Browser-native live microphone transcription with interim text and an editable transcript fallback
- Transcript-to-fact mapping that requires at least six complete factual statements
- Browser-local creation and persistence of fictional test clients
- Automatic voice and generation lockout when the treatment plan is expired
- Grounded, editable note output with source-provenance cues
- Protected same-origin Ollama drafting through a Vercel function, with deterministic grounded fallback behavior
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

The automated tests verify that all eight templates are present, expired plans block voice and AI generation while allowing factual summaries to be saved, transcript mapping produces structured facts, fictional clients persist locally, and approval/copy controls enforce clinician review.

## Optional API connection

The development server proxies `/api/v1` to the local FastAPI service and injects the documented development-only gateway assertions outside browser code. `VITE_API_BASE_URL` defaults to `/api/v1`. The client maps the backend `{ "items": [...] }` response into the view model; if the service is unavailable or has no synchronized clients, it intentionally falls back to two fictional demo clients. The Vercel deployment also serves `/api/generate`, which reads `OLLAMA_API_KEY` only in the server environment, fixes the model to `gpt-oss:20b`, validates and bounds the request, and returns a no-store response. A production deployment must replace the development proxy assertions, public-demo throttling, and model provider with approved controls.

## Demo walkthrough

The default synthetic client, **Avery Morgan**, has an active plan. Edit the seven facts, generate a new draft, review it, approve it, and use the copy control.

Search for **Jordan Lee** to see the expired-plan path. Voice is unavailable, generation is not offered, and saving the facts changes the appointment to **Documentation Pending** while preserving the source text for a future plan activation.

Choose **Voice summary** on the active plan and allow microphone access to start live transcription. Speak six or more complete statements, stop listening, review the transcript, and map it into session facts. Browser support varies, so the transcript area also accepts typed or pasted text.

Use the plus button beside client search to create a fictional test client. The record stays only in the current browser's local storage and opens with blank session facts.

## Scope and safety

This frontend is an interaction prototype, not a production EHR or medical device. It requests microphone access only after a user starts live transcription and does not persist audio. Speech processing is supplied by the browser and may depend on the browser vendor's service. Never enter real patient information in the hosted demo. The model credential remains server-side, but a public model gateway is still not a production clinical-data path. Clipboard, authentication, authorization, encryption, audit immutability, and EHR synchronization require server-side enforcement before production use.

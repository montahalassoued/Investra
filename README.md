# Frontend (Investra Chat)

Minimal Next.js chat frontend for the investra AI investment assistant.

This app connects to the FastAPI backend and sends user messages to the `/chat` endpoint with a persistent `session_id` for multi-turn conversation context.

## Screenshot

<img src="/images/Capture%20d%E2%80%99%C3%A9cran%202026-04-14%20225611.png" alt="Stockify chat screenshot" />

## Tech Stack

- Next.js 16
- React 19
- TypeScript
- Tailwind CSS 4

## Features

- Chat-first interface for investment questions
- Session persistence with `localStorage` (`investra-session-id`)
- Backend integration through `POST /chat`
- Request timeout protection (120s)

## Project Structure

- `app/(chat)/page.tsx`: chat route entry point
- `components/chat/investra-chat.tsx`: main chat UI and client-side session handling
- `lib/investra-api.ts`: backend API client for chat requests
- `.env.example`: frontend environment variables

## Requirements

- Node.js 20+
- Backend running at `http://localhost:8000` (or custom API URL)

## Environment Variables

Copy `.env.example` to `.env.local` and adjust if needed.

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Run Locally

From `frontend/chatbot`:

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Type Checking

```bash
npm run typecheck
```

## Backend API Contract

### Request

`POST /chat`

```json
{
  "message": "I have 5000$, should I invest in Apple?",
  "session_id": "<uuid>"
}
```

### Response

```json
{
  "response": "...assistant answer..."
}
```

## Notes

- The frontend creates one `session_id` per browser and reuses it across messages.
- If backend processing is slow, the frontend waits up to 120 seconds before timeout.
- The current UI renders responses progressively for a smoother feel, but the backend does not stream tokens yet.
- Ensure backend CORS allows `http://localhost:3000` in local development.

## Troubleshooting

### Frontend starts but chat fails

- Verify backend is running on `http://localhost:8000`
- Verify `.env.local` points to the correct backend URL
- Check browser console for network errors

### Timeout errors

- Some deep analyses can take longer; verify backend logs and model/API availability
- Confirm backend dependencies (LLM API key, Redis, market data providers) are configured

### Port conflicts

- Frontend default: `3000`
- Backend default: `8000`

## Scripts

- `npm run dev`: start development server
- `npm run build`: production build
- `npm run start`: run production server
- `npm run typecheck`: TypeScript validation

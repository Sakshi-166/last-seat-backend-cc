# The Last Seat — Concurrent Ticket Booking Backend

A FastAPI + PostgreSQL backend demonstrating seat inventory, temporary holds, booking confirmation, cancellation, booking history, and concurrency control.

## Requirements
- Docker Desktop, or Python 3.12+ and PostgreSQL 16+
- Git

## Run with Docker (recommended)
1. Clone the repository and open its root folder in VS Code.
2. Copy `.env.example` to `.env` if you want a local environment file. Docker Compose already supplies the database URL.
3. Run:
   ```bash
   docker compose up --build
   ```
4. Open API docs at http://localhost:8000/docs and health at http://localhost:8000/health.
5. Stop with `Ctrl+C`, then `docker compose down`. To also delete database data use `docker compose down -v` (destructive).

The first startup creates 500 seats named A001–A500. Demo hold duration is five minutes.

## Run without Docker
1. Install PostgreSQL and create database `lastseat`.
2. Create and activate a virtual environment.
3. Install `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and change `DATABASE_URL` to your local PostgreSQL credentials, for example `postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/lastseat`.
5. Run `uvicorn app.main:app --reload`.

## API endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/seats` | List all seats and status |
| POST | `/reservations` | Temporarily hold an available seat |
| POST | `/reservations/{id}/confirm` | Confirm a hold before expiry |
| POST | `/reservations/{id}/cancel` | Cancel and release a seat |
| GET | `/reservations/{id}` | Get reservation status |
| GET | `/users/{user_id}/bookings` | Booking history |

### Example requests
Hold seat A001 (add a unique `Idempotency-Key` header to make retries safe):
```bash
curl -X POST http://localhost:8000/reservations -H "Content-Type: application/json" -H "Idempotency-Key: request-abc-001" -d "{"user_id":"student-17","seat_number":"A001"}"
```
Confirm booking ID 1:
```bash
curl -X POST http://localhost:8000/reservations/1/confirm -H "Content-Type: application/json" -d "{"user_id":"student-17"}"
```
Cancel booking ID 1:
```bash
curl -X POST http://localhost:8000/reservations/1/cancel -H "Content-Type: application/json" -d "{"user_id":"student-17"}"
```
Check history:
```bash
curl http://localhost:8000/users/student-17/bookings
```

## Concurrency strategy
- A reservation transaction locks the target seat row using PostgreSQL `SELECT ... FOR UPDATE`.
- Requests for the same seat serialize: the first transaction changes its state to `held`; the next sees the updated state and receives HTTP 409.
- Holds expire after `HOLD_MINUTES`. Expired holds are released when the seat is next reserved; `/seats` also refreshes visible expired holds.
- `Idempotency-Key` lets clients safely retry a reservation request without creating another booking.
- PostgreSQL is the source of truth. Do not rely on an in-memory Python lock: it fails across multiple API workers/containers.

## ERD
```mermaid
erDiagram
    SEATS ||--o{ BOOKINGS : has
    SEATS {
        int id PK
        string seat_number UK
        string status
    }
    BOOKINGS {
        int id PK
        int seat_id FK
        string user_id
        string status
        datetime hold_expires_at
        string idempotency_key UK
        int active_key
        datetime created_at
    }
```

## Booking workflow
```mermaid
flowchart TD
    A[Client requests seat] --> B[Lock seat row in PostgreSQL]
    B --> C{Seat available?}
    C -- No --> D[Return 409 Conflict]
    C -- Yes --> E[Create temporary hold]
    E --> F{User confirms before expiry?}
    F -- Yes --> G[Mark booking confirmed and seat booked]
    F -- No --> H[Expire hold and release seat]
    G --> I[Return booking status]
    H --> I
```

## Load test (k6)
Install k6, start the app, then run:
```bash
k6 run loadtest.js
```
The script intentionally sends many requests for the same seat; expected outcome is one successful hold and other requests receiving 409 (plus any transport errors if the test environment is overloaded).

## Important production improvements
This is a learning/demo baseline. Before real ticket sales, add authentication/authorization, payment provider integration and verified payment webhooks, database migrations (Alembic), structured logs/metrics, rate limiting, a scheduled hold-expiry worker, robust integration tests, and a proper payment state machine. Do not store card details. The demo permits cancellation of confirmed bookings and does not itself process payments.

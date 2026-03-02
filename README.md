# AIContent — AI Content Generator SaaS

A production-grade Django SaaS for generating marketing content with AI.
Server-rendered templates (HTMX), Postgres, Redis, Celery, Paystack.

---

## Architecture

```
Browser → Django (Gunicorn) → Postgres / Redis
                  ↓ Celery tasks
              OpenAI API (or compatible)
                  ↓ Paystack webhooks
              Subscription activation
```

**Apps:**
| App | Responsibility |
|---|---|
| `accounts` | Auth (register, login, logout, profile) |
| `content` | Projects, ContentGeneration, UsageLedger, services |
| `billing` | Subscription, Payment, WebhookEventLog, Paystack integration |
| `ai` | Provider abstraction, prompt templates |
| `analytics` | Audit events, admin dashboard |

---

## Local Setup

### 1. Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis 7+

### 2. Clone & install

```bash
git clone <repo>
cd AI-contents
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in DB, Redis, Paystack, OpenAI keys
```

### 4. Run migrations

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py setup_beat   # registers Celery Beat tasks
```

### 5. Run development servers

```bash
# Terminal 1 — Django
python manage.py runserver

# Terminal 2 — Celery worker
celery -A config worker -l DEBUG

# Terminal 3 — Celery beat (scheduler)
celery -A config beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Visit: http://localhost:8000

---

## Docker (Production)

```bash
cp .env.example .env   # fill in production values
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Services started:
- `web` — Gunicorn on port 8000
- `worker` — Celery worker (4 concurrency)
- `beat` — Celery beat scheduler
- `redis` — Redis 7
- `postgres` — Postgres 16

---

## Paystack Test Mode

1. Get test keys from https://dashboard.paystack.com/#/settings/developers
2. Set in `.env`:
   ```
   PAYSTACK_SECRET_KEY=sk_test_...
   PAYSTACK_PUBLIC_KEY=pk_test_...
   ```
3. Use test card: `4084 0840 8408 4081`, CVV: `408`, Expiry: any future date, PIN: `0000`

### Webhook Testing (local)

Use [ngrok](https://ngrok.com) to expose your local server:
```bash
ngrok http 8000
```
Then in Paystack dashboard → Settings → API → Webhooks:
- Add URL: `https://<ngrok-id>.ngrok.io/billing/webhook/`
- Events: `charge.success`

Test webhook delivery with:
```bash
curl -X POST https://your-domain/billing/webhook/ \
  -H "X-Paystack-Signature: <computed_sig>" \
  -H "Content-Type: application/json" \
  -d '{"event":"charge.success","id":"test_001","data":{...}}'
```

---

## Running Tests

```bash
python manage.py test apps.content.tests apps.billing.tests -v 2
```

Test coverage:
- Quota enforcement (free/pro limits)
- Usage deduction atomicity
- Project limit checks
- Rate limiting
- Webhook signature verification
- Webhook idempotency (duplicate events)
- Amount/currency mismatch handling
- Unknown reference handling
- Checkout flow (mocked Paystack)

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `SECRET_KEY` | Django secret key | ✓ |
| `DEBUG` | Debug mode (False in prod) | ✓ |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | ✓ |
| `DB_NAME` | Postgres database name | ✓ |
| `DB_USER` | Postgres user | ✓ |
| `DB_PASSWORD` | Postgres password | ✓ |
| `DB_HOST` | Postgres host | ✓ |
| `DB_PORT` | Postgres port (default 5432) | |
| `REDIS_URL` | Redis connection URL | ✓ |
| `OPENAI_API_KEY` | OpenAI (or compatible) API key | ✓ |
| `OPENAI_API_BASE` | API base URL (swap for other providers) | |
| `OPENAI_MODEL` | Model name (default gpt-4o-mini) | |
| `PAYSTACK_SECRET_KEY` | Paystack secret key (server-only) | ✓ |
| `PAYSTACK_PUBLIC_KEY` | Paystack public key | ✓ |

---

## Production Hardening Checklist

- [x] `DEBUG=False` in production
- [x] `SECRET_KEY` from env (not hardcoded)
- [x] `SECURE_HSTS_SECONDS` + `SECURE_SSL_REDIRECT` (auto-enabled when DEBUG=False)
- [x] `SESSION_COOKIE_SECURE=True` + `CSRF_COOKIE_SECURE=True`
- [x] Paystack secret key never sent to frontend
- [x] Webhook signature validated before processing
- [x] DB transactions for all state transitions
- [x] `select_for_update` on Payment row during webhook
- [x] Idempotent webhook handler (WebhookEventLog unique key)
- [x] Amount + currency validated before activating subscription
- [x] Generation endpoint DB-rate-limited per user
- [x] WhiteNoise for static files (no separate Nginx needed for static)
- [x] Non-root Docker user
- [ ] Add Nginx in front of Gunicorn for production
- [ ] Configure SSL certificate (Let's Encrypt / Certbot)
- [ ] Set up log aggregation (e.g. Papertrail, Datadog)
- [ ] Configure backup for Postgres volume

---

## Admin

Visit `/admin/` — configure:
- Users & Subscriptions
- Payments & WebhookEventLogs
- ContentGeneration (retry failed)
- UsageLedger (audit usage)
- Analytics events

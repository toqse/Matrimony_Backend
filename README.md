# Matrimony Backend

Production-ready monolithic Django backend for a Matrimony platform with JWT + OTP auth, profiles, subscriptions, staff/commissions/salary, enquiries, and match engine.

## Tech stack

- Python 3.11+, Django 4.x, Django REST Framework
- SimpleJWT (access 15 min, refresh 30 days)
- Redis (OTP, cache), Celery + Celery Beat
- SQLite (dev), MySQL (prod), Docker + Gunicorn

## Project structure

```
matrimony_backend/     # project config
accounts/              # OTP, JWT, auth, users
profiles/              # Profile CRUD, photos, interests, shortlists
subscriptions/         # Plans, purchases, expiry
staff/                 # Staff, commissions, salary
branches/              # Branch management
enquiries/             # Leads & follow-ups
notifications/         # Email/SMS logs
matching/              # Match engine (Celery)
core/                  # Permissions, base models, utilities
```

## Setup (development)

1. Copy `.env.example` to `.env` and set `SECRET_KEY`, etc.
2. Use SQLite (default): leave `DATABASE_ENGINE` unset or set to `sqlite`.
3. Install and run:

```bash
pip install -r requirements.txt
set DJANGO_SETTINGS_MODULE=matrimony_backend.settings
python manage.py migrate
python manage.py runserver
```

4. For OTP/cache and Celery (optional in dev):

- Start Redis.
- In another terminal: `celery -A matrimony_backend worker -l info`
- For Beat: `celery -A matrimony_backend beat -l info`

## Docker (run the project)

1. **Create `.env`** (copy from `.env.example`) and set at least:
   - `SECRET_KEY` (e.g. a long random string)
   - `DATABASE_PASSWORD` (MySQL app user password)
   - `MYSQL_ROOT_PASSWORD` (MySQL root password, e.g. `rootpass`)

2. **Start all services:**
   ```bash
   docker-compose up --build
   ```

3. **Access:**
   - API: http://localhost:8000/
   - Plans (no auth): http://localhost:8000/api/v1/subscriptions/plans/
   - Admin: http://localhost:8000/admin/ (create a superuser inside the container first)

4. **MySQL** is mapped to host port **3307** (to avoid conflict with local MySQL on 3306). Connect with a DB client to `localhost:3307` if needed.

5. **Stop:** `Ctrl+C` then `docker-compose down`.

**Services:** `django` (Gunicorn, entrypoint runs migrations then starts), `mysql`, `redis`, `celery_worker`, `celery_beat`. All use `restart: unless-stopped` and share the same Docker network so they resolve hostnames (`redis`, `mysql`) correctly.

**If you run Celery on your host** (not in Docker), use `REDIS_URL=redis://localhost:6379/0` in `.env` so it can reach Redis; inside Docker use `redis://redis:6379/0`.

## API overview

- **Auth**: `POST /api/v1/auth/register/mobile/`, `verify/mobile/`, `register/email/`, `verify/email/`, `login/`, `token/refresh/`, `logout/`, `password/reset/`, `password/confirm/`
- **Profiles**: `GET/POST /api/v1/profiles/`, `GET/PATCH /api/v1/profiles/{id}/`, `GET /api/v1/profiles/{id}/contact/` (subscribed), `POST .../interest/`, `POST .../shortlist/`, `GET .../my/matches/`, `GET .../my/interests/`, `POST .../photos/`
- **Subscriptions**: `GET /api/v1/subscriptions/plans/`, `POST .../purchase/`, `POST .../staff-add/`, `GET .../my/`, `GET/PATCH /api/v1/subscriptions/`, `.../{id}/`
- **Staff**: `GET /api/v1/staff/me/dashboard/`, `me/commissions/`, `me/salary/`, `GET/POST/PATCH /api/v1/staff/`, `POST .../commissions/{id}/approve/`, `POST .../salary/generate/`, `.../salary/{id}/approve/`, `.../salary/{id}/mark-paid/`
- **Branches**: `GET/POST/PATCH /api/v1/branches/`
- **Enquiries**: `GET/POST /api/v1/enquiries/`, `GET/PATCH .../{id}/`, `POST .../{id}/followup/`, `POST .../{id}/convert/`

## Roles

- **user**: profile, interests, shortlist, subscription (gated contact/interest).
- **staff** / **branch_manager**: branch-scoped enquiries, staff-add subscription, commissions.
- **admin**: all + staff CRUD, salary generate/approve/mark-paid, commission approve.

## Nginx

See `nginx.conf.example` for a production-ready Nginx placeholder in front of Gunicorn.

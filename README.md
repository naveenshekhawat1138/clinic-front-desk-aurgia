# Clinic Front Desk

A booking tool for a small clinic's front desk. Prevents double-booking a doctor,
and applies a late-cancellation fee automatically based on how much notice the
patient gave.

## Tech stack

- Backend: Python, Flask, Flask-SQLAlchemy
- Database: SQLite (file `clinic.db`, created automatically on first run)
- Frontend: server-rendered HTML templates + vanilla JavaScript, calling the JSON API below

## Setup & run

```bash
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

The app runs at `http://localhost:5000`. On first run it seeds three sample doctors.

1. Go to `/register` and create a front-desk account.
2. Log in at `/login`.
3. Use the dashboard at `/dashboard` to book, view a doctor's day, and search.

## Debugging

- Flask runs with `debug=True`, so tracebacks show in the browser and the server
  auto-reloads on file changes.
- The SQLite file is `clinic.db` in the project root — delete it and restart the
  app to reset all data (doctors will be reseeded).
- If port 5000 is already in use, change the port in the last line of `app.py`.

## API endpoints

All endpoints below require an active session (log in first) except auth endpoints.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Create a front-desk account. Body: `{email, password}` |
| POST | `/api/auth/login` | Log in, starts a session. Body: `{email, password}` |
| POST | `/api/auth/logout` | Log out, clears the session |
| GET  | `/api/doctors` | List all doctors |
| POST | `/api/doctors` | Add a doctor. Body: `{name, specialization}` |
| GET  | `/api/doctors/<id>/appointments?date=YYYY-MM-DD&page=&per_page=&sort=&order=` | A doctor's appointments, optionally filtered to one day, paginated and sorted |
| GET  | `/api/patients` | List all patients |
| POST | `/api/appointments` | Book an appointment. Body: `{doctor_id, patient_name, patient_phone, start_time (ISO), duration_minutes}`. Returns `409` if the doctor already has an overlapping appointment. |
| POST | `/api/appointments/<id>/cancel` | Cancel an appointment. Applies a late fee if cancelled less than 24 hours before the start time. |
| GET  | `/api/appointments/search?patient=&page=&per_page=&sort=&order=` | Find appointments by patient name (partial match) |

## Core rules implemented

- **No double-booking:** a new booking is rejected (`409`) if it overlaps any
  existing *booked* appointment for the same doctor. Overlap is checked with the
  standard interval test (`existing.start < new.end AND existing.end > new.start`),
  checked once before insert and again right before commit to shrink the race window.
- **Cancellation fee:** cancelling **24 hours or more** before the appointment start
  is free. Cancelling within that window applies a flat fee (see `LATE_CANCELLATION_FEE`
  in `models.py`).

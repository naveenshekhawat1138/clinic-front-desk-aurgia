# Reasoning

## Priority order
The brief said to get conflict-free booking and the cancellation rule right first,
then the lookups. I built and tested in that order: booking + overlap check first,
then cancellation fee logic, then doctor-day view, search, pagination/sorting, and
the landing page last.

## Key design decisions

**Stack:** Flask + SQLite + Flask-SQLAlchemy. Chose this for a fast setup in a
timed round — no build step, minimal dependencies, SQLite needs no separate server.

**Overlap rule:** Two time ranges overlap if `existing.start < new.end AND
existing.end > new.start`. I only check against appointments with
`status == 'booked'` (cancelled ones don't block a slot). The check runs once
before creating the row and once again right before commit, to shrink the window
where two near-simultaneous requests could both pass the first check.

**Cancellation fee:** A cancellation counts as "late" if it happens less than
24 hours before the appointment's start time. Late cancellations get a flat fee
(`LATE_CANCELLATION_FEE` in `models.py`); on-time cancellations get none. This is
computed and stored at cancel-time, not derived later, so the history stays
accurate even as time passes.

**Patients found-or-created by name+phone:** the brief didn't require a separate
"add patient" step, so a booking auto-creates the patient record if one with
that name and phone doesn't already exist. Lets the front desk book in one step.

**UI over the API:** the dashboard is a thin HTML shell; all real data (doctor
list, day view, search results, booking, cancelling) goes through the JSON API
listed in the README via `fetch()` in `static/app.js`, rather than the UI talking
to the database directly.

## How I tested it

I wrote a small script that drives the Flask app through its test client (no
browser needed) and walked through the exact scenarios from the brief:

1. Register + log in a front-desk user.
2. Book doctor A at 10:00–10:30 → should succeed.
3. Book the same doctor at 10:15–10:45 (overlaps) → should be rejected with 409.
4. Book the same doctor at 10:30–11:00 (back-to-back, no overlap) → should succeed.
5. Search appointments by patient name → returns the right appointment.
6. Load a doctor's day for that date → returns both booked appointments.
7. Cancel an appointment far in the future → should be free (`late_fee_applied: false`).
8. Book an appointment starting in ~1 hour, then cancel it → should get the late fee.

## Bug I hit and fixed

My first version of the booking route re-checked for conflicts a second time
right before `commit()`, as an extra safety net against race conditions. That
second check kept failing on the very first booking, even into an empty table.

Looking at it, the cause was: `db.session.add(appt)` puts the new appointment
into the SQLAlchemy session, and SQLAlchemy auto-flushes pending changes before
running a query — so by the time the second `has_conflict()` check ran, the new
row had already been flushed to the database and was overlapping *with itself*.

Fix: call `db.session.flush()` explicitly right after `add()` to get the new
row's id, then pass `exclude_id=appt.id` into the second conflict check so it
ignores the row it's about to commit. Re-ran the test script afterward and all
cases passed.

## What I'd improve with more time
- Move from a flat late-cancellation fee to a percentage of the appointment's cost.
- Add per-doctor working hours so bookings outside them are rejected too.
- Use a proper migration tool (e.g. Alembic) instead of `db.create_all()`.

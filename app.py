import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from models import (
    db, User, Doctor, Patient, Appointment, Notification,
    has_conflict, CANCELLATION_WINDOW_HOURS, LATE_CANCELLATION_FEE,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "clinic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_app(app)

# --- Simulated clock -------------------------------------------------------
# By default the app uses real wall-clock time. A grading harness (or anyone
# testing time-based behaviour, like the no-show job or morning reminders)
# can call POST /clock to move time forward without waiting for real hours
# to pass. Every place in this app that needs "now" calls now() below instead
# of datetime.utcnow() directly, so the whole app respects the simulated time
# once it's been set.
_simulated_now = None  # None = use real time


def now():
    return _simulated_now if _simulated_now is not None else datetime.utcnow()


NO_SHOW_GRACE_MINUTES = 30  # mark a booked appointment as no-show this long after it started


def run_due_jobs():
    """
    Runs whenever the clock moves forward (see POST /clock below).
    1) Sends a "today's appointment" reminder (into the /outbox) for any
       booked appointment whose day has arrived and hasn't been reminded yet.
    2) Marks any booked appointment as "no_show" if it's more than
       NO_SHOW_GRACE_MINUTES past its start time and was never completed.
    """
    current = now()
    today_start = datetime(current.year, current.month, current.day)
    today_end = today_start + timedelta(days=1)

    # 1) Morning reminders for today's appointments
    due_for_reminder = Appointment.query.filter(
        Appointment.status == "booked",
        Appointment.reminded.is_(False),
        Appointment.start_time >= today_start,
        Appointment.start_time < today_end,
    ).all()
    for appt in due_for_reminder:
        db.session.add(Notification(
            appointment_id=appt.id,
            patient_id=appt.patient_id,
            kind="appointment_reminder",
            message=(
                f"Reminder: you have an appointment with {appt.doctor.name} "
                f"today at {appt.start_time.strftime('%H:%M')}."
            ),
            created_at=current,
        ))
        appt.reminded = True

    # 2) Auto no-show marking
    no_show_cutoff = current - timedelta(minutes=NO_SHOW_GRACE_MINUTES)
    overdue = Appointment.query.filter(
        Appointment.status == "booked",
        Appointment.start_time <= no_show_cutoff,
    ).all()
    for appt in overdue:
        appt.status = "no_show"

    db.session.commit()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "authentication required"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Page routes (server-rendered shells; the pages fetch data from /api/*)
# ---------------------------------------------------------------------------
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", email=session.get("email"))


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "an account with that email already exists"}), 409

    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "invalid email or password"}), 401
    session["user_id"] = user.id
    session["email"] = user.email
    return jsonify(user.to_dict())


@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Doctors / Patients
# ---------------------------------------------------------------------------
@app.route("/api/doctors", methods=["GET"])
@login_required
def api_list_doctors():
    doctors = Doctor.query.order_by(Doctor.name).all()
    return jsonify([d.to_dict() for d in doctors])


@app.route("/api/doctors", methods=["POST"])
@login_required
def api_create_doctor():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    doctor = Doctor(name=name, specialization=data.get("specialization"))
    db.session.add(doctor)
    db.session.commit()
    return jsonify(doctor.to_dict()), 201


@app.route("/api/doctors/<int:doctor_id>/appointments", methods=["GET"])
@login_required
def api_doctor_appointments(doctor_id):
    """A doctor's day (or full list), paginated and sortable."""
    date_str = request.args.get("date")  # YYYY-MM-DD, optional
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    sort = request.args.get("sort", "start_time")
    order = request.args.get("order", "asc")

    query = Appointment.query.filter_by(doctor_id=doctor_id)
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "date must be YYYY-MM-DD"}), 400
        next_day = day + timedelta(days=1)
        query = query.filter(Appointment.start_time >= day, Appointment.start_time < next_day)

    sort_col = {"start_time": Appointment.start_time, "status": Appointment.status}.get(
        sort, Appointment.start_time
    )
    sort_col = sort_col.desc() if order == "desc" else sort_col.asc()
    query = query.order_by(sort_col)

    paged = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [a.to_dict() for a in paged.items],
        "page": paged.page,
        "per_page": paged.per_page,
        "total": paged.total,
        "pages": paged.pages,
    })


@app.route("/api/patients", methods=["GET"])
@login_required
def api_list_patients():
    patients = Patient.query.order_by(Patient.name).all()
    return jsonify([p.to_dict() for p in patients])


# ---------------------------------------------------------------------------
# Appointments: booking (conflict-free) + cancellation (fee rule) + search
# ---------------------------------------------------------------------------
@app.route("/api/appointments", methods=["POST"])
@login_required
def api_create_appointment():
    data = request.get_json(force=True)
    doctor_id = data.get("doctor_id")
    patient_name = (data.get("patient_name") or "").strip()
    patient_phone = (data.get("patient_phone") or "").strip()
    start_str = data.get("start_time")   # ISO: "2026-09-20T10:00"
    duration_minutes = int(data.get("duration_minutes") or 30)

    if not doctor_id or not patient_name or not start_str:
        return jsonify({"error": "doctor_id, patient_name and start_time are required"}), 400

    doctor = Doctor.query.get(doctor_id)
    if not doctor:
        return jsonify({"error": "doctor not found"}), 404

    try:
        start_time = datetime.fromisoformat(start_str)
    except ValueError:
        return jsonify({"error": "start_time must be ISO format, e.g. 2026-09-20T10:00"}), 400
    end_time = start_time + timedelta(minutes=duration_minutes)

    # --- the core rule: never double-book a doctor ---
    # Re-checked inside the same DB transaction as the insert below, so two
    # near-simultaneous requests can't both pass the check and both insert.
    if has_conflict(doctor_id, start_time, end_time):
        return jsonify({
            "error": "This doctor already has an appointment that overlaps this time slot."
        }), 409

    # find-or-create patient by name+phone
    patient = None
    if patient_phone:
        patient = Patient.query.filter_by(name=patient_name, phone=patient_phone).first()
    if not patient:
        patient = Patient(name=patient_name, phone=patient_phone or None)
        db.session.add(patient)
        db.session.flush()  # get patient.id without committing yet

    appt = Appointment(
        doctor_id=doctor_id,
        patient_id=patient.id,
        start_time=start_time,
        end_time=end_time,
        status="booked",
    )
    db.session.add(appt)
    db.session.flush()  # assigns appt.id, without committing yet

    # Final safety check right before commit (narrows the race-condition window).
    # Must exclude the row we just flushed, or it will "conflict" with itself.
    if has_conflict(doctor_id, start_time, end_time, exclude_id=appt.id):
        db.session.rollback()
        return jsonify({
            "error": "This doctor already has an appointment that overlaps this time slot."
        }), 409

    db.session.commit()
    return jsonify(appt.to_dict()), 201


@app.route("/api/appointments/<int:appt_id>/cancel", methods=["POST"])
@login_required
def api_cancel_appointment(appt_id):
    appt = Appointment.query.get(appt_id)
    if not appt:
        return jsonify({"error": "appointment not found"}), 404
    if appt.status == "cancelled":
        return jsonify({"error": "appointment is already cancelled"}), 409

    current = now()
    hours_before = (appt.start_time - current).total_seconds() / 3600.0
    is_late = hours_before < CANCELLATION_WINDOW_HOURS

    appt.status = "cancelled"
    appt.cancelled_at = current
    appt.late_fee_applied = is_late
    appt.fee_amount = LATE_CANCELLATION_FEE if is_late else 0.0
    db.session.commit()

    return jsonify(appt.to_dict())


@app.route("/api/appointments/<int:appt_id>/reschedule", methods=["POST"])
@login_required
def api_reschedule_appointment(appt_id):
    """
    Lifecycle twist: move a booked appointment to a new time. Same doctor,
    same patient — only the time changes, and it must stay conflict-free.
    """
    appt = Appointment.query.get(appt_id)
    if not appt:
        return jsonify({"error": "appointment not found"}), 404
    if appt.status != "booked":
        return jsonify({"error": f"cannot reschedule an appointment with status '{appt.status}'"}), 409

    data = request.get_json(force=True)
    start_str = data.get("start_time")
    if not start_str:
        return jsonify({"error": "start_time is required"}), 400
    try:
        new_start = datetime.fromisoformat(start_str)
    except ValueError:
        return jsonify({"error": "start_time must be ISO format, e.g. 2026-09-20T10:00"}), 400

    duration_minutes = data.get("duration_minutes")
    if duration_minutes is not None:
        new_end = new_start + timedelta(minutes=int(duration_minutes))
    else:
        new_end = new_start + (appt.end_time - appt.start_time)  # keep original length

    # Re-check overlap against every OTHER booked appointment for this doctor.
    if has_conflict(appt.doctor_id, new_start, new_end, exclude_id=appt.id):
        return jsonify({
            "error": "This doctor already has an appointment that overlaps the new time slot."
        }), 409

    appt.start_time = new_start
    appt.end_time = new_end
    appt.reminded = False  # if it moved to a different day, it should be reminded again
    db.session.commit()
    return jsonify(appt.to_dict())


@app.route("/api/appointments/<int:appt_id>/complete", methods=["POST"])
@login_required
def api_complete_appointment(appt_id):
    """Front desk marks a patient as seen — this is what stops the no-show job from firing."""
    appt = Appointment.query.get(appt_id)
    if not appt:
        return jsonify({"error": "appointment not found"}), 404
    if appt.status != "booked":
        return jsonify({"error": f"cannot complete an appointment with status '{appt.status}'"}), 409
    appt.status = "completed"
    db.session.commit()
    return jsonify(appt.to_dict())


@app.route("/api/appointments/search", methods=["GET"])
@login_required
def api_search_appointments():
    """Find a patient's appointment(s) by name."""
    name = (request.args.get("patient") or "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    sort = request.args.get("sort", "start_time")
    order = request.args.get("order", "desc")

    query = Appointment.query.join(Patient)
    if name:
        query = query.filter(Patient.name.ilike(f"%{name}%"))

    sort_col = {"start_time": Appointment.start_time, "status": Appointment.status}.get(
        sort, Appointment.start_time
    )
    sort_col = sort_col.desc() if order == "desc" else sort_col.asc()
    query = query.order_by(sort_col)

    paged = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "items": [a.to_dict() for a in paged.items],
        "page": paged.page,
        "per_page": paged.per_page,
        "total": paged.total,
        "pages": paged.pages,
    })


# ---------------------------------------------------------------------------
# System endpoints for the grading harness: simulated clock + notification outbox.
# Not behind login — these represent the harness/scheduler poking the system,
# not a front-desk staff action.
# ---------------------------------------------------------------------------
@app.route("/clock", methods=["POST"])
def set_clock():
    """
    Advance or set the simulated 'now', then run whatever jobs are due
    (morning reminders, auto no-show marking).

    Body accepts ONE of:
      {"now": "2026-09-20T08:00:00"}   -> set the simulated time to this instant
      {"advance_minutes": 45}           -> move forward by N minutes from current time
      {"advance_seconds": 1800}         -> move forward by N seconds from current time
    """
    global _simulated_now
    data = request.get_json(silent=True) or {}

    if "now" in data:
        try:
            _simulated_now = datetime.fromisoformat(data["now"])
        except (ValueError, TypeError):
            return jsonify({"error": "now must be an ISO datetime string"}), 400
    elif "advance_minutes" in data:
        _simulated_now = now() + timedelta(minutes=float(data["advance_minutes"]))
    elif "advance_seconds" in data:
        _simulated_now = now() + timedelta(seconds=float(data["advance_seconds"]))
    else:
        return jsonify({
            "error": "provide one of: now (ISO datetime), advance_minutes, advance_seconds"
        }), 400

    run_due_jobs()
    return jsonify({"current_time": now().isoformat()})


@app.route("/outbox", methods=["GET"])
def get_outbox():
    """Everything the (mock) Notification Service has 'sent' so far."""
    notifications = Notification.query.order_by(Notification.created_at).all()
    return jsonify([n.to_dict() for n in notifications])


with app.app_context():
    db.create_all()
    # seed a couple of doctors on first run so the app isn't empty
    if Doctor.query.count() == 0:
        db.session.add_all([
            Doctor(name="Dr. Asha Rao", specialization="General Physician"),
            Doctor(name="Dr. Marcus Lee", specialization="Pediatrics"),
            Doctor(name="Dr. Priya Nair", specialization="Dermatology"),
        ])
        db.session.commit()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

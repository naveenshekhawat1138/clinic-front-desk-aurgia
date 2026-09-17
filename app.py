import os
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from models import (
    db, User, Doctor, Patient, Appointment,
    has_conflict, CANCELLATION_WINDOW_HOURS, LATE_CANCELLATION_FEE,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "clinic.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_app(app)


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

    now = datetime.utcnow()
    hours_before = (appt.start_time - now).total_seconds() / 3600.0
    is_late = hours_before < CANCELLATION_WINDOW_HOURS

    appt.status = "cancelled"
    appt.cancelled_at = now
    appt.late_fee_applied = is_late
    appt.fee_amount = LATE_CANCELLATION_FEE if is_late else 0.0
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

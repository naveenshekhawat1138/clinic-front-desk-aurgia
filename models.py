from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# How many hours before an appointment a cancellation still counts as "on time".
CANCELLATION_WINDOW_HOURS = 24
LATE_CANCELLATION_FEE = 20.0  # flat fee in currency units, adjust as needed


class User(db.Model):
    """Front-desk staff account."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "email": self.email}


class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    specialization = db.Column(db.String(120), nullable=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "specialization": self.specialization}


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "phone": self.phone}


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctor.id"), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="booked")  # booked | cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    late_fee_applied = db.Column(db.Boolean, default=False)
    fee_amount = db.Column(db.Float, default=0.0)

    doctor = db.relationship("Doctor")
    patient = db.relationship("Patient")

    def to_dict(self):
        return {
            "id": self.id,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.name if self.doctor else None,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "patient_phone": self.patient.phone if self.patient else None,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "status": self.status,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "late_fee_applied": self.late_fee_applied,
            "fee_amount": self.fee_amount,
        }


def has_conflict(doctor_id, start_time, end_time, exclude_id=None):
    """
    Two booked appointments for the same doctor overlap if:
        existing.start < new.end AND existing.end > new.start
    This is the standard interval-overlap test.
    """
    query = Appointment.query.filter(
        Appointment.doctor_id == doctor_id,
        Appointment.status == "booked",
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    )
    if exclude_id is not None:
        query = query.filter(Appointment.id != exclude_id)
    return db.session.query(query.exists()).scalar()

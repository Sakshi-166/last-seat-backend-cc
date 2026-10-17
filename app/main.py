from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import Booking, Seat
from app.schemas import ReserveRequest, ConfirmRequest, CancelRequest

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenient for this demo. For production, use Alembic migrations instead.
    Base.metadata.create_all(bind=engine)
    with next(get_db()) as db:
        if db.query(Seat).count() == 0:
            db.add_all([Seat(seat_number=f"A{i:03d}") for i in range(1, 501)])
            db.commit()
    yield

app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

def utcnow():
    return datetime.now(timezone.utc)

def booking_output(booking: Booking, seat: Seat):
    return {
        "id": booking.id, "user_id": booking.user_id, "seat_number": seat.seat_number,
        "status": booking.status, "hold_expires_at": booking.hold_expires_at,
        "created_at": booking.created_at,
    }

def expire_if_needed(db: Session, seat: Seat, now: datetime):
    # Caller must hold the row lock for this seat.
    active = db.scalar(select(Booking).where(
        Booking.seat_id == seat.id, Booking.status == "held"
    ).with_for_update())
    if active and active.hold_expires_at and active.hold_expires_at <= now:
        active.status = "expired"
        active.active_key = None
        seat.status = "available"
        db.flush()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/seats")
def list_seats(db: Session = Depends(get_db)):
    # Update expired holds before returning current availability.
    now = utcnow()
    seats = db.scalars(select(Seat).order_by(Seat.id)).all()
    for seat in seats:
        if seat.status == "held":
            # This list endpoint is informational; reservation endpoint rechecks under lock.
            held = db.scalar(select(Booking).where(Booking.seat_id == seat.id, Booking.status == "held"))
            if held and held.hold_expires_at and held.hold_expires_at <= now:
                held.status = "expired"
                held.active_key = None
                seat.status = "available"
    db.commit()
    return [{"seat_number": s.seat_number, "status": s.status} for s in seats]

@app.post("/reservations", status_code=status.HTTP_201_CREATED)
def reserve(body: ReserveRequest, db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    # Serialize competing requests for the same seat using a PostgreSQL row lock.
    seat = db.scalar(select(Seat).where(Seat.seat_number == body.seat_number).with_for_update())
    if not seat:
        raise HTTPException(404, "Seat not found")
    now = utcnow()
    expire_if_needed(db, seat, now)

    # Retry-safe request: if key already exists, return the original booking.
    if idempotency_key:
        prior = db.scalar(select(Booking).where(Booking.idempotency_key == idempotency_key))
        if prior:
            prior_seat = db.get(Seat, prior.seat_id)
            db.commit()
            return booking_output(prior, prior_seat)

    if seat.status != "available":
        db.rollback()
        raise HTTPException(409, "Seat is not available")
    booking = Booking(
        user_id=body.user_id, seat_id=seat.id, status="held",
        hold_expires_at=now + timedelta(minutes=settings.hold_minutes),
        idempotency_key=idempotency_key, active_key=1,
    )
    seat.status = "held"
    db.add(booking)
    db.commit()
    db.refresh(booking)
    db.refresh(seat)
    return booking_output(booking, seat)

@app.post("/reservations/{booking_id}/confirm")
def confirm(booking_id: int, body: ConfirmRequest, db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Reservation not found")
    seat = db.scalar(select(Seat).where(Seat.id == booking.seat_id).with_for_update())
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    now = utcnow()
    expire_if_needed(db, seat, now)
    if booking.user_id != body.user_id:
        db.rollback()
        raise HTTPException(403, "This reservation belongs to another user")
    if booking.status == "confirmed":
        db.commit()
        return booking_output(booking, seat)
    if booking.status != "held" or not booking.hold_expires_at or booking.hold_expires_at <= now:
        db.rollback()
        raise HTTPException(409, "Reservation hold has expired or is no longer active")
    booking.status = "confirmed"
    booking.hold_expires_at = None
    seat.status = "booked"
    db.commit()
    db.refresh(booking)
    return booking_output(booking, seat)

@app.post("/reservations/{booking_id}/cancel")
def cancel(booking_id: int, body: CancelRequest, db: Session = Depends(get_db)):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise HTTPException(404, "Reservation not found")
    seat = db.scalar(select(Seat).where(Seat.id == booking.seat_id).with_for_update())
    booking = db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking.user_id != body.user_id:
        db.rollback()
        raise HTTPException(403, "This reservation belongs to another user")
    if booking.status in ("cancelled", "expired"):
        db.commit()
        return booking_output(booking, seat)
    if booking.status == "confirmed":
        # Demo policy: confirmed bookings may be cancelled and seat released.
        seat.status = "available"
    elif booking.status == "held":
        seat.status = "available"
    booking.status = "cancelled"
    booking.active_key = None
    booking.hold_expires_at = None
    db.commit()
    db.refresh(booking)
    return booking_output(booking, seat)

@app.get("/reservations/{booking_id}")
def reservation_status(booking_id: int, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, "Reservation not found")
    seat = db.get(Seat, booking.seat_id)
    if booking.status == "held" and booking.hold_expires_at and booking.hold_expires_at <= utcnow():
        # The next reservation request also enforces expiry under a row lock.
        return {**booking_output(booking, seat), "effective_status": "expired"}
    return booking_output(booking, seat)

@app.get("/users/{user_id}/bookings")
def booking_history(user_id: str, db: Session = Depends(get_db)):
    rows = db.execute(select(Booking, Seat).join(Seat).where(Booking.user_id == user_id).order_by(Booking.created_at.desc())).all()
    return [booking_output(b, s) for b, s in rows]

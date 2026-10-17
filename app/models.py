from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class Seat(Base):
    __tablename__ = "seats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seat_number: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available", nullable=False)
    bookings: Mapped[list["Booking"]] = relationship(back_populates="seat")

class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("seat_id", "active_key", name="uq_active_seat_booking"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    seat_id: Mapped[int] = mapped_column(ForeignKey("seats.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False) # held, confirmed, cancelled, expired
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    active_key: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    seat: Mapped["Seat"] = relationship(back_populates="bookings")

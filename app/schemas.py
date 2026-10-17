from datetime import datetime
from pydantic import BaseModel, Field

class ReserveRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    seat_number: str = Field(min_length=1, max_length=12)

class ConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)

class CancelRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)

class SeatOut(BaseModel):
    seat_number: str
    status: str

class BookingOut(BaseModel):
    id: int
    user_id: str
    seat_number: str
    status: str
    hold_expires_at: datetime | None
    created_at: datetime

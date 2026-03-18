from datetime import datetime

from pydantic import BaseModel


class UserCreate(BaseModel):
    email: str
    display_name: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}

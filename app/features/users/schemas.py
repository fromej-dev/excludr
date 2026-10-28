from pydantic import BaseModel, Field

# Deliberately loose: just enough to catch typos without an email-validator dependency
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class EmailChange(BaseModel):
    email: str = Field(max_length=255, pattern=EMAIL_PATTERN)
    current_password: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

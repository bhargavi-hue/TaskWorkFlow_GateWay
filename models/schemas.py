from pydantic import BaseModel

class SignupSchema(BaseModel):
    fullname: str
    phone: str
    email: str
    password: str

class SigninSchema(BaseModel):
    username: str
    password: str

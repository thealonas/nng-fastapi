from pydantic import BaseModel


class AuthCredentials(BaseModel):
    secret_key: str
    auth_key: str

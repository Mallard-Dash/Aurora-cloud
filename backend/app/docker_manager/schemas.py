from pydantic import BaseModel, Field
from typing import Optional, List

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class ContainerInfo(BaseModel):
    id: str
    name: str
    status: str
    image: str
    created: str
    short_id: str

class CreateContainerRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=63, pattern="^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    template: str

class OperationResponse(BaseModel):
    message: str
    container_id: Optional[str] = None
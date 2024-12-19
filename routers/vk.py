from typing import Annotated

import requests
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth.actions import ensure_user_authorization

router = APIRouter()


class PostCallMethod(BaseModel):
    method: str
    params: dict


@router.post("/vk/call_method", tags=["vk"])
async def call_vk_method(
    data: PostCallMethod,
    _: Annotated[bool, Depends(ensure_user_authorization)],
):
    """Proxy a VK API method call."""
    response = requests.post(
        f"https://api.vk.com/method/{data.method}", data.params
    ).json()

    if "error" in response:
        raise HTTPException(status_code=400, detail=response["error"])

    if "response" in response:
        return response["response"]

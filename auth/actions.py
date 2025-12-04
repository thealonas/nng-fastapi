from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import sentry_sdk
from fastapi import Depends, HTTPException, Request, Query
from jose import jwt, JWTError

from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.exceptions import ItemNotFoundException
from nng_sdk.postgres.nng_postgres import NngPostgres

from utils.environment_helper import EnvironmentHelper

op = OpConnect()

postgres = NngPostgres()

allowed_services = ["watchdog", "bot"]

ALGORITHM = "HS256"


def get_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        return None

    return auth.split(" ")[1]


def verify_credential(credential: str):
    keys = EnvironmentHelper.get_auth_keys()
    return credential == keys.auth_key


def ensure_authorization(
    token: Annotated[Optional[str], Depends(get_bearer_token)],
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if check_jwt_auth(token):
        return True

    raise credentials_exception


def ensure_user_authorization(
    request: Request,
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        allowed, user_id = check_user_auth(get_bearer_token(request))
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise credentials_exception
    else:
        if not allowed:
            return ensure_authorization(get_bearer_token(request))
        return True


def ensure_websocket_authorization(token: Annotated[Optional[str], Query()]):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token or not check_jwt_auth(token):
        raise credentials_exception

    return True


def check_jwt_auth(token: str | None) -> bool:
    if not token:
        return False

    try:
        token = get_bearer_token_content(token)
        if not token or not token.get("service_name"):
            raise JWTError()
    except JWTError:
        return False

    return token.get("service_name") in allowed_services


def get_bearer_token_content(token: str | None) -> dict | None:
    if not token:
        return None

    try:
        keys = EnvironmentHelper.get_auth_keys()
        token = jwt.decode(token, keys.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None

    return token


def get_jwt_token_user_id(token: str | None) -> int | None:
    if not token:
        return None

    try:
        keys = EnvironmentHelper.get_auth_keys()
        token = jwt.decode(token, keys.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None

    return token.get("user_id")


def check_user_auth(token: str | None) -> (bool, int | None):
    if not token:
        return False, None

    try:
        keys = EnvironmentHelper.get_auth_keys()
        token = jwt.decode(token, keys.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return False, None

    user_id: int | None = token.get("user_id")
    if not user_id:
        return False, None

    token_type = token.get("type")
    if not token_type or token_type != "admin":
        return False

    try:
        admin = postgres.users.get_user(user_id).admin
    except ItemNotFoundException:
        return False
    else:
        return admin, user_id


def _create_access_token(to_encode: dict):
    keys = EnvironmentHelper.get_auth_keys()
    encoded_jwt = jwt.encode(to_encode, keys.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_service_access_token(service_name: str):
    to_encode = {
        "service_name": service_name,
        "exp": datetime.now(timezone.utc) + timedelta(days=365 * 5),
        "type": "service",
    }
    return _create_access_token(to_encode)


def create_user_access_token(user_id: int):
    to_encode = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "admin",
    }
    return _create_access_token(to_encode)

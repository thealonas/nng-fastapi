import hashlib

import sentry_sdk
from nng_sdk.one_password.op_connect import OpConnect

op = OpConnect()


def generate_invite_for_user(user_id: int):
    salt = op.get_invites_salt()
    result = hashlib.md5(f"{user_id}{salt}".encode()).hexdigest()
    return f"{user_id}:{result[:10]}"


def check_invite(invite: str) -> int | None:
    try:
        data = invite.split(":")
        user_id = int(data[0])
        hashed = data[1]
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None
    else:
        salt = op.get_invites_salt()
        result = hashlib.md5(f"{user_id}{salt}".encode()).hexdigest()
        if result[:10] == hashed:
            return user_id
        return None

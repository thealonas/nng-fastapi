def allowed_to_receive_editor(trust: int) -> bool:
    return trust > 10


def allowed_to_invite(trust: int) -> bool:
    return trust > 30


def get_groups_restriction(trust: int) -> int:
    if trust <= 10:
        return 0

    if trust <= 20:
        return 1

    if trust <= 30:
        return 3

    if trust <= 40:
        return 5

    if trust <= 50:
        return 10

    if trust <= 60:
        return 15

    if trust <= 70:
        return 20

    if trust <= 80:
        return 25

    return 30

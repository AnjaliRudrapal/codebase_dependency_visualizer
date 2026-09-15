from database import connect
from models.user import User


def charge(
    email: str,
    amount: float
) -> bool:

    connect()

    user = User(
        email
    )

    return (
        user is not None
        and amount > 0
    )
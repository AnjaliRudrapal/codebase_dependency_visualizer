from dataclasses import dataclass

from config import PAYMENT_PROVIDER


@dataclass
class User:

    email: str

    def payment_provider(self):

        return PAYMENT_PROVIDER
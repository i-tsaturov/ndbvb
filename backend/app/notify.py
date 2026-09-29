"""Customer notifications (SMS / email) rendered from Jinja2 templates."""
from jinja2 import Template

from .models import Notification, User
from .sms import send_sms


def _deliver(db, user: User, body: str) -> None:
    db.add(Notification(user_id=user.id, channel="sms", phone=user.phone, rendered_text=body))
    db.flush()
    send_sms(user.phone, body)


def notify_profile_update(db, user: User) -> None:
    text = Template(
        f"Dear {user.first_name}, your OnlineBank profile was updated. "
        f"If this was not you, call +233 30 000 0000."
    ).render()
    _deliver(db, user, text)


def notify_transfer(db, user: User, amount: float, currency: str, description: str) -> None:
    text = Template(
        f"Dear {user.first_name}, a payment of {amount:.2f} {currency} was posted to your "
        f"account: \"{description}\". Keep this SMS for your records."
    ).render()
    _deliver(db, user, text)


def notify_payment(db, user: User, amount: float, currency: str, description: str) -> None:
    text = Template(
        f"Dear {user.first_name}, payment of {amount:.2f} {currency} was completed: "
        f"\"{description}\". Keep this SMS for your records."
    ).render()
    _deliver(db, user, text)

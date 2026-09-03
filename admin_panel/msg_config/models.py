from django.conf import settings
from django.db import models

DEFAULT_INTEGRATED_NUMBER = "918590123876"
DEFAULT_NAMESPACE = "2a0ae24e_63d6_47b2_85f4_b18d0d9e2acb"

TEMPLATE_OTP = "otp_authentication"
TEMPLATE_REGISTRATION_SUCCESS = "aiswarya_registration_success"
TEMPLATE_SUBSCRIPTION_CONFIRMATION = "aiswarya_subscription_confirmation"


class MsgConfig(models.Model):
    """Singleton MSG91 WhatsApp / OTP settings (pk=1)."""

    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
        db_column="singleton_id",
    )
    development_mode = models.BooleanField(
        default=True,
        help_text="When True, skip real MSG91 sends and expose OTPs for autofill.",
    )
    auth_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="MSG91 authkey. Blank falls back to MSG91_AUTH_KEY env.",
    )
    integrated_number = models.CharField(
        max_length=20,
        default=DEFAULT_INTEGRATED_NUMBER,
        blank=True,
    )
    namespace = models.CharField(
        max_length=64,
        default=DEFAULT_NAMESPACE,
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "msg_config"
        verbose_name = "MSG config"

    def __str__(self):
        return f"MsgConfig(development_mode={self.development_mode})"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def resolve_auth_key(self) -> str:
        key = (self.auth_key or "").strip()
        if key:
            return key
        return (getattr(settings, "MSG91_AUTH_KEY", "") or "").strip()

    def resolve_integrated_number(self) -> str:
        value = (self.integrated_number or "").strip()
        if value:
            return value
        return (
            getattr(settings, "MSG91_INTEGRATED_NUMBER", "") or DEFAULT_INTEGRATED_NUMBER
        ).strip()

    def resolve_namespace(self) -> str:
        value = (self.namespace or "").strip()
        if value:
            return value
        return DEFAULT_NAMESPACE


def is_msg_development_mode() -> bool:
    try:
        return bool(MsgConfig.load().development_mode)
    except Exception:
        return True


def should_expose_otp() -> bool:
    """Single switch for console print + API data.otp autofill."""
    return is_msg_development_mode()


def get_msg91_auth_key() -> str:
    try:
        return MsgConfig.load().resolve_auth_key()
    except Exception:
        return (getattr(settings, "MSG91_AUTH_KEY", "") or "").strip()


def get_msg_config() -> MsgConfig:
    return MsgConfig.load()

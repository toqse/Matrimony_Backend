from django.test import TestCase
from django.test.utils import override_settings

from accounts.models import DummyOTPPhone
from accounts.services import generate_otp, verify_otp


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dummy-otp-tests",
        }
    },
    OTP_LENGTH=6,
)
class DummyOTPPhoneVerifyTests(TestCase):
    phone = "+919876543210"
    dummy = "654321"

    def setUp(self):
        DummyOTPPhone.objects.create(
            phone=self.phone,
            dummy_otp=self.dummy,
            is_active=True,
            note="QA",
        )

    def test_active_dummy_otp_verifies_without_generate(self):
        ok, msg = verify_otp(f"phone:{self.phone}", self.dummy)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "OK")

    def test_dummy_otp_works_for_mobile_and_pwd_reset_identifiers(self):
        ok_mobile, _ = verify_otp(f"mobile:{self.phone}", self.dummy)
        self.assertTrue(ok_mobile)
        # Recreate active row if prior verify left state; dummy match does not need OTPRecord
        ok_reset, _ = verify_otp(f"pwd_reset:mobile:{self.phone}", self.dummy)
        self.assertTrue(ok_reset)

    def test_real_otp_still_works_for_whitelisted_phone(self):
        identifier = f"mobile:{self.phone}"
        real_otp = generate_otp(identifier)
        self.assertNotEqual(real_otp, self.dummy)
        ok, msg = verify_otp(identifier, real_otp)
        self.assertTrue(ok, msg)

    def test_wrong_dummy_rejected_without_real_otp(self):
        ok, msg = verify_otp(f"phone:{self.phone}", "000000")
        self.assertFalse(ok)
        self.assertIn("OTP", msg)

    def test_inactive_phone_dummy_rejected(self):
        DummyOTPPhone.objects.filter(phone=self.phone).update(is_active=False)
        ok, msg = verify_otp(f"phone:{self.phone}", self.dummy)
        self.assertFalse(ok)
        self.assertIn("OTP", msg)

    def test_unknown_phone_dummy_rejected(self):
        ok, msg = verify_otp("phone:+919999999999", self.dummy)
        self.assertFalse(ok)
        self.assertIn("OTP", msg)

    def test_phone_normalized_on_create(self):
        entry = DummyOTPPhone.objects.create(
            phone="9876501234",
            dummy_otp="111222",
            is_active=True,
        )
        self.assertEqual(entry.phone, "+919876501234")
        ok, _ = verify_otp("phone:+919876501234", "111222")
        self.assertTrue(ok)

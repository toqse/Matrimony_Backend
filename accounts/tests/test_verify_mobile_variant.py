from unittest import mock

from django.test import TestCase
from django.test.utils import override_settings

from accounts.models import User
from accounts.views import VerifyMobileView


class VerifyMobileVariantLookupTests(TestCase):
    @override_settings(
        DEBUG_PROPAGATE_EXCEPTIONS=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            }
        },
    )
    @mock.patch("accounts.views.get_verify_otp_response_data")
    @mock.patch("accounts.views.verify_otp")
    def test_verify_mobile_reuses_existing_variant_user(
        self,
        mock_verify_otp,
        mock_response_builder,
    ):
        """
        Bulk upload may store mobile as 10 digits, while login/verify endpoints use +91 E164.
        VerifyMobileView should reuse existing users found via variant lookup and not create
        a second empty user row.
        """
        mock_verify_otp.return_value = (True, "ok")
        mock_response_builder.side_effect = lambda user, tokens, request=None: {
            "matri_id": user.matri_id
        }

        existing = User.objects.create_user(
            mobile="9876543210",
            password="x",
            name="Bulk User",
            role="user",
        )
        existing.is_active = True
        existing.mobile_verified = True
        existing.save(update_fields=["is_active", "mobile_verified", "updated_at"])

        from rest_framework.test import APIRequestFactory

        req = APIRequestFactory().post(
            "/api/v1/auth/verify/mobile/",
            {"mobile": "+919876543210", "otp": "123456"},
            format="json",
        )
        resp = VerifyMobileView.as_view()(req)

        if resp.status_code != 200:
            self.fail(f"Unexpected status={resp.status_code}, data={getattr(resp, 'data', None)}")
        self.assertTrue(resp.data.get("success"))
        self.assertEqual(resp.data["data"]["matri_id"], existing.matri_id)

        # No duplicate should be created for +91 variant.
        self.assertEqual(
            User.objects.filter(mobile__in=["+919876543210", "919876543210", "9876543210"]).count(),
            1,
        )


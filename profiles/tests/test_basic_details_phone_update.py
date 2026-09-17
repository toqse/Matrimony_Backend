"""BasicDetailsUpdateSerializer accepts phone and updates User.mobile."""
from django.test import TestCase

from accounts.models import User
from profiles.serializers import BasicDetailsUpdateSerializer


class BasicDetailsPhoneUpdateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile="+919300000101",
            password="x",
            role="user",
            name="Phone Edit Member",
        )
        self.other = User.objects.create_user(
            mobile="+919300000102",
            password="x",
            role="user",
            name="Other Member",
        )

    def test_update_phone_success(self):
        ser = BasicDetailsUpdateSerializer(
            self.user,
            data={"phone": "9876543210"},
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        ser.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.mobile, "+919876543210")

    def test_same_phone_allowed_for_same_user(self):
        ser = BasicDetailsUpdateSerializer(
            self.user,
            data={"phone": "+919300000101"},
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_rejects_phone_in_use_by_another_member(self):
        ser = BasicDetailsUpdateSerializer(
            self.user,
            data={"phone": "9300000102"},
            partial=True,
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("phone", ser.errors)

    def test_rejects_blank_phone(self):
        ser = BasicDetailsUpdateSerializer(
            self.user,
            data={"phone": ""},
            partial=True,
        )
        self.assertFalse(ser.is_valid())
        self.assertIn("phone", ser.errors)

    def test_omitted_phone_does_not_clear_mobile(self):
        ser = BasicDetailsUpdateSerializer(
            self.user,
            data={"name": "Renamed"},
            partial=True,
        )
        self.assertTrue(ser.is_valid(), ser.errors)
        ser.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Renamed")
        self.assertEqual(self.user.mobile, "+919300000101")

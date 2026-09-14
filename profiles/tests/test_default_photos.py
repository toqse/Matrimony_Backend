"""Gender default photos on admin/staff profile create."""
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.staff_profiles.registration import create_user_and_profile_sections
from profiles.default_photos import (
    apply_gender_default_photos,
    display_photo_urls,
    users_needing_default_photos,
)
from profiles.models import UserPhotos

LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "gender-default-photos-tests",
    }
}


def _png_upload(name: str, color=(255, 0, 0)) -> SimpleUploadedFile:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(CACHES=LOCMEM_CACHES)
class GenderDefaultPhotosCreateTests(TestCase):
    def setUp(self):
        self.media_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.media_tmp.name)
        media.enable()
        self.addCleanup(media.disable)

    def _create(self, *, mobile: str, gender: str, files=None, name="Member"):
        return create_user_and_profile_sections(
            name=name,
            mobile=mobile,
            gender=gender,
            dob_iso="1995-01-15",
            email=None,
            branch_pk=None,
            data={},
            files=files or {},
        )

    def test_male_create_without_photos_gets_male_defaults(self):
        user = self._create(mobile="+919811101001", gender="M", name="Male Default")
        photos = UserPhotos.objects.get(user=user)
        self.assertTrue(photos.profile_photo)
        self.assertTrue(photos.full_photo)
        self.assertIn("aiswarya_male_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_male_full", Path(photos.full_photo.name).stem)

    def test_female_create_without_photos_gets_female_defaults(self):
        user = self._create(mobile="+919811101002", gender="F", name="Female Default")
        photos = UserPhotos.objects.get(user=user)
        self.assertTrue(photos.profile_photo)
        self.assertTrue(photos.full_photo)
        self.assertIn("aiswarya_female_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_female_full", Path(photos.full_photo.name).stem)

    def test_uploaded_profile_photo_is_not_replaced(self):
        upload = _png_upload("custom_profile.png")
        user = self._create(
            mobile="+919811101003",
            gender="F",
            files={"profile_photo": upload},
            name="Partial Upload",
        )
        photos = UserPhotos.objects.get(user=user)
        self.assertIn("custom_profile", Path(photos.profile_photo.name).stem)
        self.assertNotIn("aiswarya_female_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_female_full", Path(photos.full_photo.name).stem)

    def test_other_gender_does_not_get_defaults(self):
        user = self._create(mobile="+919811101004", gender="O", name="Other Gender")
        self.assertFalse(UserPhotos.objects.filter(user=user).exists())


@override_settings(CACHES=LOCMEM_CACHES)
class GenderDefaultPhotosExistingTests(TestCase):
    def setUp(self):
        self.media_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.media_tmp.name)
        media.enable()
        self.addCleanup(media.disable)

    def _existing(self, *, mobile: str, gender: str, name="Existing"):
        return User.objects.create_user(
            mobile=mobile,
            password="x",
            role="user",
            name=name,
            gender=gender,
        )

    def test_existing_male_without_photos_gets_defaults(self):
        user = self._existing(mobile="+919811101101", gender="M", name="Existing Male")
        self.assertTrue(apply_gender_default_photos(user))
        photos = UserPhotos.objects.get(user=user)
        self.assertIn("aiswarya_male_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_male_full", Path(photos.full_photo.name).stem)

    def test_existing_female_without_photos_gets_defaults(self):
        user = self._existing(mobile="+919811101102", gender="F", name="Existing Female")
        self.assertTrue(apply_gender_default_photos(user))
        photos = UserPhotos.objects.get(user=user)
        self.assertIn("aiswarya_female_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_female_full", Path(photos.full_photo.name).stem)

    def test_existing_upload_is_not_replaced(self):
        user = self._existing(mobile="+919811101103", gender="M", name="Has File")
        photos = UserPhotos.objects.create(user=user)
        photos.profile_photo.save("custom_existing.png", _png_upload("custom_existing.png"), save=True)
        apply_gender_default_photos(user)
        photos.refresh_from_db()
        self.assertIn("custom_existing", Path(photos.profile_photo.name).stem)
        self.assertNotIn("aiswarya_male_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_male_full", Path(photos.full_photo.name).stem)

    def test_profile_photo_url_skips_default_profile_file(self):
        user = self._existing(mobile="+919811101104", gender="F", name="Url Only")
        UserPhotos.objects.create(user=user, profile_photo_url="https://example.com/photo.jpg")
        apply_gender_default_photos(user)
        photos = UserPhotos.objects.get(user=user)
        self.assertEqual(photos.profile_photo_url, "https://example.com/photo.jpg")
        self.assertFalse(photos.profile_photo)
        self.assertIn("aiswarya_female_full", Path(photos.full_photo.name).stem)

    def test_command_backfills_existing_profiles(self):
        user = self._existing(mobile="+919811101105", gender="F", name="Backfill Me")
        self.assertTrue(users_needing_default_photos().filter(pk=user.pk).exists())
        call_command("apply_gender_default_photos")
        photos = UserPhotos.objects.get(user=user)
        self.assertIn("aiswarya_female_profile", Path(photos.profile_photo.name).stem)
        self.assertIn("aiswarya_female_full", Path(photos.full_photo.name).stem)
        self.assertFalse(users_needing_default_photos().filter(pk=user.pk).exists())

    def test_command_dry_run_does_not_write(self):
        user = self._existing(mobile="+919811101106", gender="M", name="Dry Run")
        call_command("apply_gender_default_photos", dry_run=True)
        self.assertFalse(UserPhotos.objects.filter(user=user).exists())


@override_settings(CACHES=LOCMEM_CACHES)
class GenderDefaultPhotosListingTests(TestCase):
    def setUp(self):
        self.media_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.media_tmp.name)
        media.enable()
        self.addCleanup(media.disable)
        self.client = APIClient()
        self.viewer = User.objects.create_user(
            mobile="+919811101201",
            password="x",
            role="user",
            name="Viewer",
            gender="M",
            is_active=True,
        )
        self.female = User.objects.create_user(
            mobile="+919811101202",
            password="x",
            role="user",
            name="Anju",
            gender="F",
            is_active=True,
        )
        self.client.force_authenticate(user=self.viewer)

    def test_display_photo_urls_fills_female_default(self):
        request = RequestFactory().get("/")
        profile_url, full_url = display_photo_urls(request, self.female)
        self.assertIsNotNone(profile_url)
        self.assertIn("aiswarya_female_profile", profile_url)
        self.assertIsNotNone(full_url)
        self.assertIn("aiswarya_female_full", full_url)
        photos = UserPhotos.objects.get(user=self.female)
        self.assertIn("aiswarya_female_profile", Path(photos.profile_photo.name).stem)

    def test_matches_list_returns_female_default_photo(self):
        res = self.client.get("/api/v1/matches/", {"page": 1, "limit": 20})
        self.assertEqual(res.status_code, 200)
        row = next(
            p for p in res.data["data"]["profiles"] if p["matri_id"] == self.female.matri_id
        )
        self.assertTrue(row["profile_photo"])
        self.assertIn("aiswarya_female_profile", row["profile_photo"])

    def test_dashboard_new_matches_returns_female_default_photo(self):
        res = self.client.get("/api/v1/dashboard/new-matches/")
        self.assertEqual(res.status_code, 200)
        row = next(p for p in res.data["data"] if p["matri_id"] == self.female.matri_id)
        self.assertTrue(row["profile_photo"])
        self.assertIn("aiswarya_female_profile", row["profile_photo"])

    def test_profile_photo_url_is_used_instead_of_default_file(self):
        UserPhotos.objects.create(
            user=self.female, profile_photo_url="https://example.com/remote.jpg"
        )
        request = RequestFactory().get("/")
        profile_url, _full_url = display_photo_urls(request, self.female)
        self.assertEqual(profile_url, "https://example.com/remote.jpg")

    def test_today_picks_includes_female_without_photos(self):
        res = self.client.get("/api/v1/dashboard/today-picks/")
        self.assertEqual(res.status_code, 200)
        row = next(p for p in res.data["data"] if p["matri_id"] == self.female.matri_id)
        self.assertEqual(row.get("gender"), "F")
        self.assertTrue(row["profile_photo"])
        self.assertIn("aiswarya_female_profile", row["profile_photo"])

    def test_matches_list_includes_gender(self):
        res = self.client.get("/api/v1/matches/", {"page": 1, "limit": 20})
        self.assertEqual(res.status_code, 200)
        row = next(
            p for p in res.data["data"]["profiles"] if p["matri_id"] == self.female.matri_id
        )
        self.assertEqual(row.get("gender"), "F")

    def test_dashboard_new_matches_includes_gender(self):
        res = self.client.get("/api/v1/dashboard/new-matches/")
        self.assertEqual(res.status_code, 200)
        row = next(p for p in res.data["data"] if p["matri_id"] == self.female.matri_id)
        self.assertEqual(row.get("gender"), "F")

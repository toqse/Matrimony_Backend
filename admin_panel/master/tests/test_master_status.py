from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from admin_panel.auth.models import AdminUser
from master.models import Caste, Education, EducationSubject, MotherTongue, Occupation, Religion
from profiles.models import UserReligion


LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "master-status-tests",
    }
}

RELIGIONS = "/api/v1/admin/master/religions/"
CASTES = "/api/v1/admin/master/castes/"
MOTHER_TONGUES = "/api/v1/admin/master/mother-tongues/"
EDUCATIONS = "/api/v1/admin/master/educations/"
EDUCATION_SUBJECTS = "/api/v1/admin/master/education-subjects/"
OCCUPATIONS = "/api/v1/admin/master/occupations/"


@override_settings(
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
    CACHES=LOCMEM_CACHES,
)
class MasterToggleStatusTests(TestCase):
    def setUp(self):
        self.admin = AdminUser.objects.create(
            mobile="+919900000501",
            role=AdminUser.ROLE_ADMIN,
            name="Master Admin",
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.religion = Religion.objects.create(name="Hindu", is_active=True)
        self.caste = Caste.objects.create(religion=self.religion, name="Nair", is_active=True)
        self.tongue = MotherTongue.objects.create(name="Malayalam", is_active=True)
        self.education = Education.objects.create(name="B.Tech", is_active=True)
        self.subject = EducationSubject.objects.create(name="Computer Science", is_active=True)
        self.occupation = Occupation.objects.create(name="Engineer", is_active=True)

    def test_deactivate_religion_when_used(self):
        member = User.objects.create_user(mobile="9300000501", password="x", role="user")
        UserReligion.objects.create(user=member, religion=self.religion)

        res = self.client.delete(f"{RELIGIONS}{self.religion.id}/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Deactivate instead", res.data["error"]["message"])

        res = self.client.patch(f"{RELIGIONS}{self.religion.id}/toggle-status/")
        self.assertEqual(res.status_code, 200, res.data)
        self.religion.refresh_from_db()
        self.caste.refresh_from_db()
        self.assertFalse(self.religion.is_active)
        self.assertFalse(self.caste.is_active)

        listed = self.client.get(RELIGIONS)
        names = {row["name"]: row["is_active"] for row in listed.data["data"]["results"]}
        self.assertIn("Hindu", names)
        self.assertFalse(names["Hindu"])

    def test_toggle_caste_mother_tongue_education_occupation(self):
        for url, obj in (
            (f"{CASTES}{self.caste.id}/toggle-status/", self.caste),
            (f"{MOTHER_TONGUES}{self.tongue.id}/toggle-status/", self.tongue),
            (f"{EDUCATIONS}{self.education.id}/toggle-status/", self.education),
            (f"{EDUCATION_SUBJECTS}{self.subject.id}/toggle-status/", self.subject),
            (f"{OCCUPATIONS}{self.occupation.id}/toggle-status/", self.occupation),
        ):
            res = self.client.patch(url)
            self.assertEqual(res.status_code, 200, res.data)
            obj.refresh_from_db()
            self.assertFalse(obj.is_active, url)
            res = self.client.patch(url)
            self.assertEqual(res.status_code, 200, res.data)
            obj.refresh_from_db()
            self.assertTrue(obj.is_active, url)

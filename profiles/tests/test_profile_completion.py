"""Live 7-step completion % (partial family) is shared by user site and admin list."""
from django.test import TestCase

from accounts.models import User
from admin_panel.my_profiles.views import _completeness_percent
from admin_panel.profile_admin.views import _build_list_row
from profiles.models import (
    UserEducation,
    UserFamily,
    UserLocation,
    UserPersonal,
    UserPhotos,
    UserProfile,
    UserReligion,
)
from profiles.utils import (
    _PROFILE_SECTION_RELS,
    get_profile_completion_data,
    get_profile_completion_percentage,
)


class ProfileCompletionPercentageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            mobile='9100000095', password='x', role='user', name='John Doe'
        )
        UserLocation.objects.create(user=self.user, address='Kochi')
        UserReligion.objects.create(user=self.user, caste='Nair')
        UserPersonal.objects.create(user=self.user, colour='Fair')
        UserEducation.objects.create(user=self.user, employment_status='Employed')
        UserPhotos.objects.create(
            user=self.user, profile_photo_url='https://example.com/photo.jpg'
        )
        UserFamily.objects.create(
            user=self.user,
            father_name='Rajan',
            father_occupation='Teacher',
            mother_name='Latha',
            mother_occupation='Nurse',
            about_family='Close-knit family',
            family_type='Nuclear',
        )
        UserProfile.objects.create(
            user=self.user,
            about_me='Software engineer from Kochi.',
            location_completed=True,
            religion_completed=True,
            personal_completed=True,
            family_completed=False,
            education_completed=True,
            about_completed=True,
            photos_completed=False,
        )

    def _prefetched_user(self):
        return (
            User.objects.filter(pk=self.user.pk)
            .select_related(*_PROFILE_SECTION_RELS)
            .get()
        )

    def test_partial_family_is_95_not_stale_flag_percent(self):
        """6 complete steps + 6/9 family fields -> 95, not 71 (flags) or 85."""
        prefetched = self._prefetched_user()
        self.assertFalse(prefetched.user_profile.photos_completed)
        self.assertFalse(prefetched.user_profile.family_completed)

        live = get_profile_completion_percentage(prefetched, ensure_loaded=False)
        self.assertEqual(live, 95)
        self.assertEqual(_build_list_row(prefetched)['completion_percent'], 95)
        self.assertEqual(_completeness_percent(prefetched), 95)

        data = get_profile_completion_data(self.user)
        self.assertEqual(data['profile_completion_percentage'], 95)
        self.assertNotEqual(data['profile_completion_percentage'], 71)
        self.assertNotEqual(data['profile_completion_percentage'], 85)

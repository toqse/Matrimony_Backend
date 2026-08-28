"""
Tests for horoscope support during profile creation.

Covers:
    - profile created without horoscope
    - profile created with horoscope
    - validation failures when has_horoscope is true
    - automatic horoscope_profile (bridge) record creation
    - the create_horoscope_profile service defaults (is_calculated=0, calculated_at=None)
    - end-to-end staff create-profile flow wiring
"""
from datetime import date, time

from django.test import TestCase
from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.models import User
from astrology.models import HoroscopeProfile
from astrology.services.horoscope_profile_service import (
    DEFAULT_TIMEZONE,
    HoroscopeInputSerializer,
    _coords_are_usable,
    _resolve_birth_coordinates,
    apply_profile_creation_horoscope,
    create_horoscope_profile,
    normalize_horoscope_payload,
    parse_timezone_to_offset,
    validate_horoscope_input,
)
from profiles.models import UserProfile


def _member(mobile: str, name: str = "Test Member", dob: date | None = date(1996, 5, 17)) -> User:
    user = User.objects.create_user(mobile=mobile, password="x", name=name, role="user")
    user.dob = dob
    user.is_active = True
    user.save(update_fields=["dob", "is_active"])
    return user


class HoroscopeInputSerializerTests(TestCase):
    """Validation rules for the horoscope fields on the Profile Create API."""

    def test_no_horoscope_requires_nothing(self):
        serializer = HoroscopeInputSerializer(
            data={"has_horoscope": False}, context={"date_of_birth": None}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertFalse(serializer.validated_data["has_horoscope"])

    def test_missing_birth_time_and_place_fail(self):
        serializer = HoroscopeInputSerializer(
            data={"has_horoscope": True},
            context={"date_of_birth": "1996-05-17"},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("birth_time", serializer.errors)
        self.assertIn("birth_place", serializer.errors)

    def test_missing_dob_fails(self):
        serializer = HoroscopeInputSerializer(
            data={
                "has_horoscope": True,
                "birth_time": "10:30",
                "birth_place": "Chennai",
            },
            context={"date_of_birth": None},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("date_of_birth", serializer.errors)

    def test_valid_when_complete(self):
        data = {
            "has_horoscope": True,
            "birth_time": "10:30",
            "birth_place": "Chennai",
            "birth_latitude": 13.0827,
            "birth_longitude": 80.2707,
            "birth_timezone": 5.5,
        }
        normalized = validate_horoscope_input(data, date_of_birth="1996-05-17")
        self.assertEqual(normalized["birth_time"], time(10, 30))
        self.assertEqual(normalized["birth_place"], "Chennai")
        self.assertAlmostEqual(normalized["birth_latitude"], 13.0827)

    def test_validate_horoscope_input_raises(self):
        with self.assertRaises(DRFValidationError):
            validate_horoscope_input(
                {"has_horoscope": True}, date_of_birth="1996-05-17"
            )

    def test_accepts_frontend_field_aliases(self):
        """Frontend sends place_of_birth, latitude, longitude, timezone name."""
        data = {
            "has_horoscope": True,
            "time_of_birth": "15:54",
            "place_of_birth": "Kottayam, Kerala, India",
            "latitude": 9.6287383,
            "longitude": 76.6455326,
            "timezone": "Asia/Kolkata",
        }
        normalized = validate_horoscope_input(data, date_of_birth="1990-01-15")
        self.assertEqual(normalized["birth_place"], "Kottayam, Kerala, India")
        self.assertEqual(normalized["birth_time"], time(15, 54))
        self.assertAlmostEqual(normalized["birth_latitude"], 9.6287383, places=6)
        self.assertAlmostEqual(normalized["birth_longitude"], 76.6455326, places=6)
        self.assertAlmostEqual(normalized["birth_timezone"], 5.5)

    def test_canonical_keys_take_precedence_over_aliases(self):
        payload = {
            "has_horoscope": True,
            "birth_time": "10:00",
            "birth_place": "Canonical Place",
            "place_of_birth": "Alias Place",
            "birth_latitude": 1.0,
            "latitude": 99.0,
        }
        mapped = normalize_horoscope_payload(payload)
        self.assertEqual(mapped["birth_place"], "Canonical Place")
        self.assertEqual(mapped["birth_latitude"], 1.0)


class ParseTimezoneToOffsetTests(TestCase):
    def test_numeric_and_string_offset(self):
        self.assertAlmostEqual(parse_timezone_to_offset(5.5), 5.5)
        self.assertAlmostEqual(parse_timezone_to_offset("5.5"), 5.5)
        self.assertAlmostEqual(parse_timezone_to_offset("+05:30"), 5.5)
        self.assertAlmostEqual(parse_timezone_to_offset("UTC+5:30"), 5.5)

    def test_iana_name_asia_kolkata(self):
        self.assertAlmostEqual(parse_timezone_to_offset("Asia/Kolkata"), 5.5)

    def test_junk_returns_none(self):
        self.assertIsNone(parse_timezone_to_offset("not-a-timezone"))
        self.assertIsNone(parse_timezone_to_offset(""))
        self.assertIsNone(parse_timezone_to_offset(None))


class CreateHoroscopeProfileServiceTests(TestCase):
    def setUp(self):
        self.user = _member("+919800000001", "Service Member")

    def test_create_horoscope_profile_defaults(self):
        # Remove the auto-created (empty) bridge row so we test creation cleanly.
        HoroscopeProfile.objects.filter(user=self.user).delete()

        hp = create_horoscope_profile(
            user=self.user,
            name="Service Member",
            dob=date(1996, 5, 17),
            birth_time=time(10, 30),
            birth_latitude=13.0827,
            birth_longitude=80.2707,
            birth_timezone=5.5,
        )

        self.assertTrue(HoroscopeProfile.objects.filter(user=self.user).exists())
        self.assertEqual(hp.pr_name, "Service Member")
        self.assertEqual(hp.pr_dob, date(1996, 5, 17))
        self.assertEqual(hp.pr_tob, time(10, 30))
        self.assertAlmostEqual(hp.pr_lat, 13.0827)
        self.assertAlmostEqual(hp.pr_lon, 80.2707)
        self.assertAlmostEqual(hp.pr_tz, 5.5)
        # Future ready: never calculated during profile creation.
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)

    def test_create_horoscope_profile_defaults_timezone(self):
        hp = create_horoscope_profile(user=self.user, birth_time=time(9, 0))
        self.assertAlmostEqual(hp.pr_tz, DEFAULT_TIMEZONE)
        self.assertFalse(hp.is_calculated)

    def test_create_horoscope_profile_clears_outputs_when_inputs_change(self):
        hp = HoroscopeProfile.objects.get(user=self.user)
        hp.pr_tob = time(8, 0)
        hp.pr_lat = 9.0
        hp.pr_lon = 76.0
        hp.pr_tz = 5.5
        hp.pr_rasi = 'AAAAAAAAAAA'
        hp.pr_star = 5
        hp.star_name = 'Rohini'
        hp.is_calculated = True
        hp.save()

        updated = create_horoscope_profile(
            user=self.user,
            name=self.user.name,
            dob=self.user.dob,
            birth_time=time(6, 15),
            birth_latitude=11.2588,
            birth_longitude=75.7804,
            birth_timezone=5.5,
        )
        self.assertEqual(updated.pr_tob, time(6, 15))
        self.assertFalse(updated.pr_rasi)
        self.assertIsNone(updated.pr_star)
        self.assertEqual(updated.star_name, '')
        self.assertFalse(updated.is_calculated)
        self.assertFalse(updated.is_exe_done())

    def test_create_horoscope_profile_keeps_outputs_when_inputs_unchanged(self):
        hp = HoroscopeProfile.objects.get(user=self.user)
        hp.pr_tob = time(8, 0)
        hp.pr_lat = 9.0
        hp.pr_lon = 76.0
        hp.pr_tz = 5.5
        hp.pr_dob = self.user.dob
        hp.pr_rasi = 'AAAAAAAAAAA'
        hp.pr_star = 5
        hp.is_calculated = True
        hp.save()

        updated = create_horoscope_profile(
            user=self.user,
            name=self.user.name,
            dob=self.user.dob,
            birth_time=time(8, 0),
            birth_latitude=9.0,
            birth_longitude=76.0,
            birth_timezone=5.5,
        )
        self.assertEqual(updated.pr_rasi, 'AAAAAAAAAAA')
        self.assertEqual(updated.pr_star, 5)
        self.assertFalse(updated.is_calculated)
        self.assertTrue(updated.is_exe_done())


class ApplyProfileCreationHoroscopeTests(TestCase):
    def test_profile_without_horoscope(self):
        user = _member("+919800000010", "No Horo")
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})

        result = apply_profile_creation_horoscope(
            user=user,
            profile=profile,
            horoscope_input={"has_horoscope": False},
            name=user.name,
            dob=user.dob,
        )

        self.assertIsNone(result)
        profile.refresh_from_db()
        self.assertFalse(profile.has_horoscope)
        # The bridge row (auto-created on register) is not populated with birth data.
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertIsNone(hp.pr_tob)

    def test_profile_with_horoscope_creates_bridge(self):
        user = _member("+919800000011", "With Horo")
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})

        result = apply_profile_creation_horoscope(
            user=user,
            profile=profile,
            horoscope_input={
                "has_horoscope": True,
                "birth_time": time(14, 15),
                "birth_place": "Madurai",
                "birth_latitude": 9.9252,
                "birth_longitude": 78.1198,
                "birth_timezone": 5.5,
            },
            name=user.name,
            dob=user.dob,
        )

        self.assertIsNotNone(result)
        # Profile persisted birth inputs.
        profile.refresh_from_db()
        self.assertTrue(profile.has_horoscope)
        self.assertEqual(profile.time_of_birth, time(14, 15))
        self.assertEqual(profile.place_of_birth, "Madurai")
        self.assertAlmostEqual(profile.birth_latitude, 9.9252)
        self.assertAlmostEqual(profile.birth_longitude, 78.1198)
        self.assertAlmostEqual(profile.birth_timezone, 5.5)

        # Bridge record automatically populated, not calculated.
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertEqual(hp.pr_tob, time(14, 15))
        self.assertAlmostEqual(hp.pr_lat, 9.9252)
        self.assertAlmostEqual(hp.pr_lon, 78.1198)
        self.assertAlmostEqual(hp.pr_tz, 5.5)
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)


class KochiCoordinateResolutionTests(TestCase):
    """Kochi place + coordinates must land in horoscope_profile.pr_lat/pr_lon."""

    KOCHI_LAT = 9.9312
    KOCHI_LON = 76.2673

    def test_coords_are_usable_rejects_zero_placeholder(self):
        self.assertFalse(_coords_are_usable(0, 0))
        self.assertTrue(_coords_are_usable(self.KOCHI_LAT, self.KOCHI_LON))

    def test_resolve_from_place_when_frontend_sends_zero(self):
        lat, lon = _resolve_birth_coordinates('Kochi', 0, 0)
        self.assertAlmostEqual(lat, self.KOCHI_LAT, places=4)
        self.assertAlmostEqual(lon, self.KOCHI_LON, places=4)

    def test_kochi_explicit_coords_stored_in_horoscope_profile(self):
        user = _member('+919800000020', 'Kochi Explicit')
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})

        apply_profile_creation_horoscope(
            user=user,
            profile=profile,
            horoscope_input={
                'has_horoscope': True,
                'birth_time': time(10, 30),
                'birth_place': 'Kochi',
                'birth_latitude': self.KOCHI_LAT,
                'birth_longitude': self.KOCHI_LON,
                'birth_timezone': 5.5,
            },
            name=user.name,
            dob=user.dob,
        )

        hp = HoroscopeProfile.objects.get(user=user)
        self.assertAlmostEqual(hp.pr_lat, self.KOCHI_LAT, places=4)
        self.assertAlmostEqual(hp.pr_lon, self.KOCHI_LON, places=4)
        self.assertAlmostEqual(hp.pr_tz, 5.5)

    def test_kochi_zero_coords_resolved_from_place(self):
        user = _member('+919800000021', 'Kochi Zero')
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={})

        apply_profile_creation_horoscope(
            user=user,
            profile=profile,
            horoscope_input={
                'has_horoscope': True,
                'birth_time': time(10, 30),
                'birth_place': 'Kochi',
                'birth_latitude': 0,
                'birth_longitude': 0,
                'birth_timezone': 5.5,
            },
            name=user.name,
            dob=user.dob,
        )

        hp = HoroscopeProfile.objects.get(user=user)
        self.assertAlmostEqual(hp.pr_lat, self.KOCHI_LAT, places=4)
        self.assertAlmostEqual(hp.pr_lon, self.KOCHI_LON, places=4)
        profile.refresh_from_db()
        self.assertAlmostEqual(profile.birth_latitude, self.KOCHI_LAT, places=4)
        self.assertAlmostEqual(profile.birth_longitude, self.KOCHI_LON, places=4)


class StaffCreateProfileHoroscopeTests(TestCase):
    """End-to-end wiring through the staff create-profile service."""

    def setUp(self):
        from admin_panel.auth.models import AdminUser
        from admin_panel.branches.models import Branch as PanelBranch
        from admin_panel.staff_mgmt.models import StaffProfile
        from master.models import Branch as MasterBranch

        self.master_branch = MasterBranch.objects.create(name="HoroBranch", code="HORO01")
        PanelBranch.objects.create(
            name="HoroBranch Panel",
            code="HORO01",
            city="City",
            phone="9999900000",
            email="horo01@test.invalid",
        )
        admin_user = AdminUser.objects.create(
            mobile="9000000010", name="Horo Staff", role=AdminUser.ROLE_STAFF
        )
        self.staff = StaffProfile.objects.create(
            admin_user=admin_user,
            emp_code="EMP900",
            name="Horo Staff",
            mobile="9000000010",
            branch_id=PanelBranch.objects.get(code="HORO01").pk,
            designation="Counsellor",
        )

    def _create(self, data):
        from admin_panel.staff_profiles.registration import create_user_and_profile_sections

        return create_user_and_profile_sections(
            name=data["name"],
            mobile=data["mobile"],
            gender="F",
            dob_iso="2000-03-24",
            email=None,
            branch_pk=self.master_branch.pk,
            data=data,
            files={},
            staff=self.staff,
        )

    def test_staff_create_without_horoscope(self):
        user = self._create({"name": "Plain Profile", "mobile": "+919811100001"})
        self.assertFalse(user.user_profile.has_horoscope)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertIsNone(hp.pr_tob)

    def test_staff_create_with_horoscope(self):
        user = self._create(
            {
                "name": "Horo Profile",
                "mobile": "+919811100002",
                "has_horoscope": True,
                "birth_time": "06:45",
                "birth_place": "Coimbatore",
                "birth_latitude": 11.0168,
                "birth_longitude": 76.9558,
                "birth_timezone": 5.5,
            }
        )
        self.assertTrue(user.user_profile.has_horoscope)
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertEqual(hp.pr_tob, time(6, 45))
        self.assertAlmostEqual(hp.pr_lat, 11.0168)
        self.assertAlmostEqual(hp.pr_tz, 5.5)
        self.assertFalse(hp.is_calculated)
        self.assertIsNone(hp.calculated_at)

    def test_staff_create_validation_failure(self):
        with self.assertRaises(DRFValidationError):
            self._create(
                {
                    "name": "Bad Horo",
                    "mobile": "+919811100003",
                    "has_horoscope": True,
                }
            )
        # No user should be created when validation fails (rolled back / pre-write).
        self.assertFalse(User.objects.filter(mobile="+919811100003").exists())

    def test_staff_create_kochi_with_zero_coords_resolves_from_place(self):
        user = self._create(
            {
                "name": "Kochi Staff",
                "mobile": "+919811100004",
                "has_horoscope": True,
                "birth_time": "10:30",
                "birth_place": "Kochi",
                "birth_latitude": 0,
                "birth_longitude": 0,
                "birth_timezone": 5.5,
            }
        )
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertAlmostEqual(hp.pr_lat, 9.9312, places=4)
        self.assertAlmostEqual(hp.pr_lon, 76.2673, places=4)

    def test_staff_create_frontend_alias_payload_kottayam(self):
        """Matches UI: place_of_birth, latitude, longitude, timezone=Asia/Kolkata."""
        user = self._create(
            {
                "name": "Kottayam Frontend",
                "mobile": "+919811100005",
                "has_horoscope": True,
                "time_of_birth": "15:54",
                "place_of_birth": "Kottayam, Kerala, India",
                "latitude": 9.6287383,
                "longitude": 76.6455326,
                "timezone": "Asia/Kolkata",
            }
        )
        hp = HoroscopeProfile.objects.get(user=user)
        self.assertAlmostEqual(hp.pr_lat, 9.6287383, places=6)
        self.assertAlmostEqual(hp.pr_lon, 76.6455326, places=6)
        self.assertAlmostEqual(hp.pr_tz, 5.5)
        self.assertEqual(hp.pr_tob, time(15, 54))
        profile = user.user_profile
        self.assertEqual(profile.place_of_birth, "Kottayam, Kerala, India")

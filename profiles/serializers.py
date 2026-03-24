"""
Profile serializers for location, religion, personal, education, about, photos.
GET response serializers and PATCH input serializers for profile section APIs.
"""
from rest_framework import serializers
from accounts.models import User
from .models import (
    UserProfile, UserLocation, UserReligion, UserPersonal,
    UserFamily, UserEducation, UserPhotos,
)
from core.media import absolute_media_url


class UserLocationSerializer(serializers.Serializer):
    country_id = serializers.IntegerField(required=False, allow_null=True)
    state_id = serializers.IntegerField(required=False, allow_null=True)
    district_id = serializers.IntegerField(required=False, allow_null=True)
    city_id = serializers.IntegerField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_country_id(self, value):
        if value is None:
            return value
        from master.models import Country
        if not Country.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'Country with id {value} does not exist.')
        return value

    def validate_state_id(self, value):
        if value is None:
            return value
        from master.models import State
        if not State.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'State with id {value} does not exist.')
        return value

    def validate_district_id(self, value):
        if value is None:
            return value
        from master.models import District
        if not District.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'District with id {value} does not exist.')
        return value

    def validate_city_id(self, value):
        if value is None:
            return value
        from master.models import City
        if not City.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f'City with id {value} does not exist.')
        return value

    def create(self, validated_data):
        user = self.context['request'].user
        defaults = {'address': validated_data.get('address', '')}
        if validated_data.get('country_id'):
            defaults['country_id'] = validated_data['country_id']
        if validated_data.get('state_id'):
            defaults['state_id'] = validated_data['state_id']
        if validated_data.get('district_id'):
            defaults['district_id'] = validated_data['district_id']
        if validated_data.get('city_id'):
            defaults['city_id'] = validated_data['city_id']
        obj, _ = UserLocation.objects.update_or_create(user=user, defaults=defaults)
        return obj


class UserReligionSerializer(serializers.Serializer):
    religion_id = serializers.IntegerField(required=False, allow_null=True)
    caste_id = serializers.IntegerField(required=False, allow_null=True)
    mother_tongue_id = serializers.IntegerField(required=False, allow_null=True)
    partner_religion_preference = serializers.CharField(required=False, allow_blank=True)
    partner_preference_type = serializers.ChoiceField(
        choices=['own_religion_only', 'open_to_all', 'specific_religions'],
        required=False
    )
    partner_religion_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    partner_caste_preference = serializers.ChoiceField(
        choices=['any', 'own_caste_only'],
        required=False
    )

    def validate_religion_id(self, value):
        if value is None:
            return value
        from master.models import Religion
        if not Religion.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError(f'Religion with id {value} does not exist or is inactive.')
        return value

    def validate_caste_id(self, value):
        if value is None:
            return value
        from master.models import Caste
        if not Caste.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError(f'Caste with id {value} does not exist or is inactive.')
        return value

    def validate_mother_tongue_id(self, value):
        if value is None:
            return value
        from master.models import MotherTongue
        if not MotherTongue.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError(f'Mother tongue with id {value} does not exist or is inactive.')
        return value

    def validate(self, attrs):
        pref_type = attrs.get('partner_preference_type')
        religion_ids = attrs.get('partner_religion_ids')
        if pref_type == 'specific_religions' and religion_ids is not None:
            from master.models import Religion
            existing = set(
                Religion.objects.filter(pk__in=religion_ids, is_active=True).values_list('pk', flat=True)
            )
            invalid = [i for i in religion_ids if i not in existing]
            if invalid:
                raise serializers.ValidationError({
                    'partner_religion_ids': f'Invalid or inactive religion id(s): {invalid}.'
                })
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        defaults = {
            'partner_religion_preference': validated_data.get('partner_religion_preference', ''),
        }
        if validated_data.get('religion_id') is not None:
            defaults['religion_id'] = validated_data['religion_id']
        if validated_data.get('caste_id') is not None:
            defaults['caste_fk_id'] = validated_data['caste_id']
        if validated_data.get('mother_tongue_id') is not None:
            defaults['mother_tongue_id'] = validated_data['mother_tongue_id']
        if 'partner_preference_type' in validated_data:
            defaults['partner_preference_type'] = validated_data['partner_preference_type']
        if 'partner_religion_ids' in validated_data:
            defaults['partner_religion_ids'] = validated_data['partner_religion_ids']
        if 'partner_caste_preference' in validated_data:
            defaults['partner_caste_preference'] = validated_data['partner_caste_preference']
        obj, _ = UserReligion.objects.update_or_create(user=user, defaults=defaults)
        return obj


class UserPersonalSerializer(serializers.Serializer):
    marital_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    has_children = serializers.BooleanField(required=False, allow_null=True)
    number_of_children = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    height = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    complexion = serializers.ChoiceField(
        choices=['Fair', 'Wheatish', 'Dark', 'Very Fair'],
        required=False,
        allow_null=True,
    )

    def to_internal_value(self, data):
        data = dict(data) if not isinstance(data, dict) else data.copy()
        raw = data.get('has_children')
        if isinstance(raw, str):
            data['has_children'] = raw.strip().lower() in ('true', 'yes', '1')
        return super().to_internal_value(data)

    def validate_marital_status(self, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        from master.models import MaritalStatus
        name = value.strip()
        obj = MaritalStatus.objects.filter(name__iexact=name, is_active=True).first()
        if obj is None:
            valid = list(MaritalStatus.objects.filter(is_active=True).values_list('name', flat=True)[:10])
            raise serializers.ValidationError(
                f'Marital status "{name}" not found. Use one of: {", ".join(valid)}'
            )
        return obj.id

    def validate(self, attrs):
        """
        Cross-field validation for marital_status, has_children and number_of_children.
        """
        # Determine the raw marital status string from input for UI-based rules
        raw_marital = self.initial_data.get('marital_status')
        marital_normalized = (str(raw_marital).strip().lower() if raw_marital is not None else '')
        requires_children_flag = marital_normalized in ('separated', 'widowed', 'divorced')

        has_children = attrs.get('has_children', None)
        number_of_children = attrs.get('number_of_children', None)

        if requires_children_flag and has_children is None:
            # Custom message expected by frontend/API spec
            raise serializers.ValidationError('Please specify whether you have children.')

        if has_children is True and number_of_children is None:
            raise serializers.ValidationError('Please specify the number of children.')

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        marital_status_id = validated_data.get('marital_status')
        height_cm = validated_data.get('height')
        height_text = f'{height_cm} cm' if height_cm is not None else ''
        has_children = validated_data.get('has_children')
        number_of_children = validated_data.get('number_of_children')
        complexion = validated_data.get('complexion')
        defaults = {
            'has_children': has_children if has_children is not None else False,
            'weight': validated_data.get('weight'),
            'colour': complexion or '',
            'height_text': height_text,
        }
        if number_of_children is not None:
            defaults['number_of_children'] = number_of_children
        if marital_status_id is not None:
            defaults['marital_status_id'] = marital_status_id
        obj, _ = UserPersonal.objects.update_or_create(user=user, defaults=defaults)
        return obj


class UserEducationSerializer(serializers.Serializer):
    highest_education = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    education_subject = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    employment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    occupation = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    annual_income = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def _resolve_by_name(self, model_class, value, field_label):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        name = value.strip()
        # Try exact match, then with/without trailing period (e.g. "B.Tech" matches "B.Tech.")
        variants = [name]
        if name.endswith('.'):
            variants.append(name[:-1])
        else:
            variants.append(name + '.')
        obj = None
        for v in variants:
            obj = model_class.objects.filter(name__iexact=v, is_active=True).first()
            if obj is not None:
                break
        if obj is None:
            valid = list(model_class.objects.filter(is_active=True).values_list('name', flat=True)[:15])
            raise serializers.ValidationError(
                {field_label: f'"{name}" not found. Use one of: {", ".join(valid)}'}
            )
        return obj.id

    def validate_highest_education(self, value):
        from master.models import Education
        return self._resolve_by_name(Education, value, 'highest_education')

    def validate_education_subject(self, value):
        from master.models import EducationSubject
        return self._resolve_by_name(EducationSubject, value, 'education_subject')

    def validate_occupation(self, value):
        from master.models import Occupation
        return self._resolve_by_name(Occupation, value, 'occupation')

    def validate_annual_income(self, value):
        from master.models import IncomeRange
        return self._resolve_by_name(IncomeRange, value, 'annual_income')

    def validate(self, attrs):
        highest_education_id = attrs.get('highest_education')
        education_subject_id = attrs.get('education_subject')
        if highest_education_id and education_subject_id:
            from master.models import EducationSubject
            is_mapped = EducationSubject.objects.filter(
                pk=education_subject_id,
                is_active=True,
                educations__id=highest_education_id,
                educations__is_active=True,
            ).exists()
            if not is_mapped:
                raise serializers.ValidationError({
                    'education_subject': 'Selected subject is not available for the chosen highest education.'
                })
        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        defaults = {}
        if validated_data.get('highest_education') is not None:
            defaults['highest_education_id'] = validated_data['highest_education']
        if validated_data.get('education_subject') is not None:
            defaults['education_subject_id'] = validated_data['education_subject']
        if validated_data.get('employment') is not None:
            defaults['employment_status'] = validated_data['employment']
        if validated_data.get('occupation') is not None:
            defaults['occupation_id'] = validated_data['occupation']
        if validated_data.get('annual_income') is not None:
            defaults['annual_income_id'] = validated_data['annual_income']
        obj, _ = UserEducation.objects.update_or_create(user=user, defaults=defaults)
        return obj


class UserProfileAboutSerializer(serializers.Serializer):
    about_me = serializers.CharField(required=True, allow_blank=True)

    def create(self, validated_data):
        user = self.context['request'].user
        obj, _ = UserProfile.objects.get_or_create(user=user, defaults={})
        obj.about_me = validated_data.get('about_me', '')
        obj.save()
        return obj


class UserPhotosSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPhotos
        fields = [
            'profile_photo', 'full_photo', 'selfie_photo', 'family_photo',
            'aadhaar_front', 'aadhaar_back',
        ]

    def _get_user(self):
        return self.context['request'].user

    def create(self, validated_data):
        user = self._get_user()
        obj, _ = UserPhotos.objects.get_or_create(user=user, defaults={})
        for k, v in validated_data.items():
            if v is not None:
                setattr(obj, k, v)
        obj.save()
        return obj

    def update(self, instance, validated_data):
        for k, v in validated_data.items():
            if v is not None:
                setattr(instance, k, v)
        instance.save()
        return instance


# --- GET response (read) serializers for profile section APIs ---

class BasicDetailsReadSerializer(serializers.Serializer):
    """GET /api/v1/profile/basic/ response."""
    name = serializers.CharField()
    gender = serializers.SerializerMethodField()
    dob = serializers.DateField(format='%d-%m-%Y', allow_null=True)
    email = serializers.EmailField(allow_blank=True)
    phone = serializers.CharField(source='mobile', allow_blank=True)
    profile_for = serializers.CharField(allow_blank=True, allow_null=True)

    def get_gender(self, obj):
        g = getattr(obj, 'gender', None)
        if g == 'M':
            return 'Male'
        if g == 'F':
            return 'Female'
        if g == 'O':
            return 'Other'
        return g or ''


class ReligionDetailsReadSerializer(serializers.Serializer):
    religion_id = serializers.IntegerField(allow_null=True)
    religion = serializers.SerializerMethodField()
    caste_id = serializers.IntegerField(source='caste_fk_id', allow_null=True)
    caste = serializers.SerializerMethodField()
    mother_tongue_id = serializers.IntegerField(allow_null=True)
    mother_tongue = serializers.SerializerMethodField()
    partner_religion_preference = serializers.CharField()
    partner_preference_type = serializers.CharField()
    partner_religion_ids = serializers.SerializerMethodField()
    partner_caste_preference = serializers.CharField()

    def get_religion(self, obj):
        return obj.religion.name if obj.religion_id else None

    def get_caste(self, obj):
        return obj.caste_fk.name if obj.caste_fk_id else None

    def get_mother_tongue(self, obj):
        return obj.mother_tongue.name if obj.mother_tongue_id else None

    def get_partner_religion_ids(self, obj):
        ids = obj.partner_religion_ids or []
        if not ids:
            return []
        from master.models import Religion
        religion_map = {
            rel.id: rel.name
            for rel in Religion.objects.filter(pk__in=ids, is_active=True)
        }
        return [{'id': rid, 'name': religion_map.get(rid, '')} for rid in ids]


class PersonalDetailsReadSerializer(serializers.Serializer):
    marital_status_id = serializers.IntegerField(allow_null=True)
    marital_status = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()
    height_cm = serializers.SerializerMethodField()
    weight_kg = serializers.DecimalField(source='weight', max_digits=5, decimal_places=2, allow_null=True)
    colour = serializers.CharField()
    blood_group = serializers.CharField()

    def get_marital_status(self, obj):
        return obj.marital_status.name if obj.marital_status_id else None

    def get_height_cm(self, obj):
        if obj.height_text:
            return obj.height_text
        if getattr(obj, 'height_id', None) and obj.height:
            return obj.height.value_cm
        return None

    def get_children_count(self, obj):
        """
        Safely return children count, supporting both legacy `children_count`
        and new `number_of_children` attribute names.
        """
        if hasattr(obj, 'number_of_children'):
            return obj.number_of_children
        # Fallback for older schema/code where field name was children_count
        return getattr(obj, 'children_count', 0)


class LocationDetailsReadSerializer(serializers.Serializer):
    country_id = serializers.IntegerField(allow_null=True)
    country = serializers.SerializerMethodField()
    state_id = serializers.IntegerField(allow_null=True)
    state = serializers.SerializerMethodField()
    district_id = serializers.IntegerField(allow_null=True)
    district = serializers.SerializerMethodField()
    city_id = serializers.IntegerField(allow_null=True)
    city = serializers.SerializerMethodField()
    address = serializers.CharField()

    def get_country(self, obj):
        return obj.country.name if obj.country_id else None

    def get_state(self, obj):
        return obj.state.name if obj.state_id else None

    def get_district(self, obj):
        return obj.district.name if obj.district_id else None

    def get_city(self, obj):
        return obj.city.name if obj.city_id else None


class FamilyDetailsReadSerializer(serializers.Serializer):
    father_name = serializers.CharField()
    father_occupation = serializers.CharField()
    mother_name = serializers.CharField()
    mother_occupation = serializers.CharField()
    brothers = serializers.IntegerField()
    married_brothers = serializers.IntegerField()
    sisters = serializers.IntegerField()
    married_sisters = serializers.IntegerField()
    about_family = serializers.CharField()


class EducationDetailsReadSerializer(serializers.Serializer):
    highest_education_id = serializers.IntegerField(allow_null=True)
    highest_education = serializers.SerializerMethodField()
    education_subject_id = serializers.IntegerField(allow_null=True)
    education_subject = serializers.SerializerMethodField()
    employment_status = serializers.CharField()
    occupation_id = serializers.IntegerField(allow_null=True)
    occupation = serializers.SerializerMethodField()
    annual_income_id = serializers.IntegerField(allow_null=True)
    annual_income = serializers.SerializerMethodField()

    def get_highest_education(self, obj):
        return obj.highest_education.name if obj.highest_education_id else None

    def get_education_subject(self, obj):
        return obj.education_subject.name if obj.education_subject_id else None

    def get_occupation(self, obj):
        return obj.occupation.name if obj.occupation_id else None

    def get_annual_income(self, obj):
        return obj.annual_income.name if obj.annual_income_id else None


class PhotosDetailsReadSerializer(serializers.Serializer):
    profile_photo = serializers.SerializerMethodField()
    full_photo = serializers.SerializerMethodField()
    selfie_photo = serializers.SerializerMethodField()
    family_photo = serializers.SerializerMethodField()
    aadhaar_front = serializers.SerializerMethodField()
    aadhaar_back = serializers.SerializerMethodField()

    def _url(self, obj, field_name: str):
        request = self.context.get('request')
        return absolute_media_url(request, getattr(obj, field_name, None))

    def get_profile_photo(self, obj):
        return self._url(obj, 'profile_photo')

    def get_full_photo(self, obj):
        return self._url(obj, 'full_photo')

    def get_selfie_photo(self, obj):
        return self._url(obj, 'selfie_photo')

    def get_family_photo(self, obj):
        return self._url(obj, 'family_photo')

    def get_aadhaar_front(self, obj):
        return self._url(obj, 'aadhaar_front')

    def get_aadhaar_back(self, obj):
        return self._url(obj, 'aadhaar_back')


# --- PATCH input serializers (section-specific) ---

PROFILE_FOR_CHOICES = [
    ('myself', 'Myself'),
    ('son', 'Son'),
    ('daughter', 'Daughter'),
    ('brother', 'Brother'),
    ('sister', 'Sister'),
    ('friend', 'Friend'),
    ('relative', 'Relative'),
]


class BasicDetailsUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')], required=False)
    dob = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    profile_for = serializers.ChoiceField(choices=PROFILE_FOR_CHOICES, required=False, allow_blank=True, allow_null=True)

    def validate_dob(self, value):
        from accounts.serializers import parse_optional_dob
        return parse_optional_dob(value)

    def validate_email(self, value):
        normalized = (value or '').strip().lower()
        if not normalized:
            return None
        instance = getattr(self, 'instance', None)
        qs = User.objects.filter(email__iexact=normalized)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Email already exists. Please use a different email.')
        return normalized

    def update(self, instance, validated_data):
        g = validated_data.get('gender')
        if g == 'male':
            instance.gender = 'M'
        elif g == 'female':
            instance.gender = 'F'
        elif g == 'other':
            instance.gender = 'O'
        elif g is not None:
            instance.gender = g
        for k in ('name', 'dob', 'email'):
            if k in validated_data:
                setattr(instance, k, validated_data[k])
        if 'profile_for' in validated_data:
            instance.profile_for = validated_data['profile_for'] or None
        instance.save()
        return instance


class PartnerPreferencesReadSerializer(serializers.Serializer):
    """GET /api/v1/profile/partner-preferences/ response."""
    partner_preference_type = serializers.CharField()
    partner_religion_ids = serializers.ListField(child=serializers.IntegerField())
    partner_caste_preference = serializers.CharField()


class PartnerPreferencesUpdateSerializer(serializers.Serializer):
    """PATCH /api/v1/profile/partner-preferences/ body."""
    partner_preference_type = serializers.ChoiceField(
        choices=[
            'own_religion_only',
            'open_to_all',
            'specific_religions',
        ],
        required=False
    )
    partner_religion_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    partner_caste_preference = serializers.ChoiceField(
        choices=['any', 'own_caste_only'],
        required=False
    )

    def validate(self, attrs):
        pref_type = attrs.get('partner_preference_type')
        religion_ids = attrs.get('partner_religion_ids')
        if pref_type == 'specific_religions' and religion_ids is not None:
            from master.models import Religion
            existing = set(
                Religion.objects.filter(pk__in=religion_ids, is_active=True).values_list('pk', flat=True)
            )
            invalid = [i for i in religion_ids if i not in existing]
            if invalid:
                raise serializers.ValidationError({
                    'partner_religion_ids': f'Invalid or inactive religion id(s): {invalid}.'
                })
        return attrs


class ReligionDetailsUpdateSerializer(serializers.Serializer):
    religion_id = serializers.IntegerField(required=False, allow_null=True)
    caste_id = serializers.IntegerField(required=False, allow_null=True)
    mother_tongue_id = serializers.IntegerField(required=False, allow_null=True)
    partner_religion_preference = serializers.CharField(required=False, allow_blank=True)
    partner_preference_type = serializers.ChoiceField(
        choices=['own_religion_only', 'open_to_all', 'specific_religions'],
        required=False
    )
    partner_religion_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    partner_caste_preference = serializers.ChoiceField(choices=['any', 'own_caste_only'], required=False)

    def validate(self, attrs):
        pref_type = attrs.get('partner_preference_type')
        religion_ids = attrs.get('partner_religion_ids')
        if pref_type == 'specific_religions' and religion_ids is not None:
            from master.models import Religion
            existing = set(
                Religion.objects.filter(pk__in=religion_ids, is_active=True).values_list('pk', flat=True)
            )
            invalid = [i for i in religion_ids if i not in existing]
            if invalid:
                raise serializers.ValidationError({
                    'partner_religion_ids': f'Invalid or inactive religion id(s): {invalid}.'
                })
        return attrs

    def validate_religion_id(self, v):
        if v is None:
            return v
        from master.models import Religion
        if not Religion.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid religion_id.')
        return v

    def validate_caste_id(self, v):
        if v is None:
            return v
        from master.models import Caste
        if not Caste.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid caste_id.')
        return v

    def validate_mother_tongue_id(self, v):
        if v is None:
            return v
        from master.models import MotherTongue
        if not MotherTongue.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid mother_tongue_id.')
        return v


class PersonalDetailsUpdateSerializer(serializers.Serializer):
    marital_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    has_children = serializers.BooleanField(required=False, allow_null=True)
    children_count = serializers.IntegerField(source='number_of_children', required=False, min_value=0)
    number_of_children = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    height_cm = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    complexion = serializers.ChoiceField(
        choices=['Fair', 'Wheatish', 'Dark', 'Very Fair'],
        required=False,
        allow_null=True,
    )
    colour = serializers.CharField(required=False, allow_blank=True)
    blood_group = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        data = dict(data) if not isinstance(data, dict) else data.copy()
        raw = data.get('has_children')
        if isinstance(raw, str):
            raw_normalized = raw.strip().lower()
            if raw_normalized in ('true', 'yes', '1'):
                data['has_children'] = True
            elif raw_normalized in ('false', 'no', '0'):
                data['has_children'] = False
        return super().to_internal_value(data)

    def validate_marital_status(self, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        from master.models import MaritalStatus
        name = value.strip()
        obj = MaritalStatus.objects.filter(name__iexact=name, is_active=True).first()
        if obj is None:
            valid = list(MaritalStatus.objects.filter(is_active=True).values_list('name', flat=True)[:10])
            raise serializers.ValidationError(
                f'Marital status "{name}" not found. Use one of: {", ".join(valid)}'
            )
        return obj.id

    def validate(self, attrs):
        """
        Keep PATCH compatibility with POST payload rules.
        """
        marital_status_name = self.initial_data.get('marital_status')

        has_children = attrs.get('has_children', None)
        number_of_children = attrs.get('number_of_children', None)

        # If legacy children_count alias is used, it populates number_of_children via source.
        if number_of_children is None and 'children_count' in attrs:
            number_of_children = attrs.get('children_count')

        requires_children_flag = False
        if isinstance(marital_status_name, str):
            requires_children_flag = marital_status_name.strip().lower() in ('separated', 'widowed', 'divorced')

        if requires_children_flag and has_children is None:
            raise serializers.ValidationError('Please specify whether you have children.')
        if has_children is True and number_of_children is None:
            raise serializers.ValidationError('Please specify the number of children.')
        if has_children is False:
            # Keep DB value non-null and semantically consistent.
            attrs['number_of_children'] = 0

        return attrs


class LocationDetailsUpdateSerializer(serializers.Serializer):
    country_id = serializers.IntegerField(required=False, allow_null=True)
    state_id = serializers.IntegerField(required=False, allow_null=True)
    district_id = serializers.IntegerField(required=False, allow_null=True)
    city_id = serializers.IntegerField(required=False, allow_null=True)
    address = serializers.CharField(required=False, allow_blank=True)

    def validate_country_id(self, v):
        if v is None:
            return v
        from master.models import Country
        if not Country.objects.filter(pk=v).exists():
            raise serializers.ValidationError('Invalid country_id.')
        return v

    def validate_state_id(self, v):
        if v is None:
            return v
        from master.models import State
        if not State.objects.filter(pk=v).exists():
            raise serializers.ValidationError('Invalid state_id.')
        return v

    def validate_district_id(self, v):
        if v is None:
            return v
        from master.models import District
        if not District.objects.filter(pk=v).exists():
            raise serializers.ValidationError('Invalid district_id.')
        return v

    def validate_city_id(self, v):
        if v is None:
            return v
        from master.models import City
        if not City.objects.filter(pk=v).exists():
            raise serializers.ValidationError('Invalid city_id.')
        return v


class FamilyDetailsUpdateSerializer(serializers.Serializer):
    father_name = serializers.CharField(required=False, allow_blank=True)
    father_occupation = serializers.CharField(required=False, allow_blank=True)
    mother_name = serializers.CharField(required=False, allow_blank=True)
    mother_occupation = serializers.CharField(required=False, allow_blank=True)
    brothers = serializers.IntegerField(required=False, min_value=0)
    married_brothers = serializers.IntegerField(required=False, min_value=0)
    sisters = serializers.IntegerField(required=False, min_value=0)
    married_sisters = serializers.IntegerField(required=False, min_value=0)
    about_family = serializers.CharField(required=False, allow_blank=True)


class EducationDetailsUpdateSerializer(serializers.Serializer):
    highest_education_id = serializers.IntegerField(required=False, allow_null=True)
    education_subject_id = serializers.IntegerField(required=False, allow_null=True)
    employment_status = serializers.CharField(required=False, allow_blank=True)
    occupation_id = serializers.IntegerField(required=False, allow_null=True)
    annual_income_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_highest_education_id(self, v):
        if v is None:
            return v
        from master.models import Education
        if not Education.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid highest_education_id.')
        return v

    def validate_education_subject_id(self, v):
        if v is None:
            return v
        from master.models import EducationSubject
        if not EducationSubject.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid education_subject_id.')
        return v

    def validate_occupation_id(self, v):
        if v is None:
            return v
        from master.models import Occupation
        if not Occupation.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid occupation_id.')
        return v

    def validate_annual_income_id(self, v):
        if v is None:
            return v
        from master.models import IncomeRange
        if not IncomeRange.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid annual_income_id.')
        return v

    def validate(self, attrs):
        subject_id = attrs.get('education_subject_id')
        if subject_id is None:
            return attrs

        education_id = attrs.get('highest_education_id')
        if education_id is None:
            request = self.context.get('request')
            if request and request.user and request.user.is_authenticated:
                existing = UserEducation.objects.filter(user=request.user).first()
                if existing:
                    education_id = existing.highest_education_id

        if education_id is None:
            # Partial payload without education context cannot enforce mapping yet.
            return attrs

        from master.models import EducationSubject
        is_mapped = EducationSubject.objects.filter(
            pk=subject_id,
            is_active=True,
            educations__id=education_id,
            educations__is_active=True,
        ).exists()
        if not is_mapped:
            raise serializers.ValidationError({
                'education_subject_id': 'Selected subject is not available for the chosen highest education.'
            })
        return attrs


class AboutDetailsUpdateSerializer(serializers.Serializer):
    about_me = serializers.CharField(required=False, allow_blank=True)

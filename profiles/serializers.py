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
from .parent_status import normalize_parent_status


def _normalize_partner_caste_preferences(raw_value):
    if raw_value in (None, ''):
        return {}
    if not isinstance(raw_value, dict):
        raise serializers.ValidationError(
            {'partner_caste_preferences': 'Expected an object like {"<religion_id>": [<caste_id>, ...]}.'}
        )
    normalized = {}
    for key, value in raw_value.items():
        try:
            religion_id = int(str(key).strip())
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                {'partner_caste_preferences': f'Invalid religion key: {key}.'}
            )
        if not isinstance(value, list):
            raise serializers.ValidationError(
                {'partner_caste_preferences': f'Religion {religion_id} must map to a list of caste ids.'}
            )
        caste_ids = []
        for caste_id in value:
            try:
                caste_ids.append(int(caste_id))
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    {'partner_caste_preferences': f'Invalid caste id "{caste_id}" for religion {religion_id}.'}
                )
        normalized[religion_id] = caste_ids
    return normalized


def _validate_partner_mode_rules(*, attrs, existing_obj=None, user=None):
    from .models import UserReligion
    from master.models import Caste, Religion

    pref_type = attrs.get('partner_preference_type')
    if pref_type is None and existing_obj is not None:
        pref_type = existing_obj.partner_preference_type or UserReligion.PARTNER_PREFERENCE_ALL
    pref_type = pref_type or UserReligion.PARTNER_PREFERENCE_ALL

    religion_ids = attrs.get('partner_religion_ids')
    if religion_ids is None:
        religion_ids = list(existing_obj.partner_religion_ids or []) if existing_obj is not None else []
    religion_ids = [int(x) for x in religion_ids]

    caste_map = attrs.get('partner_caste_preferences')
    if caste_map is None:
        raw_existing = getattr(existing_obj, 'partner_caste_preferences', {}) if existing_obj is not None else {}
        caste_map = _normalize_partner_caste_preferences(raw_existing)
    else:
        caste_map = _normalize_partner_caste_preferences(caste_map)

    if pref_type == UserReligion.PARTNER_PREFERENCE_ALL:
        attrs['partner_religion_ids'] = []
        attrs['partner_caste_preferences'] = {}
        return attrs

    if pref_type == UserReligion.PARTNER_PREFERENCE_OWN:
        own_religion_id = None
        if attrs.get('religion_id') is not None:
            own_religion_id = int(attrs['religion_id'])
        elif existing_obj is not None and existing_obj.religion_id:
            own_religion_id = int(existing_obj.religion_id)
        elif user is not None:
            user_rel = UserReligion.objects.filter(user=user).only('religion_id').first()
            own_religion_id = int(user_rel.religion_id) if user_rel and user_rel.religion_id else None
        if not own_religion_id:
            raise serializers.ValidationError(
                {'partner_caste_preferences': 'Set your religion first before choosing own-religion caste preferences.'}
            )

        allowed_keys = {own_religion_id}
        invalid_keys = [rid for rid in caste_map.keys() if rid not in allowed_keys]
        if invalid_keys:
            raise serializers.ValidationError(
                {'partner_caste_preferences': f'Only your own religion id {own_religion_id} is allowed. Invalid keys: {invalid_keys}.'}
            )
        attrs['partner_religion_ids'] = []
        attrs['partner_caste_preferences'] = caste_map
        target_religion_ids = list(allowed_keys)
    elif pref_type == UserReligion.PARTNER_PREFERENCE_SPECIFIC:
        if not religion_ids:
            raise serializers.ValidationError(
                {'partner_religion_ids': 'This field is required and cannot be empty for specific_religions.'}
            )
        existing_religions = set(
            Religion.objects.filter(pk__in=religion_ids, is_active=True).values_list('pk', flat=True)
        )
        invalid = [rid for rid in religion_ids if rid not in existing_religions]
        if invalid:
            raise serializers.ValidationError(
                {'partner_religion_ids': f'Invalid or inactive religion id(s): {invalid}.'}
            )
        invalid_keys = [rid for rid in caste_map.keys() if rid not in set(religion_ids)]
        if invalid_keys:
            raise serializers.ValidationError(
                {'partner_caste_preferences': f'Caste map contains religion ids not selected in partner_religion_ids: {invalid_keys}.'}
            )
        attrs['partner_religion_ids'] = religion_ids
        attrs['partner_caste_preferences'] = caste_map
        target_religion_ids = religion_ids
    else:
        raise serializers.ValidationError({'partner_preference_type': 'Invalid partner_preference_type.'})

    allowed_caste_rows = Caste.objects.filter(
        religion_id__in=target_religion_ids,
        pk__in=[cid for ids in caste_map.values() for cid in ids],
        is_active=True,
    ).values_list('id', 'religion_id')
    caste_to_religion = {int(cid): int(rid) for cid, rid in allowed_caste_rows}
    for rid, caste_ids in caste_map.items():
        invalid_for_religion = [cid for cid in caste_ids if caste_to_religion.get(cid) != rid]
        if invalid_for_religion:
            raise serializers.ValidationError(
                {'partner_caste_preferences': f'Invalid caste id(s) for religion {rid}: {invalid_for_religion}.'}
            )
    return attrs


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
    partner_caste_preferences = serializers.DictField(required=False)

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
        return _validate_partner_mode_rules(
            attrs=attrs,
            existing_obj=None,
            user=self.context['request'].user,
        )

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
        if 'partner_caste_preferences' in validated_data:
            defaults['partner_caste_preferences'] = validated_data['partner_caste_preferences']
        obj, _ = UserReligion.objects.update_or_create(user=user, defaults=defaults)
        return obj


class UserPersonalSerializer(serializers.Serializer):
    marital_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    has_children = serializers.BooleanField(required=False, allow_null=True)
    number_of_children = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    height = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    complexion = serializers.ChoiceField(
        choices=['Very Fair','Fair','Wheatish','Wheatish Brown','Dark','Other'],
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
        """Member user: default request.user; admin panel passes target_user in context."""
        ctx = self.context
        u = ctx.get('target_user')
        if u is not None:
            return u
        return ctx['request'].user

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
        """API-facing gender labels (Male / Female / Other)."""
        g = getattr(obj, 'gender', None)
        mapping = {'M': 'Male', 'F': 'Female', 'O': 'Other'}
        return mapping.get(g, '')


class ReligionDetailsReadSerializer(serializers.Serializer):
    religion_id = serializers.IntegerField(allow_null=True)
    religion = serializers.SerializerMethodField()
    caste_id = serializers.IntegerField(source='caste_fk_id', allow_null=True)
    caste = serializers.SerializerMethodField()
    mother_tongue_id = serializers.IntegerField(allow_null=True)
    mother_tongue = serializers.SerializerMethodField()
    partner_religion_preference = serializers.CharField(allow_blank=True)
    partner_preference_type = serializers.CharField(allow_blank=True)
    partner_preference_type_label = serializers.SerializerMethodField()
    partner_religion_ids = serializers.SerializerMethodField()
    partner_religion_names = serializers.SerializerMethodField()
    partner_caste_preferences = serializers.SerializerMethodField()

    def get_religion(self, obj):
        return obj.religion.name if obj.religion_id else None

    def get_caste(self, obj):
        return obj.caste_fk.name if obj.caste_fk_id else None

    def get_mother_tongue(self, obj):
        return obj.mother_tongue.name if obj.mother_tongue_id else None

    def get_partner_preference_type_label(self, obj):
        if hasattr(obj, 'get_partner_preference_type_display'):
            return obj.get_partner_preference_type_display()
        from .models import UserReligion
        return dict(UserReligion.PARTNER_PREFERENCE_TYPE_CHOICES).get(
            (obj.partner_preference_type or '').strip(), ''
        )

    def get_partner_caste_preferences(self, obj):
        raw = getattr(obj, 'partner_caste_preferences', None) or {}
        normalized = _normalize_partner_caste_preferences(raw)
        return {str(rid): caste_ids for rid, caste_ids in normalized.items()}

    def get_partner_religion_ids(self, obj):
        ids = obj.partner_religion_ids or []
        return [int(x) for x in ids]

    def get_partner_religion_names(self, obj):
        ids = obj.partner_religion_ids or []
        if not ids:
            return []
        from master.models import Religion
        religion_map = {
            rel.id: rel.name
            for rel in Religion.objects.filter(pk__in=ids, is_active=True)
        }
        return [religion_map.get(int(rid), '') for rid in ids]


class PersonalDetailsReadSerializer(serializers.Serializer):
    marital_status_id = serializers.IntegerField(allow_null=True)
    marital_status = serializers.SerializerMethodField()
    has_children = serializers.BooleanField()
    children_count = serializers.SerializerMethodField()
    height_cm = serializers.SerializerMethodField()
    weight_kg = serializers.DecimalField(source='weight', max_digits=5, decimal_places=2, allow_null=True)
    colour = serializers.CharField()
    blood_group = serializers.CharField()

    def get_marital_status(self, obj):
        return obj.marital_status.name if obj.marital_status_id else None

    def get_height_cm(self, obj):
        """Integer cm for dropdowns when known; null otherwise."""
        if getattr(obj, 'height_id', None) and obj.height:
            try:
                return int(obj.height.value_cm)
            except (TypeError, ValueError):
                pass
        txt = (obj.height_text or '').strip()
        if txt:
            import re

            m = re.match(r'^(\d+)', txt)
            if m:
                return int(m.group(1))
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
    father_status = serializers.CharField(allow_blank=True)
    father_occupation = serializers.CharField()
    mother_name = serializers.CharField()
    mother_status = serializers.CharField(allow_blank=True)
    mother_occupation = serializers.CharField()
    brothers = serializers.IntegerField()
    married_brothers = serializers.IntegerField()
    sisters = serializers.IntegerField()
    married_sisters = serializers.IntegerField()
    about_family = serializers.CharField()
    family_type = serializers.CharField(allow_blank=True)
    family_status = serializers.CharField(allow_blank=True)


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


def empty_religion_details_read_data():
    """Stable GET shape when UserReligion row is missing."""
    from .models import UserReligion

    return {
        'religion_id': None,
        'religion': None,
        'caste_id': None,
        'caste': None,
        'mother_tongue_id': None,
        'mother_tongue': None,
        'partner_religion_preference': '',
        'partner_preference_type': UserReligion.PARTNER_PREFERENCE_ALL,
        'partner_preference_type_label': dict(UserReligion.PARTNER_PREFERENCE_TYPE_CHOICES).get(
            UserReligion.PARTNER_PREFERENCE_ALL, ''
        ),
        'partner_religion_ids': [],
        'partner_religion_names': [],
        'partner_caste_preferences': {},
    }


def empty_personal_details_read_data():
    return {
        'marital_status_id': None,
        'marital_status': None,
        'has_children': False,
        'children_count': 0,
        'height_cm': None,
        'weight_kg': None,
        'colour': '',
        'blood_group': '',
    }


def empty_location_details_read_data():
    return {
        'country_id': None,
        'country': None,
        'state_id': None,
        'state': None,
        'district_id': None,
        'district': None,
        'city_id': None,
        'city': None,
        'address': '',
    }


def empty_education_details_read_data():
    return {
        'highest_education_id': None,
        'highest_education': None,
        'education_subject_id': None,
        'education_subject': None,
        'employment_status': '',
        'occupation_id': None,
        'occupation': None,
        'annual_income_id': None,
        'annual_income': None,
    }


def empty_family_details_read_data():
    return {
        'father_name': '',
        'father_status': '',
        'father_occupation': '',
        'mother_name': '',
        'mother_status': '',
        'mother_occupation': '',
        'brothers': 0,
        'married_brothers': 0,
        'sisters': 0,
        'married_sisters': 0,
        'about_family': '',
        'family_type': '',
        'family_status': '',
    }


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
    gender = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    dob = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    profile_for = serializers.ChoiceField(choices=PROFILE_FOR_CHOICES, required=False, allow_blank=True, allow_null=True)

    def validate_gender(self, value):
        if value is None or (isinstance(value, str) and not str(value).strip()):
            return None
        v = str(value).strip()
        u = v.upper()
        if u in ('M', 'F', 'O'):
            return u
        low = v.lower()
        if low in ('male', 'man', 'm'):
            return 'M'
        if low in ('female', 'woman', 'f'):
            return 'F'
        if low in ('other', 'o'):
            return 'O'
        raise serializers.ValidationError('gender must be M, F, or O (or Male/Female/Other).')

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
        if 'gender' in validated_data and validated_data['gender'] is not None:
            instance.gender = validated_data['gender']
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
    partner_caste_preferences = serializers.SerializerMethodField()

    def get_partner_caste_preferences(self, obj):
        raw = getattr(obj, 'partner_caste_preferences', None) or {}
        normalized = _normalize_partner_caste_preferences(raw)
        return {str(rid): caste_ids for rid, caste_ids in normalized.items()}


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
    partner_caste_preferences = serializers.DictField(required=False)

    def validate(self, attrs):
        existing_obj = self.context.get('existing_obj')
        user = self.context.get('user')
        if user is None:
            request = self.context.get('request')
            user = getattr(request, 'user', None) if request else None
        return _validate_partner_mode_rules(attrs=attrs, existing_obj=existing_obj, user=user)


class ReligionDetailsUpdateSerializer(serializers.Serializer):
    religion_id = serializers.IntegerField(required=False, allow_null=True)
    religion = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    caste_id = serializers.IntegerField(required=False, allow_null=True)
    caste = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    mother_tongue_id = serializers.IntegerField(required=False, allow_null=True)
    mother_tongue = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    partner_religion_preference = serializers.CharField(required=False, allow_blank=True)
    partner_preference_type = serializers.ChoiceField(
        choices=['own_religion_only', 'open_to_all', 'specific_religions'],
        required=False
    )
    partner_religion_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    partner_caste_preferences = serializers.DictField(required=False)

    def validate(self, attrs):
        from master.models import Caste, MotherTongue, Religion

        attrs = dict(attrs)
        rid = attrs.get('religion_id')
        rname = attrs.pop('religion', None)
        if rid is None and isinstance(rname, str) and rname.strip():
            r = Religion.objects.filter(name__iexact=rname.strip(), is_active=True).first()
            if not r:
                raise serializers.ValidationError(
                    {'religion': f'Unknown religion name: {rname}. Use master list name or religion_id.'}
                )
            attrs['religion_id'] = r.id
            rid = r.id

        cid = attrs.get('caste_id')
        cname = attrs.pop('caste', None)
        if cid is None and isinstance(cname, str) and cname.strip():
            if not rid:
                raise serializers.ValidationError(
                    {'caste': 'caste name requires religion_id or religion name in the same payload.'}
                )
            c = Caste.objects.filter(
                religion_id=rid, name__iexact=cname.strip(), is_active=True
            ).first()
            if not c:
                raise serializers.ValidationError(
                    {'caste': f'Unknown caste for this religion: {cname}. Use master list name or caste_id.'}
                )
            attrs['caste_id'] = c.id

        mtid = attrs.get('mother_tongue_id')
        mtname = attrs.pop('mother_tongue', None)
        if mtid is None and isinstance(mtname, str) and mtname.strip():
            mt = MotherTongue.objects.filter(name__iexact=mtname.strip(), is_active=True).first()
            if not mt:
                raise serializers.ValidationError(
                    {'mother_tongue': f'Unknown mother tongue: {mtname}. Use master name or mother_tongue_id.'}
                )
            attrs['mother_tongue_id'] = mt.id

        request = self.context.get('request')
        user = getattr(request, 'user', None) if request else None
        existing_obj = UserReligion.objects.filter(user=user).first() if user is not None else None
        attrs = _validate_partner_mode_rules(attrs=attrs, existing_obj=existing_obj, user=user)
        final_rid = attrs.get('religion_id')
        final_cid = attrs.get('caste_id')
        if final_cid is not None and final_rid is not None:
            if not Caste.objects.filter(pk=final_cid, religion_id=final_rid, is_active=True).exists():
                raise serializers.ValidationError(
                    {'caste_id': 'caste_id does not belong to religion_id or is inactive.'}
                )
        attrs.pop('religion', None)
        attrs.pop('caste', None)
        attrs.pop('mother_tongue', None)
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
    marital_status_id = serializers.IntegerField(required=False, allow_null=True)
    has_children = serializers.BooleanField(required=False, allow_null=True)
    children_count = serializers.IntegerField(source='number_of_children', required=False, min_value=0)
    number_of_children = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    height_cm = serializers.IntegerField(required=False, allow_null=True)
    height = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight_kg = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    weight = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    complexion = serializers.ChoiceField(
        choices=['Very Fair','Fair','Wheatish','Wheatish Brown','Dark','Other'],
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

    def validate_marital_status_id(self, value):
        if value is None:
            return None
        from master.models import MaritalStatus
        if not MaritalStatus.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError('Invalid marital_status_id.')
        return value

    def validate(self, attrs):
        """
        Keep PATCH compatibility with POST payload rules.
        """
        attrs = dict(attrs)
        mid = attrs.pop('marital_status_id', None)
        if mid is not None:
            if attrs.get('marital_status') is not None:
                raise serializers.ValidationError(
                    'Send either marital_status (name) or marital_status_id, not both.'
                )
            attrs['marital_status'] = mid

        marital_status_name = self.initial_data.get('marital_status')
        ms_resolved = attrs.get('marital_status')
        if marital_status_name is None and isinstance(ms_resolved, int):
            from master.models import MaritalStatus
            mso = MaritalStatus.objects.filter(pk=ms_resolved).first()
            marital_status_name = mso.name if mso else ''

        has_children = attrs.get('has_children', None)
        number_of_children = attrs.get('number_of_children', None)

        # If legacy children_count alias is used, it populates number_of_children via source.
        if number_of_children is None and 'children_count' in attrs:
            number_of_children = attrs.get('children_count')

        requires_children_flag = False
        if isinstance(marital_status_name, str) and marital_status_name.strip():
            requires_children_flag = marital_status_name.strip().lower() in (
                'separated',
                'widowed',
                'divorced',
            )

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
        if not Country.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid or inactive country_id.')
        return v

    def validate_state_id(self, v):
        if v is None:
            return v
        from master.models import State
        if not State.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid or inactive state_id.')
        return v

    def validate_district_id(self, v):
        if v is None:
            return v
        from master.models import District
        if not District.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid or inactive district_id.')
        return v

    def validate_city_id(self, v):
        if v is None:
            return v
        from master.models import City
        if not City.objects.filter(pk=v, is_active=True).exists():
            raise serializers.ValidationError('Invalid or inactive city_id.')
        return v

    def validate(self, attrs):
        """When multiple location IDs are sent together, enforce master hierarchy."""
        from master.models import City, District, State

        attrs = dict(attrs)
        cid = attrs.get('country_id')
        sid = attrs.get('state_id')
        did = attrs.get('district_id')
        ciid = attrs.get('city_id')
        if sid is not None and cid is not None:
            if not State.objects.filter(pk=sid, country_id=cid, is_active=True).exists():
                raise serializers.ValidationError(
                    {'state_id': 'state_id does not belong to country_id or is inactive.'}
                )
        if did is not None and sid is not None:
            if not District.objects.filter(pk=did, state_id=sid, is_active=True).exists():
                raise serializers.ValidationError(
                    {'district_id': 'district_id does not belong to state_id or is inactive.'}
                )
        if ciid is not None and did is not None:
            if not City.objects.filter(pk=ciid, district_id=did, is_active=True).exists():
                raise serializers.ValidationError(
                    {'city_id': 'city_id does not belong to district_id or is inactive.'}
                )
        return attrs


class FamilyDetailsUpdateSerializer(serializers.Serializer):
    father_name = serializers.CharField(required=False, allow_blank=True)
    father_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    father_occupation = serializers.CharField(required=False, allow_blank=True)
    mother_name = serializers.CharField(required=False, allow_blank=True)
    mother_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    mother_occupation = serializers.CharField(required=False, allow_blank=True)
    brothers = serializers.IntegerField(required=False, min_value=0)
    married_brothers = serializers.IntegerField(required=False, min_value=0)
    sisters = serializers.IntegerField(required=False, min_value=0)
    married_sisters = serializers.IntegerField(required=False, min_value=0)
    about_family = serializers.CharField(required=False, allow_blank=True)
    family_type = serializers.CharField(required=False, allow_blank=True)
    family_status = serializers.CharField(required=False, allow_blank=True)

    def validate_father_status(self, value):
        n = normalize_parent_status(value)
        if n is None and (value is not None and str(value).strip()):
            raise serializers.ValidationError('Must be Alive or Late.')
        return n or ''

    def validate_mother_status(self, value):
        n = normalize_parent_status(value)
        if n is None and (value is not None and str(value).strip()):
            raise serializers.ValidationError('Must be Alive or Late.')
        return n or ''


class EducationDetailsUpdateSerializer(serializers.Serializer):
    highest_education_id = serializers.IntegerField(required=False, allow_null=True)
    education_subject_id = serializers.IntegerField(required=False, allow_null=True)
    employment_status = serializers.CharField(required=False, allow_blank=True)
    occupation_id = serializers.IntegerField(required=False, allow_null=True)
    annual_income_id = serializers.IntegerField(required=False, allow_null=True)
    employment = serializers.CharField(required=False, allow_blank=True, write_only=True)
    # Backward/forward compatible: allow clients to send master "name" strings
    # instead of IDs (UI often deals with labels).
    highest_education = serializers.CharField(required=False, allow_blank=True, write_only=True)
    education_subject = serializers.CharField(required=False, allow_blank=True, write_only=True)
    occupation = serializers.CharField(required=False, allow_blank=True, write_only=True)
    annual_income = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def _resolve_active_name_to_id(self, model, label: str, *, field_name: str) -> int:
        cleaned = (label or '').strip()
        if not cleaned:
            raise serializers.ValidationError({field_name: 'This field may not be blank.'})

        qs = model.objects.filter(name__iexact=cleaned, is_active=True)
        count = qs.count()
        if count == 1:
            return int(qs.values_list('id', flat=True).first())
        if count == 0:
            raise serializers.ValidationError({field_name: f'Invalid {field_name}.'})
        raise serializers.ValidationError({field_name: f'Ambiguous {field_name}; multiple matches found.'})

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
        # Allow either *_id or string label. If both are provided, *_id wins.
        from master.models import Education, EducationSubject, Occupation, IncomeRange

        # Accept `employment` alias for `employment_status`
        if 'employment_status' not in attrs and 'employment' in attrs:
            attrs['employment_status'] = attrs.pop('employment')

        if attrs.get('highest_education_id') is None and 'highest_education' in attrs:
            v = attrs.pop('highest_education')
            if v.strip() == '':
                attrs['highest_education_id'] = None
            else:
                attrs['highest_education_id'] = self._resolve_active_name_to_id(
                    Education, v, field_name='highest_education'
                )

        if attrs.get('education_subject_id') is None and 'education_subject' in attrs:
            v = attrs.pop('education_subject')
            if v.strip() == '':
                attrs['education_subject_id'] = None
            else:
                attrs['education_subject_id'] = self._resolve_active_name_to_id(
                    EducationSubject, v, field_name='education_subject'
                )

        if attrs.get('occupation_id') is None and 'occupation' in attrs:
            v = attrs.pop('occupation')
            if v.strip() == '':
                attrs['occupation_id'] = None
            else:
                attrs['occupation_id'] = self._resolve_active_name_to_id(
                    Occupation, v, field_name='occupation'
                )

        if attrs.get('annual_income_id') is None and 'annual_income' in attrs:
            v = attrs.pop('annual_income')
            if v.strip() == '':
                attrs['annual_income_id'] = None
            else:
                attrs['annual_income_id'] = self._resolve_active_name_to_id(
                    IncomeRange, v, field_name='annual_income'
                )

        subject_id = attrs.get('education_subject_id')
        if subject_id is None:
            return attrs

        education_id = attrs.get('highest_education_id')
        if education_id is None:
            user = self.context.get('user')
            if user is None:
                request = self.context.get('request')
                user = getattr(request, 'user', None) if request else None
            if user is not None and getattr(user, 'is_authenticated', False):
                existing = UserEducation.objects.filter(user=user).first()
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


class BirthDetailsUpdateSerializer(serializers.Serializer):
    time_of_birth = serializers.TimeField(required=True)
    place_of_birth = serializers.CharField(required=True, allow_blank=False, max_length=255)

    def validate_place_of_birth(self, value):
        cleaned = (value or '').strip()
        if not cleaned:
            raise serializers.ValidationError('place_of_birth cannot be empty.')
        return cleaned

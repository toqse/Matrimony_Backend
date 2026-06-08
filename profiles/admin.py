from django.contrib import admin
from django import forms
from .models import UserProfile, UserLocation, UserReligion, UserPersonal, UserFamily, UserEducation, UserPhotos


class UserPersonalAdminForm(forms.ModelForm):
    colour = forms.ChoiceField(choices=(), required=False)

    class Meta:
        model = UserPersonal
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from master.models import Complexion

        choices = [("", "---------")]
        choices.extend(
            (name, name) for name in Complexion.objects.filter(is_active=True).values_list('name', flat=True)
        )
        current = (self.instance.colour or '').strip() if getattr(self, 'instance', None) else ''
        if current and current not in {value for value, _ in choices}:
            choices.append((current, f"{current} (inactive)"))
        self.fields['colour'].choices = choices


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'about_me_short']
    search_fields = ['user__matri_id', 'user__email', 'user__mobile']

    def about_me_short(self, obj):
        return (obj.about_me or '')[:50] + '...' if (obj.about_me or '') and len(obj.about_me or '') > 50 else (obj.about_me or '')


@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ['user', 'country', 'state', 'city']


@admin.register(UserReligion)
class UserReligionAdmin(admin.ModelAdmin):
    list_display = [
        'user',
        'religion',
        'caste',
        'mother_tongue',
        'partner_preference_type',
        'partner_caste_preferences',
    ]


@admin.register(UserPersonal)
class UserPersonalAdmin(admin.ModelAdmin):
    form = UserPersonalAdminForm
    list_display = ['user', 'marital_status', 'height_text', 'has_children', 'blood_group', 'number_of_children']


@admin.register(UserFamily)
class UserFamilyAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'father_name', 'father_status', 'mother_name', 'mother_status', 'brothers', 'sisters',
    ]


@admin.register(UserEducation)
class UserEducationAdmin(admin.ModelAdmin):
    list_display = ['user', 'highest_education', 'occupation', 'annual_income']


@admin.register(UserPhotos)
class UserPhotosAdmin(admin.ModelAdmin):
    list_display = ['user', 'profile_photo', 'full_photo']

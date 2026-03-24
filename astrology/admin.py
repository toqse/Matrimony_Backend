from django.contrib import admin

from .models import Horoscope


@admin.register(Horoscope)
class HoroscopeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'profile', 'rasi', 'nakshatra', 'nakshatra_pada',
        'gana', 'yoni', 'nadi', 'rajju', 'updated_at',
    )
    search_fields = ('profile__id', 'profile__user__matri_id', 'nakshatra', 'rasi')
    readonly_fields = ('created_at', 'updated_at')

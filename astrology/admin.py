from django.contrib import admin

from .models import HoroscopeProfile, PoruthamResult


@admin.register(HoroscopeProfile)
class HoroscopeProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'pr_star',
        'rasi_sign',
        'star_name',
        'is_calculated',
        'updated_at',
    )
    search_fields = ('user__matri_id', 'user__name', 'star_name')
    raw_id_fields = ('user',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(PoruthamResult)
class PoruthamResultAdmin(admin.ModelAdmin):
    list_display = ('bride', 'groom', 'overall_result', 'calculated_at')
    raw_id_fields = ('bride', 'groom')
    readonly_fields = ('created_at', 'calculated_at')

"""
URL configuration for matrimony_backend.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from profiles.views import (
    PublicProfileByMatriIdView,
    ProfilePreviewByMatriIdView,
    ProfileRegistrationCompletedView,
)
from plans.views import MyPlanView, ContactUnlockView, WebsitePlanListView

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/v1/auth/', include('accounts.urls')),
    path('api/v1/admin/auth/', include('admin_panel.auth.urls')),
    path('api/v1/admin/dashboard/', include('admin_panel.dashboard.urls')),

    # ✅ FIXED HERE
    path('api/v1/admin/branches/', include('admin_panel.branches.urls')),
    path('api/v1/admin/staff/', include('admin_panel.staff_mgmt.urls')),
    path('api/v1/branch/staff/', include('admin_panel.staff_mgmt.branch_urls')),
    path('api/v1/branch/dashboard/', include('admin_panel.branch_dashboard.urls')),
    path('api/v1/branch/staff-performance/', include('admin_panel.staff_performance.urls')),
    path('api/v1/branch/commissions/', include('admin_panel.commissions.branch_urls')),
    path('api/v1/branch/my-commissions/', include('admin_panel.my_commissions.urls')),
    path('api/v1/branch/my-salary/', include('admin_panel.my_salary.urls')),
    path('api/v1/branch/my-profiles/', include('admin_panel.my_profiles.urls')),
    path('api/v1/admin/subscriptions/', include('admin_panel.subscriptions.urls')),
    path('api/v1/branch/subscriptions/', include('admin_panel.subscriptions.branch_urls')),
    path('api/v1/staff/subscriptions/', include('admin_panel.staff_subscriptions.urls')),
    path('api/v1/admin/commissions/', include('admin_panel.commissions.urls')),
    path('api/v1/staff/commissions/', include('admin_panel.staff_commissions.urls')),
    path('api/v1/admin/payroll/', include('admin_panel.payroll.urls')),
    path('api/v1/branch/payroll/', include('admin_panel.payroll.branch_urls')),
    path('api/v1/staff/payroll/', include('admin_panel.payroll.staff_urls')),
    path('api/v1/staff/salary/', include('admin_panel.staff_salary.urls')),
    path('api/v1/staff/payments/', include('admin_panel.staff_payments.urls')),
    path('api/v1/branch/payments/', include('admin_panel.staff_payments.branch_urls')),
    path('api/v1/admin/profiles/', include('admin_panel.profile_admin.urls')),
    path('api/v1/staff/profiles/', include('admin_panel.staff_profiles.urls')),
    path('api/v1/staff/dashboard/', include('admin_panel.staff_dashboard.urls')),
    path('api/v1/admin/bulk-upload/', include('admin_panel.bulk_upload.urls')),
    path('api/v1/admin/payments/', include('admin_panel.cash_payments.urls')),
    path('api/v1/admin/district-analysis/', include('admin_panel.district_analysis.urls')),
    path('api/v1/admin/enquiries/', include('admin_panel.enquiries.urls')),
    path('api/v1/staff/enquiries/', include('admin_panel.staff_enquiries.urls')),
    path('api/v1/branch/enquiries/', include('admin_panel.enquiries.branch_urls')),
    path('api/v1/admin/success-stories/', include('admin_panel.success_stories.urls')),
    path('api/v1/admin/reports/', include('admin_panel.reports.urls')),
    path('api/v1/admin/audit-log/', include('admin_panel.audit_log.urls')),
    path('api/v1/admin/master/', include('admin_panel.master.urls')),

    # Must be before include('profiles.urls') so this path is always registered (avoids 404 if nested urls are stale).
    path(
        'api/v1/profile/registration-completed/',
        ProfileRegistrationCompletedView.as_view(),
    ),
    path('api/v1/profile/', include('profiles.urls')),
    path('api/v1/astrology/', include('astrology.urls')),
    path('api/v1/dashboard/', include('dashboard.urls')),
    path('api/v1/profiles/<str:matri_id>/preview/', ProfilePreviewByMatriIdView.as_view()),
    path('api/v1/profiles/<str:matri_id>/full/', PublicProfileByMatriIdView.as_view()),
    path('api/v1/profiles/<str:matri_id>/', PublicProfileByMatriIdView.as_view()),
    path('api/v1/master/', include('master.urls')),
    path('api/v1/matches/', include('matches.urls')),
    path('api/v1/interests/', include('plans.urls')),
    path('api/v1/wishlist/', include('wishlist.urls')),
    path('api/v1/plans/', include('plans.urls_plans')),
    path('api/v1/website/plans/', WebsitePlanListView.as_view()),
    path('api/v1/admin/plans/', include('admin_panel.plans.urls')),
    path('api/v1/chat/', include('chat.urls')),
    path('api/v1/settings/', include('user_settings.urls')),
    path('api/v1/contact/unlock/', ContactUnlockView.as_view()),
    path('api/v1/my/plan/', MyPlanView.as_view()),
    path('api/v1/transactions/', include('plans.urls_transactions')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

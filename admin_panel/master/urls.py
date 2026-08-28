from django.urls import include, path

urlpatterns = [
    path("", include("admin_panel.master.caste.urls")),
    path("", include("admin_panel.master.city.urls")),
    path("", include("admin_panel.master.country.urls")),
    path("", include("admin_panel.master.district.urls")),
    path("", include("admin_panel.master.education.urls")),
    path("", include("admin_panel.master.education_subject.urls")),
    path("", include("admin_panel.master.occupation.urls")),
    path("", include("admin_panel.master.mother_tongue.urls")),
    path("", include("admin_panel.master.religion.urls")),
    path("", include("admin_panel.master.state.urls")),
]

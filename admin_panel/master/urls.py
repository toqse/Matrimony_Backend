from django.urls import include, path

urlpatterns = [
    path("", include("admin_panel.master.caste.urls")),
    path("", include("admin_panel.master.mother_tongue.urls")),
    path("", include("admin_panel.master.religion.urls")),
]

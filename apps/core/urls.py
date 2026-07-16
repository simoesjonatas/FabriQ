from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("healthz/", views.healthcheck, name="healthcheck"),
    path("", views.HomeView.as_view(), name="home"),
]

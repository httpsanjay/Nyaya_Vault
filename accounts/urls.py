from django.urls import path

from .views import (
    login_view,
    register_view,
    logout_view,
    dashboard
)

urlpatterns = [
    path(
        "",  # Handles http://127.0.0
        login_view,
        name="home"
    ),
    path(
        "login/",
        login_view,
        name="login"
    ),
    path(
        "register/",
        register_view,
        name="register"
    ),
    path(
        "dashboard/",
        dashboard,
        name="dashboard"
    ),
    path(
        "logout/",
        logout_view,
        name="logout"
    ),
]

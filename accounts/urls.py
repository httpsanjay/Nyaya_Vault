from django.urls import path

from .views import (
    login_view,
    register_view,
    logout_view,
    dashboard
)
from accounts import views

urlpatterns = [
    path("mcp/", views.mcp_page, name="mcp_page"),
    path(
        "", 
        views.index_view,
        name="index"
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
    "check-unique/",
    views.check_unique_field,
    name="check_unique_field"
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

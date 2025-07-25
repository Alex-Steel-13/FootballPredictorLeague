from django.urls import path, include
from . import views

app_name = "users"
urlpatterns = [
    path("register/", views.register_view, name = "registration"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout")
    ]
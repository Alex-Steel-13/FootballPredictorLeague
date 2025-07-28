from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

CustomUser = get_user_model()

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser

    # Fields shown in the admin list view
    list_display = ("username", "email", "is_staff", "is_active", "can_participate")
    list_filter = ("is_staff", "is_active", "is_superuser")

    # Fields shown on the user detail/edit page
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions", "can_participate")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # Fields used when creating a user via the admin
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "is_staff", "is_active", "can_participate"),
        }),
    )

    search_fields = ("username", "email")
    ordering = ("username",)

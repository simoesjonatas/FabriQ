from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class FabriQUserAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "is_active", "last_login")
    list_filter = ("is_active", "is_staff", "groups")

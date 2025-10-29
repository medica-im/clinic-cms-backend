from django.contrib import admin
from django import forms
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TranslationAdmin

from .models import User, GrammaticalGender, Role

class RoleInline(admin.TabularInline):
    model = Role
    extra = 0
    fk_name = 'user'


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = (
            'email',
            'username',
        )


class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = (
            'email',
            'username',
        )


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = (
        'email',
        'username',
        'is_staff',
        'is_active',
        'node',
        'created_at',
        'grammatical_gender',
        'last_login',
        'effector',
        'site',
        'role',
    )
    list_filter = (
        'is_staff',
        'is_active',
        'grammatical_gender',
        'site',
    )
    inlines = (
        RoleInline,
    )
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'email',
                    'username',
                    'password',
                    'bio',
                    'full_name',
                    'birth_date',
                    'grammatical_gender',
                    'node',
                    'effector',
                    'site',
                    'role',
                )
            },
        ),
        (
            'Permissions',
            {
                'fields': (
                    'is_staff',
                    'is_active',
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {'classes': ('wide',), 'fields': ('email', 'username', 'password1', 'password2', 'is_staff', 'is_active')},
        ),
    )
    search_fields = (
        'email',
        'username',
        'effector',
    )
    ordering = (
        'email',
        'username',
    )


@admin.register(GrammaticalGender)
class GrammaticalGenderAdmin(TranslationAdmin):
    list_display = (
        'name',
        'label',
        'code',
    )
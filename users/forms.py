from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from django.core.validators import RegexValidator

User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    username = forms.CharField(
        max_length=150,
        validators=[RegexValidator(
            regex=r'^[\w @*+-]+$',
            message='Username may contain letters, numbers, spaces, and * @ + - .'
        )],
    )

    class Meta:
        model = User
        fields = ("username", "email")  # Add more fields if needed

class CustomAuthenticationForm(AuthenticationForm):
    class Meta:
        model = User
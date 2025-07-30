from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

class CustomUser(AbstractUser):
    can_participate = models.BooleanField(default=True)
    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[RegexValidator(
            regex=r'^[\w @*+-]+$',
            message='Username may contain letters, numbers, spaces, and * @ + - .'
        )],
    )
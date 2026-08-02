from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .models import UserLoginDay


@receiver(user_logged_in)
def record_unique_login_day(sender, request, user, **kwargs):
    UserLoginDay.objects.get_or_create(user=user, login_date=timezone.localdate())

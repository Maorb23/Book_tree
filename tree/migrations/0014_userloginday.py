from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def backfill_last_login_day(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserLoginDay = apps.get_model('tree', 'UserLoginDay')
    rows = []
    for user in User.objects.exclude(last_login=None).iterator():
        login_date = timezone.localtime(user.last_login).date() if timezone.is_aware(user.last_login) else user.last_login.date()
        rows.append(UserLoginDay(user_id=user.id, login_date=login_date))
    if rows:
        UserLoginDay.objects.bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tree', '0013_backfill_user_profiles'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserLoginDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('login_date', models.DateField()),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_days', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-login_date'],
                'constraints': [
                    models.UniqueConstraint(fields=('user', 'login_date'), name='unique_user_login_day'),
                ],
            },
        ),
        migrations.RunPython(backfill_last_login_day, migrations.RunPython.noop),
    ]

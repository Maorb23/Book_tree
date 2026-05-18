from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tree', '0006_treeversion_importedbook'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReadingChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField(default=2026)),
                ('target_books', models.PositiveIntegerField(default=25)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reading_challenges', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='DailyPageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('book_title', models.CharField(max_length=255)),
                ('book_author', models.CharField(blank=True, max_length=255)),
                ('log_date', models.DateField()),
                ('pages', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('imported_book', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='page_logs', to='tree.importedbook')),
                ('node', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='page_logs', to='tree.node')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='daily_page_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-log_date', '-created_at'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='readingchallenge',
            unique_together={('user', 'year')},
        ),
        migrations.AddIndex(
            model_name='readingchallenge',
            index=models.Index(fields=['user', 'year'], name='read_chal_user_year_idx'),
        ),
        migrations.AddIndex(
            model_name='dailypagelog',
            index=models.Index(fields=['user', 'log_date'], name='page_log_user_date_idx'),
        ),
    ]

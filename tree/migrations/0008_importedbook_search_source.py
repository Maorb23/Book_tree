from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0007_reading_challenge_page_log'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importedbook',
            name='source',
            field=models.CharField(
                choices=[('goodreads', 'Goodreads'), ('search', 'Search')],
                default='goodreads',
                max_length=32,
            ),
        ),
    ]

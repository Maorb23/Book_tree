from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0004_user_scoped_tree'),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='custom_shelf',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='node',
            name='shelf',
            field=models.CharField(
                choices=[
                    ('all', 'All'),
                    ('want_to_read', 'Want to Read'),
                    ('currently_reading', 'Currently Reading'),
                    ('read', 'Read'),
                    ('did_not_finish', 'Did Not Finish'),
                ],
                default='want_to_read',
                max_length=32,
            ),
        ),
    ]

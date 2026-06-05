from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0009_multi_tree'),
    ]

    operations = [
        migrations.AddField(
            model_name='treeversion',
            name='comment',
            field=models.TextField(blank=True),
        ),
    ]

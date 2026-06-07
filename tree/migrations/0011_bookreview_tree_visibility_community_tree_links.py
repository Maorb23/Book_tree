from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0010_treeversion_comment'),
    ]

    operations = [
        migrations.AddField(
            model_name='tree',
            name='visibility',
            field=models.CharField(
                choices=[('private', 'Private'), ('friends', 'Friends'), ('public', 'Public')],
                default='private',
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name='BookReview',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(blank=True, max_length=255)),
                ('isbn', models.CharField(blank=True, max_length=20)),
                ('cover_image', models.URLField(blank=True, max_length=1000)),
                ('rating', models.FloatField(blank=True, null=True)),
                ('review', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('imported_book', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='tree.importedbook')),
                ('node', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='tree.node')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='book_reviews', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-updated_at'],
                'indexes': [
                    models.Index(fields=['user', 'updated_at'], name='book_review_user_date_idx'),
                    models.Index(fields=['user', 'isbn'], name='book_review_user_isbn_idx'),
                    models.Index(fields=['user', 'title', 'author'], name='book_review_user_book_idx'),
                ],
            },
        ),
        migrations.AddField(
            model_name='communitypost',
            name='tree',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='community_posts', to='tree.tree'),
        ),
        migrations.AddField(
            model_name='communitypost',
            name='tree_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='community_posts', to='tree.treeversion'),
        ),
    ]

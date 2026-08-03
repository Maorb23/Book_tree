from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import hashlib
import re


def backfill_treecred(apps, schema_editor):
    Tree = apps.get_model('tree', 'Tree')
    Node = apps.get_model('tree', 'Node')
    ImportedBook = apps.get_model('tree', 'ImportedBook')
    Transaction = apps.get_model('tree', 'TreeCredTransaction')

    for tree in Tree.objects.all().iterator():
        Transaction.objects.get_or_create(
            user_id=tree.user_id,
            event_key=f'tree:{tree.pk}',
            defaults={
                'amount': 5,
                'reason': 'tree_created',
                'description': f'Created tree: {tree.name}'[:255],
            },
        )

    def event_key(book):
        isbn = re.sub(r'[^0-9Xx]', '', str(book.isbn or '')).upper()
        if isbn:
            return f'book:isbn:{isbn}'
        identity = ' '.join(f'{book.title} {book.author}'.lower().split())
        return f"book:title:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"

    books = list(ImportedBook.objects.all().iterator())
    books.extend(
        node for node in Node.objects.filter(node_type='book').iterator()
        if not (node.style or {}).get('library_shadow')
    )
    for book in books:
        Transaction.objects.get_or_create(
            user_id=book.user_id,
            event_key=event_key(book),
            defaults={
                'amount': 1,
                'reason': 'book_added',
                'description': f'Added book: {book.title}'[:255],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tree', '0014_userloginday'),
    ]

    operations = [
        migrations.AddField(
            model_name='tree',
            name='generation_mode',
            field=models.CharField(
                choices=[('manual', 'Manual'), ('author', 'Authors'), ('year', 'Years')],
                default='manual',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='tree',
            name='layout_mode',
            field=models.CharField(
                choices=[('organic', 'Organic tree'), ('timeline', 'Year timeline')],
                default='organic',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='tree',
            name='target_books',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='node',
            name='node_type',
            field=models.CharField(
                choices=[
                    ('book', 'Book'), ('author', 'Author'), ('genre', 'Genre'),
                    ('year', 'Year'), ('series', 'Series'), ('custom', 'Custom'),
                ],
                default='book',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='TreeCredTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.IntegerField()),
                ('reason', models.CharField(choices=[('tree_created', 'Tree created'), ('book_added', 'Book added')], max_length=32)),
                ('event_key', models.CharField(max_length=180)),
                ('description', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='treecred_transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['user', 'created_at'], name='treecred_user_date_idx')],
                'constraints': [models.UniqueConstraint(fields=('user', 'event_key'), name='unique_user_treecred_event')],
            },
        ),
        migrations.RunPython(backfill_treecred, migrations.RunPython.noop),
    ]

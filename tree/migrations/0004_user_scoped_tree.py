from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_user_to_tree(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Node = apps.get_model('tree', 'Node')
    Edge = apps.get_model('tree', 'Edge')

    user = User.objects.order_by('id').first()
    if not user:
        user = User.objects.create(username='legacy')
        user.set_unusable_password()
        user.save(update_fields=['password'])

    Node.objects.filter(user__isnull=True).update(user=user)

    edges = Edge.objects.filter(user__isnull=True).select_related('source')
    for edge in edges:
        edge.user_id = edge.source.user_id or user.id
        edge.save(update_fields=['user'])


def unassign_user_from_tree(apps, schema_editor):
    Node = apps.get_model('tree', 'Node')
    Edge = apps.get_model('tree', 'Edge')
    Node.objects.update(user=None)
    Edge.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ('tree', '0003_rename_tree_friend_to_user_status_idx_tree_friend_to_user_5d2a1e_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='node',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='nodes',
            ),
        ),
        migrations.AddField(
            model_name='edge',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='edges',
            ),
        ),
        migrations.RunPython(assign_user_to_tree, unassign_user_from_tree),
        migrations.AlterField(
            model_name='node',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='nodes',
            ),
        ),
        migrations.AlterField(
            model_name='edge',
            name='user',
            field=models.ForeignKey(
                to=settings.AUTH_USER_MODEL,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='edges',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='edge',
            unique_together={('user', 'source', 'target', 'edge_type')},
        ),
        migrations.AddIndex(
            model_name='node',
            index=models.Index(fields=['user', 'date_added'], name='tree_node_user_date_idx'),
        ),
        migrations.AddIndex(
            model_name='edge',
            index=models.Index(fields=['user', 'edge_type'], name='tree_edge_user_type_idx'),
        ),
    ]

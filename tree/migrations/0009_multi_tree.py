from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_default_trees(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Tree = apps.get_model('tree', 'Tree')
    Node = apps.get_model('tree', 'Node')
    Edge = apps.get_model('tree', 'Edge')
    TreeVersion = apps.get_model('tree', 'TreeVersion')

    for user in User.objects.all():
        tree, _ = Tree.objects.get_or_create(
            user=user,
            is_default=True,
            defaults={'name': 'Main Tree'},
        )
        Node.objects.filter(user=user, tree__isnull=True).update(tree=tree)
        Edge.objects.filter(user=user, tree__isnull=True).update(tree=tree)
        TreeVersion.objects.filter(user=user, tree__isnull=True).update(tree=tree)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tree', '0008_importedbook_search_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='Tree',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160)),
                ('description', models.CharField(blank=True, max_length=280)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trees', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.AddField(
            model_name='node',
            name='tree',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='nodes', to='tree.tree'),
        ),
        migrations.AddField(
            model_name='edge',
            name='tree',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='edges', to='tree.tree'),
        ),
        migrations.AddField(
            model_name='treeversion',
            name='tree',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='tree.tree'),
        ),
        migrations.RunPython(create_default_trees, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='tree',
            index=models.Index(fields=['user', 'is_default'], name='tree_user_default_idx'),
        ),
        migrations.AddIndex(
            model_name='node',
            index=models.Index(fields=['tree', 'date_added'], name='tree_node_tree_date_idx'),
        ),
        migrations.AddIndex(
            model_name='edge',
            index=models.Index(fields=['tree', 'edge_type'], name='tree_edge_tree_type_idx'),
        ),
        migrations.AddIndex(
            model_name='treeversion',
            index=models.Index(fields=['tree', 'created_at'], name='tree_version_tree_date_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='edge',
            unique_together={('user', 'tree', 'source', 'target', 'edge_type')},
        ),
    ]

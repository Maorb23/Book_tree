from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import ImportedBook, Node, Tree, TreeCredTransaction, UserLoginDay
from .treecred import award_treecred, book_event_key, tree_event_key


@receiver(user_logged_in)
def record_unique_login_day(sender, request, user, **kwargs):
    UserLoginDay.objects.get_or_create(user=user, login_date=timezone.localdate())


@receiver(post_save, sender=Tree)
def award_tree_creation_credit(sender, instance, created, **kwargs):
    if created:
        award_treecred(
            instance.user_id,
            tree_event_key(instance.pk),
            5,
            TreeCredTransaction.REASON_TREE,
            f'Created tree: {instance.name}',
        )


@receiver(post_save, sender=ImportedBook)
def award_imported_book_credit(sender, instance, created, **kwargs):
    if created:
        award_treecred(
            instance.user_id,
            book_event_key(instance),
            1,
            TreeCredTransaction.REASON_BOOK,
            f'Added book: {instance.title}',
        )


@receiver(post_save, sender=Node)
def award_tree_book_credit(sender, instance, created, **kwargs):
    if not created or instance.node_type != 'book' or (instance.style or {}).get('library_shadow'):
        return
    award_treecred(
        instance.user_id,
        book_event_key(instance),
        1,
        TreeCredTransaction.REASON_BOOK,
        f'Added book: {instance.title}',
    )

import hashlib
import re

from .models import TreeCredTransaction


def tree_event_key(tree_id):
    return f'tree:{tree_id}'


def book_event_key(book):
    isbn = re.sub(r'[^0-9Xx]', '', str(getattr(book, 'isbn', '') or '')).upper()
    if isbn:
        return f'book:isbn:{isbn}'
    identity = ' '.join(
        f"{getattr(book, 'title', '')} {getattr(book, 'author', '')}".lower().split()
    )
    digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    return f'book:title:{digest}'


def award_treecred(user_id, event_key, amount, reason, description):
    return TreeCredTransaction.objects.get_or_create(
        user_id=user_id,
        event_key=event_key,
        defaults={
            'amount': amount,
            'reason': reason,
            'description': description[:255],
        },
    )

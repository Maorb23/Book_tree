(function () {
  'use strict';

  const tabs = Array.from(document.querySelectorAll('.shelf-tab'));
  const cards = Array.from(document.querySelectorAll('.library-book'));
  const search = document.getElementById('bookSearch');
  const toast = document.getElementById('shelfToast');
  let activeFilter = 'all';

  function getCsrf() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 2200);
  }

  function matchesFilter(card) {
    if (activeFilter === 'all') return true;
    if (activeFilter.startsWith('custom:')) {
      return card.dataset.custom === activeFilter.slice(7).toLowerCase();
    }
    return card.dataset.shelf === activeFilter;
  }

  function matchesSearch(card) {
    const q = (search?.value || '').trim().toLowerCase();
    if (!q) return true;
    return [
      card.dataset.title,
      card.dataset.author,
      card.dataset.genre,
      card.dataset.shelf,
      card.dataset.custom,
    ].some(value => (value || '').includes(q));
  }

  function applyFilters() {
    cards.forEach(card => {
      card.classList.toggle('is-hidden', !(matchesFilter(card) && matchesSearch(card)));
    });
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      activeFilter = tab.dataset.filter || 'all';
      tabs.forEach(item => item.classList.toggle('active', item === tab));
      applyFilters();
    });
  });

  search?.addEventListener('input', applyFilters);

  document.querySelectorAll('.save-book-shelf').forEach(button => {
    button.addEventListener('click', async () => {
      const card = button.closest('.library-book');
      if (!card) return;
      const shelf = card.querySelector('.shelf-select')?.value || 'want_to_read';
      const customShelf = (card.querySelector('.custom-shelf-input')?.value || '').trim();

      button.disabled = true;
      button.textContent = 'Saving...';
      try {
        const res = await fetch(`/api/nodes/${card.dataset.id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({ shelf, custom_shelf: customShelf }),
        });
        if (!res.ok) throw new Error('Save failed');
        card.dataset.shelf = shelf;
        card.dataset.custom = customShelf.toLowerCase();
        applyFilters();
        showToast('Shelf updated.');
      } catch (_) {
        showToast('Could not update this shelf.');
      } finally {
        button.disabled = false;
        button.textContent = 'Save';
      }
    });
  });

  applyFilters();
})();

(function () {
  'use strict';

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

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
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

  function syncShelfTabs() {
    const baseCounts = {
      all: cards.length,
      want_to_read: 0,
      currently_reading: 0,
      read: 0,
      did_not_finish: 0,
    };
    const customCounts = new Map();

    cards.forEach(card => {
      const shelf = card.dataset.shelf || 'want_to_read';
      if (baseCounts[shelf] !== undefined) baseCounts[shelf] += 1;
      const custom = (card.dataset.custom || '').trim();
      const customLabel = (card.dataset.customLabel || custom).trim();
      if (custom) {
        const existing = customCounts.get(custom) || { label: customLabel, count: 0 };
        existing.count += 1;
        if (customLabel) existing.label = customLabel;
        customCounts.set(custom, existing);
      }
    });

    Object.entries(baseCounts).forEach(([filter, count]) => {
      const tab = document.querySelector(`.shelf-tab[data-filter="${filter}"]`);
      const countEl = tab?.querySelector('span');
      if (countEl) countEl.textContent = String(count);
    });

    const customHost = document.querySelector('.custom-shelves');
    if (!customHost) return;
    customHost.querySelectorAll('.shelf-tab').forEach(tab => tab.remove());
    const empty = customHost.querySelector('p');
    if (empty) empty.style.display = customCounts.size ? 'none' : '';

    [...customCounts.entries()]
      .sort(([, a], [, b]) => a.label.localeCompare(b.label))
      .forEach(([key, row]) => {
        const button = document.createElement('button');
        button.className = `shelf-tab${activeFilter === `custom:${key}` ? ' active' : ''}`;
        button.dataset.filter = `custom:${key}`;
        button.innerHTML = `${escapeHtml(row.label)} <span>${row.count}</span>`;
        customHost.appendChild(button);
      });

    const activeTab = Array.from(document.querySelectorAll('.shelf-tab'))
      .find(tab => (tab.dataset.filter || 'all') === activeFilter);
    if (!activeTab) activeFilter = 'all';
    document.querySelectorAll('.shelf-tab').forEach(tab => {
      tab.classList.toggle('active', (tab.dataset.filter || 'all') === activeFilter);
    });
  }

  document.addEventListener('click', event => {
    const tab = event.target.closest('.shelf-tab');
    if (!tab) return;
    activeFilter = tab.dataset.filter || 'all';
    document.querySelectorAll('.shelf-tab').forEach(item => item.classList.toggle('active', item === tab));
    applyFilters();
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
        card.dataset.customLabel = customShelf;
        syncShelfTabs();
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

  syncShelfTabs();
  applyFilters();
})();

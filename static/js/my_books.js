(function () {
  'use strict';

  const cards = Array.from(document.querySelectorAll('.library-book'));
  const search = document.getElementById('bookSearch');
  const toast = document.getElementById('shelfToast');
  const importPanel = document.getElementById('goodreadsImport');
  const importForm = document.getElementById('goodreadsImportForm');
  const importSummary = document.getElementById('importSummary');
  const importPreview = document.getElementById('importPreview');
  const importRows = document.getElementById('importPreviewRows');
  const confirmImport = document.getElementById('confirmGoodreadsImport');
  const previewTitle = document.getElementById('importPreviewTitle');
  let activeFilter = 'all';
  let previewBooks = [];

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

  document.getElementById('openImportBooks')?.addEventListener('click', () => {
    if (!importPanel) return;
    importPanel.hidden = false;
    importPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  document.getElementById('closeImportBooks')?.addEventListener('click', () => {
    if (importPanel) importPanel.hidden = true;
  });

  function shelfLabel(value) {
    return {
      want_to_read: 'Want to Read',
      currently_reading: 'Currently Reading',
      read: 'Read',
      did_not_finish: 'Did Not Finish',
    }[value] || 'Want to Read';
  }

  function renderImportPreview(data) {
    previewBooks = data.books || [];
    if (!importRows || !importPreview || !confirmImport || !previewTitle) return;

    previewTitle.textContent = `Preview matched books (${data.importable_count || 0} ready, ${data.existing_count || 0} already in tree)`;
    importRows.innerHTML = previewBooks.map((book, index) => {
      const disabled = book.exists ? 'disabled' : '';
      const checked = book.exists ? '' : 'checked';
      const meta = [book.author, book.year].filter(Boolean).map(escapeHtml).join(' · ');
      return `
        <tr class="${book.exists ? 'is-existing' : ''}">
          <td><input type="checkbox" data-import-index="${index}" ${checked} ${disabled} aria-label="Import ${escapeHtml(book.title)}"></td>
          <td>
            <strong>${escapeHtml(book.title)}</strong>
            <span>${meta || 'Unknown author'}</span>
          </td>
          <td>${escapeHtml(shelfLabel(book.shelf))}${book.custom_shelf ? ` · ${escapeHtml(book.custom_shelf)}` : ''}</td>
          <td><span class="import-status">${escapeHtml(book.match)}</span></td>
        </tr>
      `;
    }).join('');
    importPreview.hidden = false;
    confirmImport.disabled = !previewBooks.some(book => !book.exists);
  }

  importForm?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!importSummary) return;
    const formData = new FormData(importForm);
    const file = formData.get('csv_file');
    if (!file || !file.name) {
      showToast('Choose your Goodreads CSV first.');
      return;
    }

    importSummary.textContent = 'Reading your Goodreads export...';
    if (confirmImport) confirmImport.disabled = true;

    try {
      const res = await fetch('/api/goodreads/preview/', {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrf() },
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Preview failed');
      importSummary.textContent = `${data.total} books found. ${data.importable_count} can be imported and ${data.existing_count} already exist in your tree.`;
      renderImportPreview(data);
    } catch (error) {
      importSummary.textContent = error.message || 'Could not preview this file.';
      if (importPreview) importPreview.hidden = true;
    }
  });

  confirmImport?.addEventListener('click', async () => {
    const selected = Array.from(document.querySelectorAll('[data-import-index]:checked'))
      .map(input => previewBooks[Number(input.dataset.importIndex)])
      .filter(Boolean);

    if (!selected.length) {
      showToast('Select at least one book to import.');
      return;
    }

    confirmImport.disabled = true;
    confirmImport.textContent = 'Importing...';
    try {
      const res = await fetch('/api/goodreads/import/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ books: selected }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Import failed');
      showToast(`Imported ${data.created_count} books.`);
      window.location.reload();
    } catch (error) {
      showToast(error.message || 'Could not import these books.');
      confirmImport.disabled = false;
      confirmImport.textContent = 'Confirm Import';
    }
  });

  document.querySelectorAll('.save-book-shelf').forEach(button => {
    button.addEventListener('click', async () => {
      const card = button.closest('.library-book');
      if (!card) return;
      const shelf = card.querySelector('.shelf-select')?.value || 'want_to_read';
      const customShelf = (card.querySelector('.custom-shelf-input')?.value || '').trim();

      button.disabled = true;
      button.textContent = 'Saving...';
      try {
        const endpoint = card.dataset.source === 'imported'
          ? `/api/imported-books/${card.dataset.id}/`
          : `/api/nodes/${card.dataset.id}/`;
        const res = await fetch(endpoint, {
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

  document.querySelectorAll('.add-book-to-tree').forEach(button => {
    button.addEventListener('click', async () => {
      const card = button.closest('.library-book');
      if (!card) return;
      const parent = card.querySelector('.tree-parent-select')?.value || null;
      const isImported = card.dataset.source === 'imported';
      const endpoint = isImported
        ? `/api/imported-books/${card.dataset.id}/add-to-tree/`
        : `/api/nodes/${card.dataset.id}/`;

      button.disabled = true;
      button.textContent = isImported ? 'Adding...' : 'Moving...';
      try {
        const res = await fetch(endpoint, {
          method: isImported ? 'POST' : 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({ parent, pos_x: null, pos_y: null }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const message = data.parent?.[0] || data.detail || 'Could not update the tree.';
          throw new Error(message);
        }
        if (data.id) card.dataset.id = data.id;
        card.dataset.source = 'tree';
        showToast(isImported ? 'Book added to your tree.' : 'Book moved in your tree.');
      } catch (error) {
        showToast(error.message || 'Could not update the tree.');
      } finally {
        button.disabled = false;
        button.textContent = 'Move in Tree';
      }
    });
  });

  syncShelfTabs();
  applyFilters();
})();

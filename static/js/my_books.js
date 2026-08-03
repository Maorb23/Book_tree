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
  const addBooksPanel = document.getElementById('addBooksPanel');
  const catalogSearch = document.getElementById('catalogBookSearch');
  const catalogResults = document.getElementById('catalogResults');
  const runCatalogSearch = document.getElementById('runCatalogSearch');
  const autoTreeShelf = document.getElementById('autoTreeShelf');
  const autoTreeMode = document.getElementById('autoTreeMode');
  const autoTreeDestination = document.getElementById('autoTreeDestination');
  const autoTreeName = document.getElementById('autoTreeName');
  const createAutoTree = document.getElementById('createAutoTree');
  const autoTreeStatus = document.getElementById('autoTreeStatus');
  const recommendationGrid = document.getElementById('recommendationGrid');
  const refreshRecommendations = document.getElementById('refreshRecommendations');
  let activeFilter = 'all';
  let previewBooks = [];
  let catalogSearchTimer = null;
  const readingPanelState = (() => {
    try {
      return JSON.parse(localStorage.getItem('readwoodsReadingPanels') || '{}');
    } catch (_) {
      return {};
    }
  })();

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

  function readingPanelKey(card) {
    return `${card.dataset.source || 'book'}:${card.dataset.id || card.dataset.title || ''}`;
  }

  function saveReadingPanelState() {
    try {
      localStorage.setItem('readwoodsReadingPanels', JSON.stringify(readingPanelState));
    } catch (_) {
      // Ignore storage failures; the panel still works for this session.
    }
  }

  function setReadingPanelCollapsed(panel, collapsed) {
    panel.classList.toggle('is-collapsed', collapsed);
    const toggle = panel.querySelector('.reading-update__toggle');
    if (toggle) {
      toggle.textContent = collapsed ? 'Show' : 'Hide';
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
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
    if (activeFilter === 'reviewed') return card.dataset.reviewed === '1';
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

  function syncReadingControls(card) {
    const panel = card.querySelector('.reading-update');
    if (!panel) return;
    panel.hidden = card.dataset.shelf !== 'currently_reading';
    setReadingPanelCollapsed(panel, readingPanelState[readingPanelKey(card)] === 'hidden');
    const dateInput = panel.querySelector('.reading-date-input');
    if (dateInput && !dateInput.value) dateInput.value = new Date().toISOString().slice(0, 10);
  }

  function syncShelfTabs() {
    const baseCounts = {
      all: cards.length,
      want_to_read: 0,
      currently_reading: 0,
      read: 0,
      did_not_finish: 0,
      reviewed: 0,
    };
    const customCounts = new Map();

    cards.forEach(card => {
      const shelf = card.dataset.shelf || 'want_to_read';
      if (baseCounts[shelf] !== undefined) baseCounts[shelf] += 1;
      if (card.dataset.reviewed === '1') baseCounts.reviewed += 1;
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

  document.addEventListener('click', event => {
    const button = event.target.closest('.reading-update__toggle');
    if (!button) return;
    const panel = button.closest('.reading-update');
    const card = button.closest('.library-book');
    if (!panel || !card) return;
    const collapsed = !panel.classList.contains('is-collapsed');
    setReadingPanelCollapsed(panel, collapsed);
    readingPanelState[readingPanelKey(card)] = collapsed ? 'hidden' : 'shown';
    saveReadingPanelState();
  });

  async function saveReviewForCard(card, reviewText) {
    const res = await fetch('/api/book-reviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        imported_book: card.dataset.source === 'imported' ? card.dataset.id : null,
        node: card.dataset.source === 'tree' ? card.dataset.id : null,
        title: card.querySelector('h3')?.textContent?.trim() || '',
        author: card.dataset.author || '',
        isbn: card.dataset.isbn || '',
        cover_image: card.dataset.cover || '',
        review: reviewText,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Could not save review.');
    return data;
  }

  document.addEventListener('click', async event => {
    const button = event.target.closest('.add-book-review');
    if (!button) return;
    const card = button.closest('.library-book');
    if (!card) return;
    const title = card.querySelector('h3')?.textContent?.trim() || 'this book';
    const text = window.prompt(`Review "${title}"`);
    if (text === null) return;
    const review = text.trim();
    if (!review) {
      showToast('Review cannot be empty.');
      return;
    }
    button.disabled = true;
    try {
      await saveReviewForCard(card, review);
      card.dataset.reviewed = '1';
      button.textContent = 'Edit Review';
      syncShelfTabs();
      applyFilters();
      showToast('Review saved.');
    } catch (error) {
      showToast(error.message || 'Could not save review.');
    } finally {
      button.disabled = false;
    }
  });

  document.addEventListener('click', async event => {
    const button = event.target.closest('.delete-library-book');
    if (!button) return;
    const card = button.closest('.library-book');
    if (!card) return;

    const title = card.querySelector('h3')?.textContent?.trim() || 'this book';
    const source = card.dataset.source;
    const endpoint = source === 'imported'
      ? `/api/imported-books/${encodeURIComponent(card.dataset.id)}/`
      : `/api/nodes/${encodeURIComponent(card.dataset.id)}/`;
    const warning = source === 'tree'
      ? `Delete "${title}"? This will also remove it from your tree.`
      : `Delete "${title}" from My Books?`;
    if (!window.confirm(warning)) return;

    button.disabled = true;
    button.textContent = 'Deleting...';
    try {
      const res = await fetch(endpoint, {
        method: 'DELETE',
        headers: { 'X-CSRFToken': getCsrf() },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Could not delete this book.');
      }
      showToast('Book deleted.');
      window.location.reload();
    } catch (error) {
      showToast(error.message || 'Could not delete this book.');
      button.disabled = false;
      button.textContent = 'Delete Book';
    }
  });

  document.addEventListener('click', event => {
    const button = event.target.closest('.read-review-more');
    if (!button) return;
    const text = button.closest('.review-card')?.querySelector('.review-card__text');
    if (!text) return;
    text.classList.toggle('is-collapsed');
    button.textContent = text.classList.contains('is-collapsed') ? 'Read more' : 'Show less';
  });

  function openAddBooksPanel() {
    if (!addBooksPanel) return;
    addBooksPanel.hidden = false;
    addBooksPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setTimeout(() => catalogSearch?.focus(), 120);
  }

  document.getElementById('openAddBooks')?.addEventListener('click', openAddBooksPanel);
  document.getElementById('emptyAddBooks')?.addEventListener('click', openAddBooksPanel);
  document.getElementById('closeAddBooks')?.addEventListener('click', () => {
    if (addBooksPanel) addBooksPanel.hidden = true;
  });

  function bookPayload(book) {
    return {
      title: book.title || '',
      author: book.author || '',
      genre: book.genre || '',
      year: book.year || null,
      isbn: book.isbn || '',
      source_key: book.isbn || `${book.title || ''}:${book.author || ''}`,
      cover_image: book.cover_url || book.cover_image || '',
      notes: book.description || '',
      shelf: 'want_to_read',
    };
  }

  function recommendationPayload(book) {
    return {
      ...bookPayload(book),
      source_key: book.isbn || `recommendation:${book.title || ''}:${book.author || ''}`,
      cover_image: book.cover_url || book.cover_image || '',
      notes: book.description || book.reason || '',
    };
  }

  function renderAutoTreeStatus(message, tone) {
    if (!autoTreeStatus) return;
    autoTreeStatus.textContent = message || '';
    autoTreeStatus.classList.toggle('is-error', tone === 'error');
    autoTreeStatus.classList.toggle('is-success', tone === 'success');
  }

  async function runAutoTreeGeneration() {
    if (!autoTreeShelf || !createAutoTree) return;
    const rawValue = autoTreeShelf.value || '';
    if (!rawValue) {
      renderAutoTreeStatus('Choose a shelf first.', 'error');
      autoTreeShelf.focus();
      return;
    }
    const separator = rawValue.indexOf(':');
    const shelfType = separator >= 0 ? rawValue.slice(0, separator) : 'custom';
    const shelf = separator >= 0 ? rawValue.slice(separator + 1) : rawValue;
    const destinationValue = autoTreeDestination?.value || 'new';
    const destinationSeparator = destinationValue.indexOf(':');
    const destination = destinationSeparator >= 0 ? destinationValue.slice(0, destinationSeparator) : destinationValue;
    const treeId = destinationSeparator >= 0 ? destinationValue.slice(destinationSeparator + 1) : '';

    createAutoTree.disabled = true;
    createAutoTree.textContent = 'Creating...';
    const selectedMode = autoTreeMode?.value || 'author';
    renderAutoTreeStatus(selectedMode === 'year'
      ? 'Arranging your shelf into a year timeline...'
      : 'Shaping your shelf into author branches...');
    try {
      const res = await fetch('/api/tree/auto-from-shelf/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({
          shelf,
          shelf_type: shelfType,
          mode: selectedMode,
          destination,
          tree_id: treeId,
          tree_name: autoTreeName?.value || '',
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not create an auto tree from this shelf.');
      const summary = [
        selectedMode === 'year'
          ? `${data.created_years || 0} years created`
          : `${data.created_authors || 0} authors created`,
        `${data.created_books || 0} books added`,
        `${data.reused_books || 0} books reused`,
      ].join(', ');
      renderAutoTreeStatus(`Tree created: ${summary}.`, 'success');
      showToast('Auto tree created. Open My Tree to see it.');
    } catch (error) {
      renderAutoTreeStatus(error.message || 'Could not create an auto tree from this shelf.', 'error');
      showToast(error.message || 'Could not create this tree.');
    } finally {
      createAutoTree.disabled = false;
      createAutoTree.textContent = 'Create Tree';
    }
  }

  createAutoTree?.addEventListener('click', runAutoTreeGeneration);
  autoTreeDestination?.addEventListener('change', () => {
    if (!autoTreeName) return;
    autoTreeName.hidden = (autoTreeDestination.value || 'new') !== 'new';
  });

  function renderRecommendations(results, message) {
    if (!recommendationGrid) return;
    if (message) {
      recommendationGrid.innerHTML = `<p class="recommendation-message">${escapeHtml(message)}</p>`;
      return;
    }
    if (!results.length) {
      recommendationGrid.innerHTML = '<p class="recommendation-message">Add or rate a few books and recommendations will get sharper.</p>';
      return;
    }
    recommendationGrid.innerHTML = results.map((book, index) => {
      const cover = book.cover_url
        ? `<img src="${escapeHtml(book.cover_url)}" alt="">`
        : `<span>${escapeHtml((book.title || 'B').slice(0, 1))}</span>`;
      const meta = [book.author || 'Unknown author', book.genre, book.year].filter(Boolean).map(escapeHtml).join(' &middot; ');
      return `
        <article class="recommendation-book">
          <div class="recommendation-book__cover">${cover}</div>
          <div class="recommendation-book__body">
            <h3>${escapeHtml(book.title || 'Untitled')}</h3>
            <p>${meta}</p>
            <span>${escapeHtml(book.reason || 'Based on your library')}</span>
          </div>
          <button class="btn btn--primary btn--sm add-recommendation-book" type="button" data-index="${index}">Add</button>
        </article>
      `;
    }).join('');

    recommendationGrid.querySelectorAll('.add-recommendation-book').forEach(button => {
      button.addEventListener('click', async () => {
        const book = results[Number(button.dataset.index)];
        if (!book) return;
        button.disabled = true;
        button.textContent = 'Adding...';
        try {
          const res = await fetch('/api/my-books/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body: JSON.stringify(recommendationPayload(book)),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.detail || 'Could not add this recommendation.');
          showToast('Recommendation added to My Books.');
          window.location.reload();
        } catch (error) {
          showToast(error.message || 'Could not add this recommendation.');
          button.disabled = false;
          button.textContent = 'Add';
        }
      });
    });
  }

  async function loadRecommendations() {
    if (!recommendationGrid) return;
    renderRecommendations([], 'Finding matches from your shelves...');
    if (refreshRecommendations) refreshRecommendations.disabled = true;
    try {
      const res = await fetch('/api/my-books/recommendations/', { cache: 'no-store' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not load recommendations.');
      renderRecommendations(data.results || []);
    } catch (error) {
      renderRecommendations([], error.message || 'Could not load recommendations right now.');
    } finally {
      if (refreshRecommendations) refreshRecommendations.disabled = false;
    }
  }

  refreshRecommendations?.addEventListener('click', loadRecommendations);

  function renderCatalogResults(results, message) {
    if (!catalogResults) return;
    if (message) {
      catalogResults.innerHTML = `<p class="catalog-results__message">${escapeHtml(message)}</p>`;
      return;
    }
    if (!results.length) {
      catalogResults.innerHTML = '<p class="catalog-results__message">No matching books found. Try a title, author, or ISBN.</p>';
      return;
    }
    catalogResults.innerHTML = results.map((book, index) => {
      const cover = book.cover_url
        ? `<img src="${escapeHtml(book.cover_url)}" alt="">`
        : `<span>${escapeHtml((book.title || 'B').slice(0, 1))}</span>`;
      const meta = [book.author || 'Unknown author', book.genre, book.year].filter(Boolean).map(escapeHtml).join(' &middot; ');
      return `
        <article class="catalog-book">
          <div class="catalog-book__cover">${cover}</div>
          <div class="catalog-book__body">
            <h3>${escapeHtml(book.title || 'Untitled')}</h3>
            <p>${meta}</p>
          </div>
          <button class="btn btn--primary btn--sm add-catalog-book" type="button" data-index="${index}">Add</button>
        </article>
      `;
    }).join('');

    catalogResults.querySelectorAll('.add-catalog-book').forEach(button => {
      button.addEventListener('click', async () => {
        const book = results[Number(button.dataset.index)];
        if (!book) return;
        button.disabled = true;
        button.textContent = 'Adding...';
        try {
          const res = await fetch('/api/my-books/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body: JSON.stringify(bookPayload(book)),
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) throw new Error(data.detail || 'Could not add this book.');
          showToast('Book added to My Books.');
          window.location.reload();
        } catch (error) {
          showToast(error.message || 'Could not add this book.');
          button.disabled = false;
          button.textContent = 'Add';
        }
      });
    });
  }

  async function searchCatalogBooks() {
    const query = (catalogSearch?.value || '').trim();
    if (query.length < 2) {
      renderCatalogResults([], 'Type at least two characters to search.');
      return;
    }
    renderCatalogResults([], 'Searching the catalog...');
    if (runCatalogSearch) runCatalogSearch.disabled = true;
    try {
      const res = await fetch(`/api/book-search/?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed.');
      renderCatalogResults((data.results || []).slice(0, 8));
    } catch (error) {
      renderCatalogResults([], error.message || 'Could not search right now.');
    } finally {
      if (runCatalogSearch) runCatalogSearch.disabled = false;
    }
  }

  runCatalogSearch?.addEventListener('click', searchCatalogBooks);
  catalogSearch?.addEventListener('input', () => {
    if (catalogSearchTimer) clearTimeout(catalogSearchTimer);
    catalogSearchTimer = setTimeout(searchCatalogBooks, 380);
  });
  catalogSearch?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      searchCatalogBooks();
    }
  });

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
        syncReadingControls(card);
        syncShelfTabs();
        applyFilters();
        showToast('Shelf updated.');
      } catch (_) {
        showToast('Could not update this shelf.');
      } finally {
        button.disabled = false;
        button.textContent = 'Save To Shelf';
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
      button.textContent = 'Adding...';
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
        showToast('Book added to your tree.');
      } catch (error) {
        showToast(error.message || 'Could not update the tree.');
      } finally {
        button.disabled = false;
        button.textContent = 'Add to tree';
      }
    });
  });

  document.querySelectorAll('.log-reading-update').forEach(button => {
    button.addEventListener('click', async () => {
      const card = button.closest('.library-book');
      if (!card) return;
      const pagesInput = card.querySelector('.reading-pages-input');
      const dateInput = card.querySelector('.reading-date-input');
      const pages = Number(pagesInput?.value || 0);
      if (!pages || pages < 1) {
        showToast('Enter how many pages you read.');
        pagesInput?.focus();
        return;
      }

      button.disabled = true;
      button.textContent = 'Logging...';
      try {
        const res = await fetch('/api/reading-updates/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({
            source: card.dataset.source,
            book_id: card.dataset.id,
            pages,
            log_date: dateInput?.value || new Date().toISOString().slice(0, 10),
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || 'Could not log pages.');
        if (pagesInput) pagesInput.value = '';
        showToast(`Logged ${pages} pages. Best streak: ${data.best_page_streak || 0} days.`);
      } catch (error) {
        showToast(error.message || 'Could not log pages.');
      } finally {
        button.disabled = false;
        button.textContent = 'Log Pages';
      }
    });
  });

  cards.forEach(syncReadingControls);
  syncShelfTabs();
  applyFilters();
  loadRecommendations();
})();

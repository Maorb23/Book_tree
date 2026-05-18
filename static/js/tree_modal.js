/* ─── TREE MODAL — Add / Edit Nodes ────────────────── */
'use strict';

(function () {
  function notify(message, level = 'info') {
    if (typeof window.showToast === 'function') {
      window.showToast(message, level);
      return;
    }
    alert(message);
  }

  const modal = document.getElementById('bookModal');
  const overlay = modal;

  // Form fields
  const fTitle    = document.getElementById('fTitle');
  const fAuthor   = document.getElementById('fAuthor');
  const fGenre    = document.getElementById('fGenre');
  const fYear     = document.getElementById('fYear');
  const fIsbn     = document.getElementById('fIsbn');
  const fRating   = document.getElementById('fRating');
  const fCoverUrl = document.getElementById('fCoverUrl');
  const fCoverFile= document.getElementById('fCoverFile');
  const fParent   = document.getElementById('fParent');
  const fColor    = document.getElementById('fColor');
  const fGlow     = document.getElementById('fGlow');
  const fBorder   = document.getElementById('fBorder');
  const fParentEdgeColor = document.getElementById('fParentEdgeColor');
  const fParentEdgeStyle = document.getElementById('fParentEdgeStyle');
  const fParentEdgeWidth = document.getElementById('fParentEdgeWidth');
  const fNotes    = document.getElementById('fNotes');
  const coverPreview = document.getElementById('coverPreview');
  const modalTitle   = document.getElementById('modalTitle');
  const deleteBtn    = document.getElementById('deleteNodeBtn');
  const floatBar     = document.getElementById('floatBar');
  const bookSuggestions = document.getElementById('bookSuggestions');

  let editingNode = null;
  let selectedType = 'book';
  let selectedBadges = new Set();
  let autocompleteOptions = [];

  // ── Open / close ──────────────────────────────────────
  function openModal() {
    // Populate parent select from loaded nodes
    fParent.innerHTML = '<option value="">— root (no parent) —</option>';
    (window.allNodes || []).forEach(n => {
      const opt = document.createElement('option');
      opt.value = n.id;
      opt.textContent = `${n.title} (${n.node_type})`;
      fParent.appendChild(opt);
    });
    overlay.classList.add('open');
  }

  function closeModal() {
    overlay.classList.remove('open');
    resetForm();
  }

  function resetForm() {
    editingNode = null;
    fTitle.value = ''; fAuthor.value = ''; fGenre.value = '';
    fYear.value = ''; fIsbn.value = ''; fRating.value = '';
    fCoverUrl.value = ''; fNotes.value = '';
    fParent.value = '';
    fColor.value = '#1a3a5c';
    fGlow.value = '#4fc3f7';
    fBorder.value = '#4fc3f7';
    if (fParentEdgeColor) fParentEdgeColor.value = '#ccc7cf';
    if (fParentEdgeStyle) fParentEdgeStyle.value = 'solid';
    if (fParentEdgeWidth) fParentEdgeWidth.value = '3';
    coverPreview.innerHTML = '<span>No cover</span>';
    selectedType = 'book';
    selectedBadges = new Set();
    updateTypeButtons();
    updateBadges();
    modalTitle.textContent = 'ADD NEW NODE';
    deleteBtn.style.display = 'none';
    autocompleteOptions = [];
    if (bookSuggestions) bookSuggestions.innerHTML = '';
  }

  // ── Open for new book ──────────────────────────────────
  function openAddModal(preParent) {
    resetForm();
    if (preParent) {
      openModal();
      const opt = document.querySelector(`#fParent option[value="${preParent.id}"]`);
      if (opt) fParent.value = preParent.id;
    } else {
      openModal();
    }
    modalTitle.textContent = 'ADD NEW NODE';
  }
  window.openAddModal = openAddModal;

  function openAddChildModal(parentNode) {
    document.getElementById('sidebar').classList.remove('open');
    openAddModal(parentNode);
  }
  window.openAddChildModal = openAddChildModal;

  // ── Open for edit ──────────────────────────────────────
  function openEditModal(node) {
    document.getElementById('sidebar').classList.remove('open');
    editingNode = node;
    openModal();
    modalTitle.textContent = 'EDIT NODE';
    deleteBtn.style.display = 'block';

    fTitle.value  = node.title || '';
    fAuthor.value = node.author || '';
    fGenre.value  = node.genre || '';
    fYear.value   = node.year || '';
    fIsbn.value   = node.isbn || '';
    fRating.value = node.rating || '';
    fNotes.value  = node.notes || '';
    fCoverUrl.value = node.cover_image || '';
    if (node.parent) fParent.value = node.parent;

    if (node.style) {
      fColor.value  = node.style.color  || '#1a3a5c';
      fGlow.value   = node.style.glow   || '#4fc3f7';
      fBorder.value = node.style.border || '#4fc3f7';
      const parentEdge = node.style.parent_edge || node.style.parentEdge || {};
      if (fParentEdgeColor) fParentEdgeColor.value = parentEdge.color || '#f1efec';
      if (fParentEdgeStyle) fParentEdgeStyle.value = parentEdge.line_style || parentEdge.lineStyle || 'solid';
      if (fParentEdgeWidth) fParentEdgeWidth.value = String(parentEdge.width || 3);
    }

    selectedType = node.node_type || 'book';
    selectedBadges = new Set(node.badges || []);
    updateTypeButtons();
    updateBadges();

    const coverSrc = node.cover_url || node.cover_image;
    if (coverSrc) {
      coverPreview.innerHTML = `<img src="${coverSrc}" style="width:100%;height:100%;object-fit:cover">`;
    }
  }
  window.openEditModal = openEditModal;

  // ── Type buttons ──────────────────────────────────────
  document.querySelectorAll('.type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedType = btn.dataset.type;
      updateTypeButtons();
      const q = fTitle.value.trim();
      if (q.length >= 3) lookupBooksByTitle(q);
    });
  });

  function updateTypeButtons() {
    document.querySelectorAll('.type-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.type === selectedType);
    });
  }

  // ── Badge picker ──────────────────────────────────────
  document.querySelectorAll('.badge-opt').forEach(badge => {
    badge.addEventListener('click', () => {
      const b = badge.dataset.badge;
      if (selectedBadges.has(b)) selectedBadges.delete(b);
      else selectedBadges.add(b);
      updateBadges();
    });
  });

  function updateBadges() {
    document.querySelectorAll('.badge-opt').forEach(badge => {
      badge.classList.toggle('selected', selectedBadges.has(badge.dataset.badge));
    });
  }

  // ── Cover preview ─────────────────────────────────────
  fCoverUrl.addEventListener('input', () => {
    const url = fCoverUrl.value.trim();
    if (url) coverPreview.innerHTML = `<img src="${url}" style="width:100%;height:100%;object-fit:cover" onerror="this.parentElement.innerHTML='<span>Invalid URL</span>'">`;
    else coverPreview.innerHTML = '<span>No cover</span>';
  });

  fCoverFile.addEventListener('change', () => {
    const file = fCoverFile.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
      coverPreview.innerHTML = `<img src="${e.target.result}" style="width:100%;height:100%;object-fit:cover">`;
    };
    reader.readAsDataURL(file);
  });

  document.getElementById('uploadCoverBtn').addEventListener('click', () => fCoverFile.click());

  // ── Title autocomplete → full metadata populate ──────
  let titleLookupTimer = null;

  fTitle.addEventListener('input', () => {
    const q = fTitle.value.trim();
    if (titleLookupTimer) clearTimeout(titleLookupTimer);
    if (q.length < 3) {
      autocompleteOptions = [];
      if (bookSuggestions) bookSuggestions.innerHTML = '';
      return;
    }

    titleLookupTimer = setTimeout(() => {
      lookupBooksByTitle(q);
    }, 380);
  });

  fTitle.addEventListener('change', () => {
    applySuggestionFromTitle(fTitle.value.trim());
  });

  fTitle.addEventListener('blur', () => {
    applySuggestionFromTitle(fTitle.value.trim(), true);
  });

  async function lookupBooksByTitle(query) {
    try {
      const endpoint = selectedType === 'author' ? '/api/author-search/' : '/api/book-search/';
      const res = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      autocompleteOptions = (data.results || []).slice(0, 8).map(item => ({
        ...item,
        label: `${item.title || ''}, ${item.author || 'Unknown author'}`,
      }));

      if (!bookSuggestions) return;
      bookSuggestions.innerHTML = '';
      autocompleteOptions.forEach(item => {
        const opt = document.createElement('option');
        opt.value = item.label;
        bookSuggestions.appendChild(opt);
      });
    } catch (_) {
      autocompleteOptions = [];
      if (bookSuggestions) bookSuggestions.innerHTML = '';
    }
  }

  function applySuggestionFromTitle(rawValue, allowFirstFallback = false) {
    if (!rawValue || !autocompleteOptions.length) return;
    const normalized = rawValue.toLowerCase();
    let match = autocompleteOptions.find(item => (item.label || '').toLowerCase() === normalized);
    if (!match) {
      match = autocompleteOptions.find(item => (item.title || '').toLowerCase() === normalized);
    }
    if (!match) {
      match = autocompleteOptions.find(item => (item.title || '').toLowerCase().startsWith(normalized));
    }
    if (!match && allowFirstFallback) {
      const first = autocompleteOptions[0];
      const looksLikeAutocompletePick =
        first &&
        first.title &&
        first.title.toLowerCase().startsWith(normalized);
      if (looksLikeAutocompletePick) {
        match = first;
      }
    }
    if (!match) return;
    if (match.node_type) {
      selectedType = match.node_type;
      updateTypeButtons();
    }
    if (match.node_type === 'author') {
      fGenre.value = '';
      fIsbn.value = '';
    }
    populateFromBookInfo(match, { force: true });
    // Normalize field value to clean title after selection.
    fTitle.value = match.title || fTitle.value;
  }

  function populateFromBookInfo(info, options = {}) {
    const force = !!options.force;
    if ((force || !fTitle.value) && info.title) fTitle.value = info.title;
    if ((force || !fAuthor.value) && info.author) fAuthor.value = info.author;
    if ((force || !fGenre.value) && info.genre) fGenre.value = info.genre;
    if ((force || !fYear.value) && info.year) fYear.value = info.year;
    if ((force || !fIsbn.value) && info.isbn) fIsbn.value = info.isbn;
    if ((force || !fNotes.value) && info.description) {
      fNotes.value = info.description.slice(0, 800);
    }
    if ((force || !fCoverUrl.value) && info.cover_url) {
      fCoverUrl.value = info.cover_url;
      coverPreview.innerHTML = `<img src="${info.cover_url}" style="width:100%;height:100%;object-fit:cover">`;
    }
  }

  // ── Auto-fetch cover ──────────────────────────────────
  document.getElementById('fetchCoverBtn').addEventListener('click', async () => {
    const title  = fTitle.value.trim();
    const author = fAuthor.value.trim();
    const isbn   = fIsbn.value.trim();

    if (!title && !isbn) { notify('Enter a title or ISBN first.', 'error'); return; }

    const btn = document.getElementById('fetchCoverBtn');
    btn.textContent = '⏳ Fetching…';
    btn.disabled = true;

    try {
      const params = new URLSearchParams();
      if (isbn) params.set('isbn', isbn);
      if (title) params.set('title', title);
      if (author) params.set('author', author);

      const res = await fetch(`/api/cover/?${params}`);
      const data = await res.json();

      if (data.cover_url) {
        fCoverUrl.value = data.cover_url;
        coverPreview.innerHTML = `<img src="${data.cover_url}" style="width:100%;height:100%;object-fit:cover">`;
      } else {
        btn.textContent = '❌ Not found';
        setTimeout(() => { btn.textContent = '🔍 Auto-fetch'; }, 2000);
      }
    } catch (e) {
      btn.textContent = '❌ Error';
      notify('Cover lookup failed. Please try again.', 'error');
    } finally {
      btn.disabled = false;
      if (btn.textContent === '⏳ Fetching…') btn.textContent = '🔍 Auto-fetch';
    }
  });

  // ── ISBN → auto populate fields ────────────────────────
  fIsbn.addEventListener('blur', async () => {
    const isbn = fIsbn.value.trim();
    if (!isbn || fTitle.value.trim()) return;
    try {
      const res = await fetch(`https://www.googleapis.com/books/v1/volumes?q=isbn:${isbn}&maxResults=1`);
      const data = await res.json();
      const item = (data.items || [])[0];
      if (item) {
        const info = item.volumeInfo;
        const isbn13 = (info.industryIdentifiers || []).find(i => i.type === 'ISBN_13')?.identifier || '';
        const isbn10 = (info.industryIdentifiers || []).find(i => i.type === 'ISBN_10')?.identifier || '';
        populateFromBookInfo({
          title: info.title || '',
          author: (info.authors || []).join(', '),
          genre: (info.categories || [])[0] || '',
          year: (info.publishedDate || '').slice(0, 4),
          isbn: (isbn13 || isbn10 || '').replace(/-/g, ''),
          cover_url: info.imageLinks?.thumbnail ? info.imageLinks.thumbnail.replace('http://', 'https://') : '',
          description: info.description || '',
        });
      }
    } catch (_) {}
  });

  // ── Save ─────────────────────────────────────────────
  document.getElementById('saveBookBtn').addEventListener('click', saveNode);

  async function saveNode() {
    const title = fTitle.value.trim();
    if (!title) { fTitle.focus(); return; }
    const isEditing = !!editingNode;

    const payload = {
      title,
      author:     fAuthor.value.trim(),
      genre:      fGenre.value.trim(),
      year:       fYear.value ? parseInt(fYear.value) : null,
      isbn:       fIsbn.value.trim(),
      rating:     fRating.value ? parseFloat(fRating.value) : null,
      cover_image: fCoverUrl.value.trim(),
      parent:     fParent.value || null,
      node_type:  selectedType,
      notes:      fNotes.value.trim(),
      badges:     Array.from(selectedBadges),
      style: {
        color:  fColor.value,
        glow:   fGlow.value,
        border: fBorder.value,
        parent_edge: {
          color: fParentEdgeColor ? fParentEdgeColor.value : '#74d39f',
          line_style: fParentEdgeStyle ? fParentEdgeStyle.value : 'solid',
          width: Number(fParentEdgeWidth ? fParentEdgeWidth.value : 3),
        },
      },
    };

    const saveBtn = document.getElementById('saveBookBtn');
    saveBtn.textContent = 'Saving…';
    saveBtn.disabled = true;

    try {
      let res;
      if (editingNode) {
        res = await fetch(`/api/nodes/${editingNode.id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch('/api/nodes/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const err = await res.json();
        notify('Could not save node: ' + JSON.stringify(err), 'error');
        return;
      }

      const savedNode = await res.json();
      if (typeof window.upsertTreeNode === 'function') {
        window.upsertTreeNode(savedNode);
      } else if (typeof window.loadTree === 'function') {
        await window.loadTree();
      }
      closeModal();
      notify(isEditing ? 'Node updated instantly.' : 'Node created instantly.', 'success');
    } catch (e) {
      notify('Network error. Please try again.', 'error');
    } finally {
      saveBtn.textContent = 'Save Node';
      saveBtn.disabled = false;
    }
  }

  // ── Delete from modal ─────────────────────────────────
  deleteBtn.addEventListener('click', async () => {
    if (!editingNode) return;
    const ok = typeof window.confirmAction === 'function'
      ? await window.confirmAction(
          `Delete "${editingNode.title}"? Child nodes will be unlinked from it.`,
          'Delete node'
        )
      : confirm(`Delete "${editingNode.title}"? Child nodes will be unlinked.`);
    if (!ok) return;
    try {
      const res = await fetch(`/api/nodes/${editingNode.id}/`, {
        method: 'DELETE',
        headers: { 'X-CSRFToken': getCsrf() },
      });
      if (!res.ok) {
        notify('Failed to delete node.', 'error');
        return;
      }
      if (typeof window.removeTreeNode === 'function') {
        window.removeTreeNode(editingNode.id);
      } else if (typeof window.loadTree === 'function') {
        await window.loadTree();
      }
      closeModal();
      notify('Node deleted.', 'success');
    } catch (e) {
      notify('Failed to delete node.', 'error');
    }
  });

  // ── Close buttons ──────────────────────────────────────
  document.getElementById('closeBookModal').addEventListener('click', closeModal);
  document.getElementById('cancelBookModal').addEventListener('click', closeModal);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });

  // ── Top bar + float bar buttons ───────────────────────
  document.getElementById('addBookBtn')?.addEventListener('click', () => openAddModal());
  document.getElementById('addNodeBtn')?.addEventListener('click', () => openAddModal());
  document.getElementById('floatAddBook')?.addEventListener('click', () => openAddModal());
  document.getElementById('emptyAddBtn')?.addEventListener('click', () => openAddModal());

  // Float bar visibility (show after small delay to simulate "scroll")
  setTimeout(() => {
    document.getElementById('floatBar')?.classList.add('visible');
  }, 3000);

  // ── CSRF helper ───────────────────────────────────────
  function getCsrf() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  // ── Keyboard shortcuts ────────────────────────────────
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeModal();
      document.getElementById('sidebar').classList.remove('open');
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      document.getElementById('searchInput').focus();
    }
  });

  // ── Scroll top ────────────────────────────────────────
  document.getElementById('scrollTopBtn').addEventListener('click', () => {
    window.fitTree && window.fitTree();
  });
})();

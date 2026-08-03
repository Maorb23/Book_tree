(function () {
  'use strict';

  const workspace = document.body;
  const listPanel = document.getElementById('mobileTreeList');
  const listHost = document.getElementById('mobileTreeListNodes');
  const listSearch = document.getElementById('mobileTreeSearch');
  const listCount = document.getElementById('mobileTreeCount');
  const canvas = document.getElementById('treeCanvas');
  const viewButtons = Array.from(document.querySelectorAll('[data-tree-view]'));
  const mobileSwitcher = document.getElementById('mobileTreeSwitcher');
  const desktopSwitcher = document.getElementById('treeSwitcher');
  const storageKey = 'readwoods.tree.mobileView';

  if (!listPanel || !listHost || !canvas || !viewButtons.length) return;

  function storedView() {
    try { return window.localStorage.getItem(storageKey); }
    catch (_) { return null; }
  }

  function rememberView(value) {
    try { window.localStorage.setItem(storageKey, value); }
    catch (_) {}
  }

  function setView(mode, persist = true) {
    const nextMode = mode === 'list' ? 'list' : 'canvas';
    workspace.dataset.treeView = nextMode;
    listPanel.hidden = nextMode !== 'list';
    canvas.setAttribute('aria-hidden', nextMode === 'list' ? 'true' : 'false');
    viewButtons.forEach(button => {
      button.setAttribute('aria-pressed', button.dataset.treeView === nextMode ? 'true' : 'false');
    });
    if (persist) rememberView(nextMode);
    if (nextMode === 'list') renderList();
    else window.requestAnimationFrame(() => window.fitTree?.());
  }

  function normalize(value) {
    return String(value || '').trim().toLowerCase();
  }

  function sortNodes(a, b) {
    const groupA = Number(a.style?.timeline_group);
    const groupB = Number(b.style?.timeline_group);
    if (Number.isFinite(groupA) && Number.isFinite(groupB) && groupA !== groupB) return groupA - groupB;
    const yearA = Number(a.year);
    const yearB = Number(b.year);
    if (Number.isFinite(yearA) && Number.isFinite(yearB) && yearA !== yearB) return yearA - yearB;
    return String(a.title || '').localeCompare(String(b.title || ''));
  }

  function renderList() {
    const nodes = Array.isArray(window.allNodes) ? window.allNodes : [];
    const query = normalize(listSearch?.value);
    const byId = new Map(nodes.map(node => [String(node.id), node]));
    const children = new Map();
    nodes.forEach(node => {
      const parentId = node.parent ? String(node.parent) : '';
      if (!children.has(parentId)) children.set(parentId, []);
      children.get(parentId).push(node);
    });
    children.forEach(rows => rows.sort(sortNodes));

    const visible = new Set();
    if (query) {
      nodes.forEach(node => {
        const searchable = [node.title, node.author, node.genre, node.year, node.node_type]
          .map(normalize).join(' ');
        if (!searchable.includes(query)) return;
        let current = node;
        const ancestors = new Set();
        while (current && !ancestors.has(String(current.id))) {
          const currentId = String(current.id);
          visible.add(currentId);
          ancestors.add(currentId);
          current = current.parent ? byId.get(String(current.parent)) : null;
        }
      });
    } else {
      nodes.forEach(node => visible.add(String(node.id)));
    }

    const roots = nodes
      .filter(node => !node.parent || !byId.has(String(node.parent)))
      .sort(sortNodes);
    const fragment = document.createDocumentFragment();
    const rendered = new Set();

    function appendNode(node, depth) {
      const id = String(node.id);
      if (rendered.has(id) || !visible.has(id)) return;
      rendered.add(id);

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mobile-tree-node';
      button.style.setProperty('--tree-depth', String(Math.min(depth, 4)));

      const imageUrl = node.display_image_url || node.cover_url || node.cover_image || '';
      const visual = imageUrl ? document.createElement('img') : document.createElement('span');
      if (imageUrl) {
        visual.className = 'mobile-tree-node__cover';
        visual.src = imageUrl;
        visual.alt = '';
        visual.loading = 'lazy';
        visual.addEventListener('error', () => {
          const fallback = document.createElement('span');
          fallback.className = 'mobile-tree-node__fallback';
          fallback.textContent = String(node.node_type || 'node').slice(0, 2).toUpperCase();
          visual.replaceWith(fallback);
        }, { once: true });
      } else {
        visual.className = 'mobile-tree-node__fallback';
        visual.textContent = String(node.node_type || 'node').slice(0, 2).toUpperCase();
      }

      const copy = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = node.title || 'Untitled node';
      const meta = document.createElement('small');
      meta.textContent = [node.author, node.genre, node.year].filter(Boolean).join(' · ') || node.node_type || 'Node';
      copy.append(title, meta);

      const childTotal = (children.get(id) || []).length;
      const count = document.createElement('span');
      count.className = 'mobile-tree-node__children';
      count.textContent = childTotal ? String(childTotal) : '';
      count.setAttribute('aria-label', childTotal ? `${childTotal} child nodes` : 'No child nodes');

      button.append(visual, copy, count);
      button.addEventListener('click', () => window.onNodeClick?.(node));
      fragment.appendChild(button);
      (children.get(id) || []).forEach(child => appendNode(child, depth + 1));
    }

    roots.forEach(root => appendNode(root, 0));
    nodes.filter(node => !rendered.has(String(node.id))).sort(sortNodes).forEach(node => appendNode(node, 0));

    listHost.replaceChildren(fragment);
    if (!rendered.size) {
      const empty = document.createElement('p');
      empty.className = 'mobile-tree-list__empty';
      empty.textContent = query ? 'No matching nodes.' : 'This tree has no nodes yet.';
      listHost.appendChild(empty);
    }
    if (listCount) listCount.textContent = `${rendered.size} node${rendered.size === 1 ? '' : 's'}`;
  }

  viewButtons.forEach(button => button.addEventListener('click', () => setView(button.dataset.treeView)));
  listSearch?.addEventListener('input', renderList);
  document.getElementById('mobileFitTree')?.addEventListener('click', () => setView('canvas'));
  document.getElementById('mobileAddNode')?.addEventListener('click', () => window.openAddModal?.());

  document.querySelectorAll('[data-proxy-click]').forEach(button => {
    button.addEventListener('click', () => {
      document.getElementById(button.dataset.proxyClick)?.click();
      button.closest('details')?.removeAttribute('open');
    });
  });

  mobileSwitcher?.addEventListener('change', () => {
    if (!desktopSwitcher) return;
    desktopSwitcher.value = mobileSwitcher.value;
    desktopSwitcher.dispatchEvent(new Event('change', { bubbles: true }));
  });
  desktopSwitcher?.addEventListener('change', () => {
    if (mobileSwitcher) mobileSwitcher.value = desktopSwitcher.value;
  });

  window.addEventListener('readwoods:tree-updated', renderList);
  setView(storedView() || 'canvas', false);
  renderList();
})();

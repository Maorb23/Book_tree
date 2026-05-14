/* ─── TREE VISUALIZATION — D3.js ───────────────────── */
'use strict';

// ── Constants ──────────────────────────────────────────
// Original: NODE_W = 180, NODE_H = 250, H_SEP = 250, V_SEP = 350, NODE_IMG_H = 180
const NODE_W = 250;
const NODE_H = 270;
const NODE_IMG_H = 200; // height of the image area within a node card
const H_SEP = 260;   // horizontal separation
const V_SEP = 360;   // vertical separation

const GENRE_COLORS = {
  'Fantasy':        { bg: '#3b2c6e', glow: '#c5a5ff', link: '#c5a5ff' },
  'Science Fiction':{ bg: '#1d4f7c', glow: '#72c3ff', link: '#72c3ff' },
  'Classic':        { bg: '#2b4e78', glow: '#9ec7ff', link: '#9ec7ff' },
  'Mystery':        { bg: '#69483e', glow: '#ffb98f', link: '#ffb98f' },
  'Thriller':       { bg: '#5c2f48', glow: '#ff9fc6', link: '#ff9fc6' },
  'Romance':        { bg: '#7b3778', glow: '#ffb6ef', link: '#ffb6ef' },
  'Horror':         { bg: '#3f304f', glow: '#bea7e8', link: '#bea7e8' },
  'default':        { bg: '#234a67', glow: '#8fd8ff', link: '#8fd8ff' },
};

const PLACEHOLDER_ICONS = {
  'Fantasy': 'FA',
  'Science Fiction': 'SF',
  'Mystery': 'MY',
  'Classic': 'CL',
  'Thriller': 'TH',
  'Romance': 'RO',
  'Horror': 'HO',
  'default': 'BK',
};

// ── State ───────────────────────────────────────────────
let allNodes = [];
let allEdges = [];
let nodeMap = {};
let collapsedNodes = new Set();
let currentTransform = d3.zoomIdentity;
const edgeDashMap = {
  solid: '',
  dashed: '10,4',
  dotted: '2,6',
  'dash-dot': '12,4,2,4',
};
const EDGE_TYPE_PRESETS = {
  progression: { color: '#74d39f', lineStyle: 'solid', width: 3 },
  genre: { color: '#6ee7b7', lineStyle: 'dotted', width: 3 },
  author: { color: '#c4b5fd', lineStyle: 'dash-dot', width: 3 },
  series: { color: '#fbbf24', lineStyle: 'dashed', width: 4 },
  custom: { color: '#7dd3fc', lineStyle: 'dashed', width: 3 },
};

function showToast(message, level = 'info') {
  const host = document.getElementById('toastHost');
  if (!host) {
    window.alert(message);
    return;
  }

  const labels = {
    success: 'Saved',
    error: 'Action failed',
    info: 'Update',
  };
  const toneClass = level === 'error' ? 'app-toast--error' : (level === 'success' ? 'app-toast--success' : '');
  const lead = labels[level] || labels.info;

  const toastEl = document.createElement('div');
  toastEl.className = `app-toast ${toneClass}`;
  toastEl.role = 'status';
  toastEl.setAttribute('aria-live', 'polite');
  toastEl.setAttribute('aria-atomic', 'true');
  toastEl.innerHTML = `
    <div class="app-toast__msg"><strong>${lead}:</strong> ${message}</div>
    <button type="button" class="app-toast__close" aria-label="Dismiss">x</button>
  `;

  host.appendChild(toastEl);
  const dismiss = () => {
    toastEl.classList.add('app-toast--hide');
    setTimeout(() => toastEl.remove(), 180);
  };
  toastEl.querySelector('.app-toast__close').addEventListener('click', dismiss);
  window.setTimeout(dismiss, level === 'error' ? 5200 : 2800);
}

window.showToast = showToast;

function confirmAction(message, title = 'Please confirm') {
  return new Promise((resolve) => {
    const existing = document.querySelector('.app-confirm');
    if (existing) existing.remove();

    const modalEl = document.createElement('div');
    modalEl.className = 'app-confirm';
    modalEl.setAttribute('role', 'dialog');
    modalEl.setAttribute('aria-modal', 'true');
    modalEl.innerHTML = `
      <div class="app-confirm__dialog">
        <div class="app-confirm__card">
          <div class="app-confirm__header">
            <h5 class="app-confirm__title">${title}</h5>
            <button type="button" class="app-confirm__x" data-role="cancel" aria-label="Close">x</button>
          </div>
          <div class="app-confirm__body">${message}</div>
          <div class="app-confirm__footer">
            <button type="button" class="btn btn--ghost" data-role="cancel">Cancel</button>
            <button type="button" class="btn btn--danger" data-role="confirm">Delete</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);
    document.body.classList.add('confirm-open');

    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
      modalEl.remove();
      document.body.classList.remove('confirm-open');
    };

    modalEl.querySelector('[data-role="confirm"]').addEventListener('click', () => finish(true));
    modalEl.querySelector('[data-role="cancel"]').addEventListener('click', () => finish(false));
    modalEl.addEventListener('click', (event) => {
      if (event.target === modalEl) finish(false);
    });
    window.addEventListener('keydown', function onEsc(event) {
      if (event.key !== 'Escape') return;
      window.removeEventListener('keydown', onEsc);
      finish(false);
    }, { once: true });

  });
}

window.confirmAction = confirmAction;

// ── SVG Setup ───────────────────────────────────────────
const svg = d3.select('#treeCanvas');
const backdropLayer = d3.select('#forestBackdrop');
const linksLayer = d3.select('#linksLayer');
const nodesLayer = d3.select('#nodesLayer');
const bgRect = d3.select('#bgRect');

let W = 0, H = 0;

function getSize() {
  const rect = document.getElementById('treeCanvas').getBoundingClientRect();
  W = rect.width;
  H = rect.height;
  bgRect.attr('width', W).attr('height', H);
  renderForestBackdrop();
}

function renderForestBackdrop() {
  backdropLayer.selectAll('*').remove();
  if (!W || !H) return;

  backdropLayer.append('rect')
    .attr('x', 0)
    .attr('y', 0)
    .attr('width', W)
    .attr('height', H)
    .attr('fill', '#0c120d');

  const silhouettes = [
    { y: H * 0.78, color: '#1b2a1cdd', amp: 30, step: 130, alpha: 0.82 },
    { y: H * 0.84, color: '#24332499', amp: 22, step: 120, alpha: 0.72 },
    { y: H * 0.9, color: '#2b3a2a77', amp: 16, step: 110, alpha: 0.64 },
  ];

  silhouettes.forEach((layer, index) => {
    let d = `M0,${H} L0,${layer.y}`;
    for (let x = 0; x <= W + layer.step; x += layer.step) {
      const wave = Math.sin((x + index * 47) * 0.014) * layer.amp;
      d += ` L${x},${layer.y - wave}`;
    }
    d += ` L${W},${H} Z`;
    backdropLayer.append('path')
      .attr('d', d)
      .attr('fill', layer.color)
      .attr('opacity', layer.alpha);
  });

  for (let i = 0; i < 38; i += 1) {
    const x = (W / 37) * i + Math.sin(i * 1.8) * 14;
    const trunkBaseY = H * 0.92 + (i % 2) * 8;
    const trunkHeight = 26 + (i % 5) * 6;
    backdropLayer.append('line')
      .attr('x1', x)
      .attr('y1', trunkBaseY)
      .attr('x2', x + (i % 3 === 0 ? -3 : 2))
      .attr('y2', trunkBaseY - trunkHeight)
      .attr('stroke', '#3f5a3f')
      .attr('stroke-width', 2)
      .attr('opacity', 0.6);
    backdropLayer.append('circle')
      .attr('cx', x + (i % 3 === 0 ? -3 : 2))
      .attr('cy', trunkBaseY - trunkHeight - 6)
      .attr('r', 8 + (i % 4))
      .attr('fill', '#9fbf8b')
      .attr('opacity', 0.46);
  }
}

// ── Zoom behaviour ──────────────────────────────────────
const zoom = d3.zoom()
  .scaleExtent([0.05, 3])
  .on('zoom', (event) => {
    currentTransform = event.transform;
    linksLayer.attr('transform', event.transform);
    nodesLayer.attr('transform', event.transform);
    updateMinimap();
  });

svg.call(zoom).on('dblclick.zoom', null);

// Zoom buttons
document.getElementById('zoomIn').addEventListener('click', () =>
  svg.transition().duration(300).call(zoom.scaleBy, 1.4));
document.getElementById('zoomOut').addEventListener('click', () =>
  svg.transition().duration(300).call(zoom.scaleBy, 0.7));
document.getElementById('zoomReset').addEventListener('click', fitTree);

// ── Data Loading ────────────────────────────────────────
async function loadTree() {
  document.getElementById('loadingOverlay').style.display = 'flex';
  try {
    const res = await fetch('/api/tree/', {
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
    });
    const data = await res.json();
    allNodes = data.nodes || [];
    allEdges = data.edges || [];
    nodeMap = {};
    allNodes.forEach(n => nodeMap[n.id] = n);
    // Sync public references
    window.allNodes = allNodes;
    window.nodeMap = nodeMap;

    if (allNodes.length === 0) {
      document.getElementById('loadingOverlay').style.display = 'none';
      document.getElementById('emptyState').style.display = 'flex';
      return;
    }

    buildLayout();
    renderTree();
    fitTree();
  } catch (err) {
    console.error('Failed to load tree:', err);
    showToast('Could not load tree data.', 'error');
  } finally {
    document.getElementById('loadingOverlay').style.display = 'none';
  }
}

function renderTreeInstant() {
  buildLayout();
  renderTree();
  updateMinimap();
}

function getEdgeVisualStyle(edge, fallbackColor) {
  const style = edge.style || {};
  const lineStyle = style.line_style || style.lineStyle || edge.line_style || edge.lineStyle || 'dashed';
  const color = style.color || edge.color || fallbackColor;
  const width = Number(style.width || edge.width || 3);
  return { lineStyle, color, width };
}

function getParentEdgeVisualStyle(node, fallbackColor, fallbackWidth) {
  const style = node.style?.parent_edge || node.style?.parentEdge || {};
  const lineStyle = style.line_style || style.lineStyle || 'solid';
  const color = style.color || fallbackColor;
  const width = Number(style.width || fallbackWidth || 3);
  return { lineStyle, color, width };
}

// ── Layout ──────────────────────────────────────────────
function buildLayout() {
  // Build a virtual forest: find roots (no parent)
  const roots = allNodes.filter(n => !n.parent);
  const childMap = {};
  allNodes.forEach(n => {
    childMap[n.id] = allNodes.filter(c => c.parent === n.id);
  });

  // Assign positions using a recursive layout
  // Multiple roots laid out side by side
  // Tree grows UPWARD: roots at ~y=0, leaves at negative y

  const positions = {};
  let totalWidth = 0;
  const rootLayouts = roots.map(r => computeSubtreeLayout(r, childMap, new Set()));

  // Space out root subtrees horizontally
  let xOffset = 0;
  roots.forEach((root, i) => {
    const layout = rootLayouts[i];
    const defaultX = xOffset + layout.width / 2;
    const rootX = root.pos_x != null ? root.pos_x : defaultX;
    const rootY = root.pos_y != null ? root.pos_y : 0;
    assignPositions(root, childMap, positions, rootX, rootY, layout, new Set());
    xOffset += layout.width + H_SEP;
    totalWidth = xOffset;
  });

  // Safety net: if there are cycles or disconnected components, layout remaining nodes as extra roots.
  allNodes.forEach((node) => {
    if (positions[node.id]) return;
    const layout = computeSubtreeLayout(node, childMap, new Set());
    const fallbackX = xOffset + layout.width / 2;
    const rootX = node.pos_x != null ? node.pos_x : fallbackX;
    const rootY = node.pos_y != null ? node.pos_y : 0;
    assignPositions(node, childMap, positions, rootX, rootY, layout, new Set());
    xOffset += layout.width + H_SEP;
  });

  // Store positions on nodes
  allNodes.forEach(n => {
    if (positions[n.id]) {
      n._x = positions[n.id].x;
      n._y = positions[n.id].y;
    }
  });
}

function computeSubtreeLayout(node, childMap, stack) {
  if (stack.has(node.id)) {
    return { width: NODE_W + H_SEP * 0.5 };
  }
  const nextStack = new Set(stack);
  nextStack.add(node.id);

  const children = (childMap[node.id] || []).filter(c => !collapsedNodes.has(node.id) && !nextStack.has(c.id));
  if (children.length === 0) {
    return { width: NODE_W + H_SEP * 0.5 };
  }
  const childLayouts = children.map(c => computeSubtreeLayout(c, childMap, nextStack));
  const width = Math.max(
    childLayouts.reduce((sum, l) => sum + l.width, 0),
    NODE_W + H_SEP * 0.5
  );
  return { width };
}

function assignPositions(node, childMap, positions, cx, cy, layout, stack) {
  if (stack.has(node.id)) return;
  const nextStack = new Set(stack);
  nextStack.add(node.id);

  positions[node.id] = { x: cx, y: cy };
  const children = (childMap[node.id] || []).filter(c => !collapsedNodes.has(node.id) && !nextStack.has(c.id));
  if (children.length === 0) return;

  const childLayouts = children.map(c => computeSubtreeLayout(c, childMap, nextStack));
  const totalW = childLayouts.reduce((s, l) => s + l.width, 0);

  let x = cx - totalW / 2;
  children.forEach((child, i) => {
    const childCx = x + childLayouts[i].width / 2;
    assignPositions(child, childMap, positions, childCx, cy - V_SEP, childLayouts[i], nextStack);
    x += childLayouts[i].width;
  });
}

// ── Rendering ───────────────────────────────────────────
function renderTree() {
  renderLinks();
  renderNodes();
  renderGenreLabels();
}

function getTheme(node) {
  const genre = node.genre || (node.node_type === 'genre' ? node.title : '');
  return GENRE_COLORS[genre] || GENRE_COLORS['default'];
}

// ── Links ────────────────────────────────────────────────
function renderLinks() {
  linksLayer.selectAll('*').remove();

  const visibleIds = new Set(allNodes.filter(n => {
    // visible if not hidden by collapsed ancestor
    return !isHiddenByCollapse(n);
  }).map(n => n.id));

  allNodes.forEach(node => {
    if (!node.parent) return;
    if (!visibleIds.has(node.id) || !visibleIds.has(node.parent)) return;

    const parent = nodeMap[node.parent];
    if (!parent) return;

    const x1 = parent._x, y1 = parent._y - NODE_H * 0.46;
    const x2 = node._x, y2 = node._y + NODE_H * 0.46;
    const depth = getNodeDepth(node);
    const theme = getTheme(node);

    const path = branchPath(x1, y1, x2, y2);
    const trunkWidth = Math.max(2.8, 6.8 - depth * 0.45);
    const branchWidth = Math.max(1.2, trunkWidth * 0.46);
    const parentVisual = getParentEdgeVisualStyle(node, theme.link || theme.glow, branchWidth);

    // Wood-tone trunk layer for a lifelike branch feeling.
    linksLayer.append('path')
      .attr('class', 'tree-link tree-link--wood')
      .attr('d', path)
      .style('stroke', '#4e3929')
      .style('opacity', 0.52)
      .style('stroke-width', trunkWidth);

    linksLayer.append('path')
      .attr('class', 'tree-link')
      .attr('d', path)
      .style('stroke', parentVisual.color)
      .style('opacity', 0.78)
      .style('stroke-width', Math.max(1.3, parentVisual.width))
      .style('stroke-dasharray', edgeDashMap[parentVisual.lineStyle] || edgeDashMap.solid);

    // A soft highlight stripe gives branch depth without breaking zoom behavior.
    linksLayer.append('path')
      .attr('class', 'tree-link tree-link--highlight')
      .attr('d', path)
      .style('stroke', '#d8c6a8')
      .style('opacity', 0.18)
      .style('stroke-width', Math.max(0.8, parentVisual.width * 0.38));

  });

  // Also render explicit edges
  allEdges.forEach(edge => {
    if (edge.id && edge.id.toString().startsWith('parent-')) return; // skip parent edges, already drawn
    const src = nodeMap[edge.source];
    const tgt = nodeMap[edge.target];
    if (!src || !tgt || !visibleIds.has(src.id) || !visibleIds.has(tgt.id)) return;

    const theme = getTheme(src);
    const visual = getEdgeVisualStyle(edge, theme.glow);
    const path = `M${src._x},${src._y} C${src._x},${(src._y + tgt._y)/2} ${tgt._x},${(src._y + tgt._y)/2} ${tgt._x},${tgt._y}`;
    linksLayer.append('path')
      .attr('class', 'tree-link tree-link--custom')
      .attr('d', path)
      .style('stroke', visual.color)
      .style('opacity', 0.82)
      .style('stroke-width', Math.max(1.5, visual.width))
      .style('stroke-dasharray', edgeDashMap[visual.lineStyle] || edgeDashMap.dashed);
  });
}

function branchPath(x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const splitY = y1 - Math.max(Math.abs(dy) * 0.42, 40);
  const swaySeed = Math.sin((x1 + x2 + y1 + y2) * 0.0125);
  const sway = swaySeed * 24;
  const c1x = x1 + dx * 0.14 + sway;
  const c1y = y1 - Math.max(Math.abs(dy) * 0.16, 24);
  const c2x = x1 + dx * 0.32 + sway * 0.7;
  const c2y = splitY;
  const c3x = x1 + dx * 0.74 - sway * 0.4;
  const c3y = splitY;
  const c4x = x2 - dx * 0.1 + sway * 0.2;
  const c4y = y2 + Math.max(Math.abs(dy) * 0.07, 14);
  return [
    `M${x1},${y1}`,
    `C${c1x},${c1y} ${c2x},${c2y} ${x1 + dx * 0.46},${splitY}`,
    `C${c3x},${c3y} ${c4x},${c4y} ${x2},${y2}`,
  ].join(' ');
}

function getNodeDepth(node) {
  let depth = 0;
  let current = nodeMap[node.parent];
  while (current) {
    depth += 1;
    current = nodeMap[current.parent];
  }
  return depth;
}

function isHiddenByCollapse(node) {
  let current = nodeMap[node.parent];
  while (current) {
    if (collapsedNodes.has(current.id)) return true;
    current = nodeMap[current.parent];
  }
  return false;
}

// ── Nodes ─────────────────────────────────────────────
function renderNodes() {
  nodesLayer.selectAll('*').remove();

  const visible = allNodes.filter(n => !isHiddenByCollapse(n));

  visible.forEach(node => {
    if (node._x == null) return;
    const theme = getTheme(node);
    const x = node._x - NODE_W / 2;
    const y = node._y - NODE_H / 2;

    const isGenre = node.node_type === 'genre' || node.node_type === 'series';
    const isCollapsed = collapsedNodes.has(node.id);
    const childCount = allNodes.filter(c => c.parent === node.id).length;

    const g = nodesLayer.append('g')
      .attr('class', 'node-group')
      .attr('data-id', node.id)
      .attr('transform', `translate(${x}, ${y})`)
      .style('opacity', 0)
      .on('mouseenter', () => g.classed('is-hovered', true))
      .on('mouseleave', () => g.classed('is-hovered', false))
      .on('click', (event) => {
        event.stopPropagation();
        onNodeClick(node);
      });

    // Animate in
    g.transition().duration(400).style('opacity', 1);

    // Glow ring
    const glowColor = node.style?.glow || theme.glow;
    g.append('ellipse')
      .attr('cx', NODE_W / 2)
      .attr('cy', NODE_H / 2)
      .attr('rx', NODE_W * 0.6)
      .attr('ry', NODE_H * 0.25)
      .attr('fill', glowColor)
      .style('opacity', 0.12)
      .style('filter', 'blur(16px)');

    // Card background
    const bgColor = node.style?.color || theme.bg;
    const borderColor = node.style?.border || glowColor;

    g.append('rect')
      .attr('class', 'node-card')
      .attr('width', NODE_W)
      .attr('height', NODE_H)
      .attr('rx', 12)
      .attr('fill', bgColor)
      .attr('stroke', borderColor)
      .attr('stroke-width', isGenre ? 2 : 1.5)
      .style('filter', 'url(#shadow)');

    // Cover image area
    const imgH = isGenre ? NODE_H * 0.65 : NODE_IMG_H;
    const coverUrl = node.cover_url || node.cover_image || '';

    if (coverUrl && !isGenre) {
      // Image clip
      const clipId = `clip-${node.id.replace(/-/g, '')}`;
      g.append('defs').append('clipPath')
        .attr('id', clipId)
        .append('rect')
        .attr('width', NODE_W)
        .attr('height', imgH)
        .attr('rx', 12);

      const imgEl = g.append('image')
        .attr('href', coverUrl)
        .attr('width', NODE_W)
        .attr('height', imgH)
        .attr('clip-path', `url(#${clipId})`)
        .attr('preserveAspectRatio', 'xMidYMid slice');

      // Fallback on error
      imgEl.on('error', function() {
        d3.select(this).remove();
        renderPlaceholder(g, node, imgH, bgColor);
      });
    } else {
      renderPlaceholder(g, node, isGenre ? NODE_H * 0.58 : imgH, bgColor);
    }

    // Gradient overlay over image
    if (!isGenre) {
      const gradId = `grad-${node.id.replace(/-/g, '')}`;
      const defs = g.select('defs').empty() ? g.append('defs') : g.select('defs');
      const grad = defs.append('linearGradient')
        .attr('id', gradId)
        .attr('x1', '0%').attr('y1', '0%')
        .attr('x2', '0%').attr('y2', '100%');
      grad.append('stop').attr('offset', '60%').attr('stop-color', 'transparent');
      grad.append('stop').attr('offset', '100%').attr('stop-color', bgColor);

      g.append('rect')
        .attr('width', NODE_W).attr('height', imgH + 2)
        .attr('rx', 12).attr('fill', `url(#${gradId})`);
    }

    // Text area
    const textY = isGenre ? NODE_H * 0.62 : NODE_IMG_H + 8;
    const textAreaH = NODE_H - textY - 6;

    // Title- function to wrap text into multiple lines if needed
    const titleLines = wrapText(node.title, NODE_W - 14, 11);
    titleLines.slice(0, 3).forEach((line, li) => {
      g.append('text')
        .attr('class', 'node-title')
        .attr('x', NODE_W / 2) // Adjust for center alignment
        .attr('y', textY + 14 + li * 22)
        .text(line);
    });

    // Meta line
    const metaParts = [node.author, node.genre].filter(Boolean);
    const metaLine = metaParts.slice(0, 2).join(' · ');
    if (metaLine) {
      g.append('text')
        .attr('class', 'node-meta')
        .attr('x', NODE_W / 2)
        .attr('y', textY + 14 + Math.min(titleLines.length, 2) * 17 + 2)
        .text(truncate(metaLine, 22));
    }

    // Rating stars
    if (node.rating && !isGenre) {
      const starY = textY + 14 + Math.min(titleLines.length, 2) * 14 + 16;
      const stars = '★'.repeat(Math.round(node.rating)).padEnd(5, '☆');
      g.append('text')
        .attr('x', NODE_W / 2)
        .attr('y', starY)
        .attr('text-anchor', 'middle')
        .attr('font-size', '10px')
        .attr('fill', '#bcb8b2')
        .text(stars.slice(0, 5));
    }

    // Badges
    if (node.badges && node.badges.length > 0) {
      node.badges.slice(0, 3).forEach((badge, bi) => {
        g.append('text')
          .attr('class', 'node-badge')
          .attr('x', 8 + bi * 18)
          .attr('y', 20)
          .text(badge);
      });
    }

    // Collapse indicator
    if (childCount > 0) {
      const collapseG = g.append('g')
        .attr('transform', `translate(${NODE_W / 2 - 10}, ${NODE_H - 14})`)
        .style('cursor', 'pointer')
        .on('click', (event) => {
          event.stopPropagation();
          toggleCollapse(node.id);
        });

      collapseG.append('rect')
        .attr('width', 20).attr('height', 14)
        .attr('rx', 7)
        .attr('fill', 'rgba(234, 245, 220, 0.15)')
        .attr('stroke', 'rgba(228, 239, 217, 0.4)')
        .attr('stroke-width', 1);

      collapseG.append('text')
        .attr('x', 10).attr('y', 10)
        .attr('text-anchor', 'middle')
        .attr('fill', '#dfdfdf')
        .attr('font-size', '9px')
        .text(isCollapsed ? `+${childCount}` : '−');
    }

    // Hover bridge keeps the group hovered while moving pointer to side buttons.
    g.append('rect')
      .attr('class', 'node-hover-bridge')
      .attr('x', NODE_W - 6)
      .attr('y', -14)
      .attr('width', 92)
      .attr('height', NODE_H + 28)
      .attr('fill', 'transparent');

    // Hover action buttons
    const actionsG = g.append('g')
      .attr('class', 'node-actions')
      .attr('transform', `translate(${NODE_W + 12}, -4)`);

    actionsG.append('rect')
      .attr('class', 'action-rail')
      .attr('width', 58)
      .attr('height', 146)
      .attr('rx', 12)
      .attr('pointer-events', 'none')
      .attr('fill', 'rgba(149, 156, 163, 0.72)')
      .attr('stroke', 'rgba(193, 206, 193, 0.28)')
      .attr('stroke-width', 1);

    [
      { icon: '✏️', label: 'Edit', action: () => window.openEditModal(node) },
      { icon: '➕', label: 'Add child', action: () => window.openAddChildModal(node) },
      { icon: '🗑️', label: 'Delete', action: () => confirmDelete(node) },
    ].forEach((btn, i) => {
      const btnG = actionsG.append('g')
        .attr('class', 'action-btn')
        .attr('transform', `translate(8, ${8 + i * 46})`)
        .attr('aria-label', btn.label)
        .on('click', (e) => { e.stopPropagation(); btn.action(); });

      btnG.append('rect')
        .attr('width', 42).attr('height', 42).attr('rx', 10)
        .attr('fill', 'rgba(6,13,19,0.92)')
        .attr('stroke', 'rgba(79,195,247,0.45)')
        .attr('stroke-width', 1.2);

      btnG.append('text')
        .attr('x', 21).attr('y', 28)
        .attr('text-anchor', 'middle')
        .attr('font-size', '18px')
        .text(btn.icon);
    });
  });
}

function renderPlaceholder(g, node, imgH, bgColor) {
  g.append('rect')
    .attr('width', NODE_W).attr('height', imgH)
    .attr('rx', 12)
    .attr('fill', bgColor)
    .attr('opacity', 0.6);

  const icon = PLACEHOLDER_ICONS[node.genre] || PLACEHOLDER_ICONS['default'];
  const badgeRadius = Math.max(18, Math.min(34, imgH * 0.16));

  g.append('circle')
    .attr('cx', NODE_W / 2)
    .attr('cy', imgH / 2)
    .attr('r', badgeRadius)
    .attr('fill', 'rgba(15, 24, 34, 0.72)')
    .attr('stroke', 'rgba(232, 243, 255, 0.28)')
    .attr('stroke-width', 1.4);

  g.append('text')
    .attr('x', NODE_W / 2).attr('y', imgH / 2 + 5)
    .attr('text-anchor', 'middle')
    .attr('font-size', '16px')
    .attr('font-weight', 700)
    .attr('letter-spacing', '0.08em')
    .attr('fill', '#edf5ff')
    .text(icon);

  if (node.node_type === 'genre' || node.node_type === 'series') {
    g.append('text')
      .attr('x', NODE_W / 2)
      .attr('y', imgH / 2 + badgeRadius + 16)
      .attr('text-anchor', 'middle')
      .attr('font-size', '9px')
      .attr('font-weight', 600)
      .attr('letter-spacing', '0.06em')
      .attr('fill', 'rgba(234, 243, 255, 0.7)')
      .text('GENRE');
  }

  if (node.year) {
    g.append('text')
      .attr('x', NODE_W / 2).attr('y', imgH / 2 - 10)
      .attr('text-anchor', 'middle')
      .attr('font-size', '12px')
      .attr('fill', 'rgba(200,220,240,0.5)')
      .text(node.year);
  }
}

// ── Genre labels ─────────────────────────────────────
function renderGenreLabels() {
  nodesLayer.selectAll('.genre-label').remove();
  const genres = allNodes.filter(n => n.node_type === 'genre' && !isHiddenByCollapse(n));
  genres.forEach(n => {
    nodesLayer.append('text')
      .attr('class', 'genre-label')
      .attr('x', n._x)
      .attr('y', n._y - NODE_H / 2 - 24)
      .attr('text-anchor', 'middle')
      .text(n.title);
  });
}

// ── Collapse / Expand ────────────────────────────────
function toggleCollapse(nodeId) {
  if (collapsedNodes.has(nodeId)) {
    collapsedNodes.delete(nodeId);
  } else {
    collapsedNodes.add(nodeId);
  }
  buildLayout();
  renderTree();
}

document.getElementById('expandAllBtn').addEventListener('click', () => {
  collapsedNodes.clear();
  buildLayout();
  renderTree();
});
document.getElementById('collapseAllBtn').addEventListener('click', () => {
  const roots = allNodes.filter(n => !n.parent);
  roots.forEach(r => collapsedNodes.add(r.id));
  buildLayout();
  renderTree();
});

// ── Fit tree to view ─────────────────────────────────
function fitTree() {
  getSize();
  if (allNodes.length === 0) return;

  const xs = allNodes.filter(n => n._x != null).map(n => n._x);
  const ys = allNodes.filter(n => n._y != null).map(n => n._y);
  if (!xs.length) return;

  const minX = Math.min(...xs) - NODE_W / 2 - 60;
  const maxX = Math.max(...xs) + NODE_W / 2 + 60;
  const minY = Math.min(...ys) - NODE_H / 2 - 80;
  const maxY = Math.max(...ys) + NODE_H / 2 + 80;

  const treeW = maxX - minX;
  const treeH = maxY - minY;
  const scale = Math.min(W / treeW, H / treeH, 1) * 0.88;

  const tx = (W - treeW * scale) / 2 - minX * scale;
  const ty = (H - treeH * scale) / 2 - minY * scale;

  svg.transition().duration(700).call(
    zoom.transform,
    d3.zoomIdentity.translate(tx, ty).scale(scale)
  );
}

// ── Minimap ──────────────────────────────────────────
const minimapSvg = d3.select('#minimapSvg');
const MINIMAP_W = 178;
const MINIMAP_H = 130;

function updateMinimap() {
  minimapSvg.selectAll('*').remove();
  if (!allNodes.length) return;

  const xs = allNodes.filter(n => n._x != null).map(n => n._x);
  const ys = allNodes.filter(n => n._y != null).map(n => n._y);
  if (!xs.length) return;

  const minX = Math.min(...xs) - NODE_W;
  const maxX = Math.max(...xs) + NODE_W;
  const minY = Math.min(...ys) - NODE_H;
  const maxY = Math.max(...ys) + NODE_H;
  const tW = maxX - minX || 1;
  const tH = maxY - minY || 1;
  const scale = Math.min(MINIMAP_W / tW, MINIMAP_H / tH) * 0.9;

  const offX = (MINIMAP_W - tW * scale) / 2;
  const offY = (MINIMAP_H - tH * scale) / 2;

  // Draw mini links
  allNodes.forEach(node => {
    if (!node.parent || node._x == null) return;
    const parent = nodeMap[node.parent];
    if (!parent || parent._x == null) return;
    const x1 = offX + (parent._x - minX) * scale;
    const y1 = offY + (parent._y - minY) * scale;
    const x2 = offX + (node._x - minX) * scale;
    const y2 = offY + (node._y - minY) * scale;
    minimapSvg.append('line')
      .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
      .attr('stroke', 'rgba(79,195,247,0.3)').attr('stroke-width', 0.8);
  });

  // Draw mini nodes
  allNodes
    .filter(n => n._x != null && !isHiddenByCollapse(n))
    .forEach(node => {
      const theme = getTheme(node);
      const mx = offX + (node._x - minX) * scale;
      const my = offY + (node._y - minY) * scale;
      minimapSvg.append('circle')
        .attr('cx', mx).attr('cy', my)
        .attr('r', node.node_type === 'genre' ? 4 : 2.5)
        .attr('fill', node.style?.glow || theme.glow)
        .attr('opacity', 0.8);
    });

  // Viewport rect
  const vp = document.getElementById('minimapViewport');
  if (!currentTransform) return;
  const vpX = (-currentTransform.x / currentTransform.k - minX) * scale + offX;
  const vpY = (-currentTransform.y / currentTransform.k - minY) * scale + offY;
  const vpW = (W / currentTransform.k) * scale;
  const vpH = (H / currentTransform.k) * scale;

  vp.style.left = `${vpX}px`;
  vp.style.top = `${vpY + 28}px`; // offset for header
  vp.style.width = `${Math.max(vpW, 4)}px`;
  vp.style.height = `${Math.max(vpH, 4)}px`;
}

// ── Search ──────────────────────────────────────────────
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');

searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) { searchResults.classList.remove('active'); return; }

  const matches = allNodes.filter(n =>
    n.title.toLowerCase().includes(q) ||
    (n.author || '').toLowerCase().includes(q) ||
    (n.genre || '').toLowerCase().includes(q)
  ).slice(0, 8);

  if (matches.length === 0) { searchResults.classList.remove('active'); return; }

  matches.forEach(n => {
    const div = document.createElement('div');
    div.className = 'search-item';
    div.innerHTML = `
      <img class="search-item__cover" src="${n.cover_url || n.cover_image || ''}" onerror="this.style.display='none'" loading="lazy">
      <span><strong>${n.title}</strong><br><small style="color:#7bafc8">${n.author || n.genre || ''}</small></span>
    `;
    div.addEventListener('click', () => {
      searchResults.classList.remove('active');
      searchInput.value = '';
      panToNode(n);
    });
    searchResults.appendChild(div);
  });
  searchResults.classList.add('active');
});

document.addEventListener('click', e => {
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.classList.remove('active');
});

function panToNode(node) {
  if (node._x == null) return;
  getSize();
  const scale = Math.min(currentTransform.k, 1.2);
  const tx = W / 2 - node._x * scale;
  const ty = H / 2 - node._y * scale;
  svg.transition().duration(700).call(
    zoom.transform,
    d3.zoomIdentity.translate(tx, ty).scale(scale)
  );
}

// ── Node click → sidebar ────────────────────────────────
function onNodeClick(node) {
  const sidebar = document.getElementById('sidebar');
  const content = document.getElementById('sidebarContent');
  const children = allNodes.filter(c => c.parent === node.id);
  const candidates = allNodes.filter(n => n.id !== node.id);
  const anyNodeOptions = candidates
    .slice()
    .sort((a, b) => a.title.localeCompare(b.title))
    .map(n => `<option value="${n.id}">${n.title}</option>`)
    .join('');
  const branchLinkBlock = candidates.length > 0
    ? `
      <div class="sidebar-section-title">Connect Node To Any Node</div>
      <div class="sidebar-actions">
        <select id="branchTarget_${node.id}" class="sidebar-select">
          <option value="">Select target node…</option>
          ${anyNodeOptions}
        </select>
        <label class="sidebar-section-title" style="margin-top:2px;">Connection Color</label>
        <input id="branchEdgeColor_${node.id}" type="color" value="#7dd3fc" class="sidebar-select" style="height:38px;padding:4px 8px;">
        <label class="sidebar-section-title" style="margin-top:2px;">Connection Style</label>
        <select id="branchEdgeStyle_${node.id}" class="sidebar-select">
          <option value="dashed">Dashed</option>
          <option value="solid">Solid</option>
          <option value="dotted">Dotted</option>
          <option value="dash-dot">Dash Dot</option>
        </select>
        <label class="sidebar-section-title" style="margin-top:2px;">Connection Width</label>
        <select id="branchEdgeWidth_${node.id}" class="sidebar-select">
          <option value="2">Thin</option>
          <option value="3" selected>Normal</option>
          <option value="4">Bold</option>
          <option value="6">Heavy</option>
        </select>
      </div>
    `
    : '';

  const parentOptions = allNodes
    .filter(n => n.id !== node.id)
    .sort((a, b) => a.title.localeCompare(b.title))
    .map(n => `<option value="${n.id}" ${node.parent === n.id ? 'selected' : ''}>${n.title}</option>`)
    .join('');

  const connectedEdges = allEdges.filter(e => {
    if (!e || !e.id) return false;
    if (String(e.id).startsWith('parent-')) return false;
    return e.source === node.id || e.target === node.id;
  });

  const edgeListBlock = connectedEdges.length > 0
    ? `
      <div class="sidebar-section-title">Existing Connections</div>
      <ul class="sidebar-children">
        ${connectedEdges.map(e => {
          const edgeDomId = String(e.id).replace(/[^a-zA-Z0-9_-]/g, '');
          const otherId = e.source === node.id ? e.target : e.source;
          const other = nodeMap[otherId];
          const otherTitle = other ? other.title : otherId;
          const preset = EDGE_TYPE_PRESETS[e.edge_type] || EDGE_TYPE_PRESETS.custom;
          const edgeColor = e.style?.color || preset.color;
          const edgeLineStyle = e.style?.line_style || preset.lineStyle;
          const edgeWidth = Number(e.style?.width || preset.width);
          return `<li class="sidebar-child sidebar-child--connection">
            <div class="connection-row-head">
              <span>${otherTitle} <small style="color:#7bafc8;">(${e.edge_type || 'custom'})</small></span>
            </div>
            <div class="connection-style-grid">
              <label class="sidebar-section-title" style="margin:0;">Color</label>
              <input id="edgeColor_${edgeDomId}" type="color" value="${edgeColor}" class="sidebar-select" style="height:34px;padding:3px 6px;">
              <label class="sidebar-section-title" style="margin:0;">Style</label>
              <select id="edgeStyle_${edgeDomId}" class="sidebar-select">
                <option value="solid" ${edgeLineStyle === 'solid' ? 'selected' : ''}>Solid</option>
                <option value="dashed" ${edgeLineStyle === 'dashed' ? 'selected' : ''}>Dashed</option>
                <option value="dotted" ${edgeLineStyle === 'dotted' ? 'selected' : ''}>Dotted</option>
                <option value="dash-dot" ${edgeLineStyle === 'dash-dot' ? 'selected' : ''}>Dash Dot</option>
              </select>
              <label class="sidebar-section-title" style="margin:0;">Width</label>
              <select id="edgeWidth_${edgeDomId}" class="sidebar-select">
                <option value="2" ${edgeWidth === 2 ? 'selected' : ''}>Thin</option>
                <option value="3" ${edgeWidth === 3 ? 'selected' : ''}>Normal</option>
                <option value="4" ${edgeWidth === 4 ? 'selected' : ''}>Bold</option>
                <option value="6" ${edgeWidth === 6 ? 'selected' : ''}>Heavy</option>
              </select>
            </div>
            <div class="connection-row-actions">
              <button class="btn btn--ghost btn--sm" onclick="updateConnectionStyle('${e.id}','edgeColor_${edgeDomId}','edgeStyle_${edgeDomId}','edgeWidth_${edgeDomId}')">Save</button>
              <button class="btn btn--danger btn--sm" onclick="deleteConnection('${e.id}')">Unlink</button>
            </div>
          </li>`;
        }).join('')}
      </ul>
    `
    : '';

  content.innerHTML = `
    ${(node.cover_url || node.cover_image)
      ? `<img class="sidebar-cover" src="${node.cover_url || node.cover_image}" loading="lazy" onerror="this.style.display='none'">`
      : `<div class="sidebar-cover" style="display:flex;align-items:center;justify-content:center;font-size:3rem;background:var(--bg-dark)">${PLACEHOLDER_ICONS[node.genre]||'📖'}</div>`}
    <div class="sidebar-title">${node.title}</div>
    <div class="sidebar-meta">
      ${[node.author, node.genre, node.year && `(${node.year})`].filter(Boolean).join(' · ')}
      ${node.rating ? ` · ${'★'.repeat(Math.round(node.rating))}` : ''}
    </div>
    ${(node.badges||[]).length > 0
      ? `<div class="sidebar-badges">${node.badges.map(b => `<span class="sidebar-badge">${b}</span>`).join('')}</div>`
      : ''}
    ${node.notes ? `<p class="sidebar-notes">${node.notes}</p>` : ''}
    ${node.description ? `<p class="sidebar-notes">${node.description}</p>` : ''}
    <div class="sidebar-actions">
      <button class="btn btn--ghost" onclick="window.openEditModal(${JSON.stringify(node).replace(/"/g,'&quot;')})">✏️ Edit Node</button>
      <button class="btn btn--ghost" onclick="window.openAddChildModal(${JSON.stringify(node).replace(/"/g,'&quot;')})">➕ Add Child Node</button>
      <button class="btn btn--danger" onclick="confirmDelete(${JSON.stringify(node).replace(/"/g,'&quot;')})">🗑️ Delete</button>
    </div>
    ${branchLinkBlock}
    ${edgeListBlock}
    <div class="sidebar-section-title">Quick Appearance</div>
    <div class="sidebar-actions">
      <label class="sidebar-section-title" style="margin-top:2px;">Node Color</label>
      <input id="quickNodeColor_${node.id}" type="color" value="${node.style?.color || '#1a3a5c'}" class="sidebar-select" style="height:38px;padding:4px 8px;">
      <label class="sidebar-section-title" style="margin-top:2px;">Glow Color</label>
      <input id="quickNodeGlow_${node.id}" type="color" value="${node.style?.glow || '#4fc3f7'}" class="sidebar-select" style="height:38px;padding:4px 8px;">
      <label class="sidebar-section-title" style="margin-top:2px;">Border Color</label>
      <input id="quickNodeBorder_${node.id}" type="color" value="${node.style?.border || '#4fc3f7'}" class="sidebar-select" style="height:38px;padding:4px 8px;">
      <label class="sidebar-section-title" style="margin-top:2px;">Parent Connection Color</label>
      <input id="quickParentEdgeColor_${node.id}" type="color" value="${node.style?.parent_edge?.color || '#74d39f'}" class="sidebar-select" style="height:38px;padding:4px 8px;">
      <label class="sidebar-section-title" style="margin-top:2px;">Parent Connection Style</label>
      <select id="quickParentEdgeStyle_${node.id}" class="sidebar-select">
        <option value="solid" ${(node.style?.parent_edge?.line_style || 'solid') === 'solid' ? 'selected' : ''}>Solid</option>
        <option value="dashed" ${(node.style?.parent_edge?.line_style || '') === 'dashed' ? 'selected' : ''}>Dashed</option>
        <option value="dotted" ${(node.style?.parent_edge?.line_style || '') === 'dotted' ? 'selected' : ''}>Dotted</option>
        <option value="dash-dot" ${(node.style?.parent_edge?.line_style || '') === 'dash-dot' ? 'selected' : ''}>Dash Dot</option>
      </select>
      <label class="sidebar-section-title" style="margin-top:2px;">Parent Connection Width</label>
      <select id="quickParentEdgeWidth_${node.id}" class="sidebar-select">
        <option value="2" ${(Number(node.style?.parent_edge?.width || 3) === 2) ? 'selected' : ''}>Thin</option>
        <option value="3" ${(Number(node.style?.parent_edge?.width || 3) === 3) ? 'selected' : ''}>Normal</option>
        <option value="4" ${(Number(node.style?.parent_edge?.width || 3) === 4) ? 'selected' : ''}>Bold</option>
        <option value="6" ${(Number(node.style?.parent_edge?.width || 3) === 6) ? 'selected' : ''}>Heavy</option>
      </select>
    </div>
    <div class="sidebar-section-title">Change Parent</div>
    <div class="sidebar-actions">
      <select id="parentTarget_${node.id}" class="sidebar-select">
        <option value="">No parent (make root)</option>
        ${parentOptions}
      </select>
    </div>
    ${!node.parent ? `
      <div class="sidebar-section-title">Rearrange Main Branch</div>
      <div class="sidebar-actions">
        <button class="btn btn--ghost" onclick="nudgeRootNode(${JSON.stringify(node).replace(/"/g,'&quot;')}, -180, 0)">⬅ Move Left</button>
        <button class="btn btn--ghost" onclick="nudgeRootNode(${JSON.stringify(node).replace(/"/g,'&quot;')}, 180, 0)">Move Right ➡</button>
      </div>
      <div class="sidebar-actions">
        <button class="btn btn--ghost" onclick="nudgeRootNode(${JSON.stringify(node).replace(/"/g,'&quot;')}, 0, -120)">⬆ Move Up</button>
        <button class="btn btn--ghost" onclick="nudgeRootNode(${JSON.stringify(node).replace(/"/g,'&quot;')}, 0, 120)">Move Down ⬇</button>
      </div>
    ` : ''}
    ${node.parent ? `
      <div class="sidebar-section-title">Main Branch Tools</div>
      <div class="sidebar-actions">
        <button class="btn btn--ghost" onclick="promoteToRoot(${JSON.stringify(node).replace(/"/g,'&quot;')})">⬆ Promote to Main Node</button>
      </div>
    ` : ''}
    ${children.length > 0 ? `
      <div class="sidebar-section-title">Connected (${children.length})</div>
      <ul class="sidebar-children">
        ${children.slice(0, 6).map(c =>
          `<li class="sidebar-child" onclick="panToNode__${c.id.replace(/-/g,'')}">${c.title}</li>`
        ).join('')}
      </ul>
    ` : ''}
    <div class="sidebar-section-title">Apply Changes</div>
    <div class="sidebar-actions">
      <button class="btn btn--primary" onclick="applyNodeChanges('${node.id}')">Apply</button>
    </div>
  `;

  // Wire up child click handlers
  children.slice(0, 6).forEach(c => {
    const li = content.querySelector(`[onclick="panToNode__${c.id.replace(/-/g,'')}"]`);
    if (li) li.addEventListener('click', () => panToNode(c));
  });

  sidebar.classList.add('open');
}

document.getElementById('closeSidebar').addEventListener('click', () => {
  document.getElementById('sidebar').classList.remove('open');
});

// ── Delete ──────────────────────────────────────────────
async function confirmDelete(node) {
  const ok = await confirmAction(
    `Delete "${node.title}"? Child nodes will be unlinked from it.`,
    'Delete node'
  );
  if (!ok) return;
  try {
    const res = await fetch(`/api/nodes/${node.id}/`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrf() },
    });
    if (!res.ok) {
      showToast('Failed to delete node.', 'error');
      return;
    }
    removeTreeNode(node.id);
    document.getElementById('sidebar').classList.remove('open');
    showToast(`Deleted "${node.title}".`, 'success');
  } catch (e) {
    showToast('Failed to delete node.', 'error');
  }
}
window.confirmDelete = confirmDelete;

async function connectNodes(sourceId, selectId, colorId, styleId, widthId) {
  const select = document.getElementById(selectId);
  const targetId = select ? select.value : '';
  if (!targetId) {
    showToast('Please select a target node.', 'error');
    return;
  }

  const sourceNode = nodeMap[sourceId];
  const targetNode = nodeMap[targetId];
  if (!sourceNode || !targetNode) {
    showToast('Could not resolve selected nodes.', 'error');
    return;
  }

  const colorInput = colorId ? document.getElementById(colorId) : null;
  const styleInput = styleId ? document.getElementById(styleId) : null;
  const widthInput = widthId ? document.getElementById(widthId) : null;
  const preset = EDGE_TYPE_PRESETS.custom;
  const edgeStyle = {
    color: colorInput?.value || preset.color,
    line_style: styleInput?.value || preset.lineStyle,
    width: Number(widthInput?.value || preset.width),
  };

  try {
    const edgeType = 'custom';
    const res = await fetch('/api/edges/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({
        source: sourceNode.id,
        target: targetNode.id,
        edge_type: edgeType,
        label: `${sourceNode.title} ↔ ${targetNode.title}`,
        style: edgeStyle,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || 'Failed to connect branches.', 'error');
      return;
    }

    const created = await res.json();
    upsertTreeEdge(created);
    showToast('Connection created.', 'success');
  } catch (_) {
    showToast('Network error while connecting branches.', 'error');
  }
}
window.connectNodes = connectNodes;

async function connectGenreBranch(sourceNode) {
  const allGenreNodes = allNodes.filter(n => n.node_type === 'genre' && n.id !== sourceNode.id);
  if (!allGenreNodes.length) {
    showToast('No other genre nodes found to connect.', 'error');
    return;
  }

  const available = allGenreNodes.slice(0, 12).map(n => n.title).join(', ');
  const typed = window.prompt(`Connect "${sourceNode.title}" to which genre?\nExamples: ${available}`);
  if (!typed) return;

  const targetNode = allGenreNodes.find(n => n.title.toLowerCase() === typed.trim().toLowerCase());
  if (!targetNode) {
    showToast('Could not find a matching genre node by that title.', 'error');
    return;
  }

  try {
    const edgeType = sourceNode.node_type === 'genre' && targetNode.node_type === 'genre' ? 'genre' : 'custom';
    const res = await fetch('/api/edges/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({
        source: sourceNode.id,
        target: targetNode.id,
        edge_type: edgeType,
        label: `${sourceNode.title} → ${targetNode.title}`,
        style: {
          color: '#34d399',
          line_style: 'dashed',
          width: 3,
        },
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.detail || 'Failed to connect branches.', 'error');
      return;
    }

    const created = await res.json();
    upsertTreeEdge(created);
    showToast('Branch connection added.', 'success');
  } catch (_) {
    showToast('Network error while connecting branches.', 'error');
  }
}
window.connectGenreBranch = connectGenreBranch;

async function deleteConnection(edgeId) {
  if (!edgeId) return;
  try {
    const res = await fetch(`/api/edges/${edgeId}/`, {
      method: 'DELETE',
      headers: { 'X-CSRFToken': getCsrf() },
    });
    if (!res.ok) {
      showToast('Failed to delete connection.', 'error');
      return;
    }
    removeTreeEdge(edgeId);
    document.getElementById('sidebar').classList.remove('open');
    showToast('Connection deleted.', 'success');
  } catch (_) {
    showToast('Network error while deleting connection.', 'error');
  }
}
window.deleteConnection = deleteConnection;

async function updateConnectionStyle(edgeId, colorId, styleId, widthId) {
  const edge = allEdges.find(e => String(e.id) === String(edgeId));
  if (!edge) {
    showToast('Connection not found.', 'error');
    return;
  }

  const colorInput = document.getElementById(colorId);
  const styleInput = document.getElementById(styleId);
  const widthInput = document.getElementById(widthId);
  const preset = EDGE_TYPE_PRESETS[edge.edge_type] || EDGE_TYPE_PRESETS.custom;
  const stylePayload = {
    color: colorInput?.value || edge.style?.color || preset.color,
    line_style: styleInput?.value || edge.style?.line_style || preset.lineStyle,
    width: Number(widthInput?.value || edge.style?.width || preset.width),
  };

  try {
    const res = await fetch(`/api/edges/${edgeId}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({ style: stylePayload }),
    });

    if (!res.ok) {
      showToast('Failed to update connection style.', 'error');
      return;
    }

    const savedEdge = await res.json();
    upsertTreeEdge(savedEdge);
    showToast('Connection style updated.', 'success');
  } catch (_) {
    showToast('Network error while updating connection style.', 'error');
  }
}
window.updateConnectionStyle = updateConnectionStyle;

async function applyNodeChanges(nodeId) {
  const node = nodeMap[nodeId];
  if (!node) return;

  const stylePayload = {
    color: document.getElementById(`quickNodeColor_${nodeId}`)?.value || node.style?.color || '#1a3a5c',
    glow: document.getElementById(`quickNodeGlow_${nodeId}`)?.value || node.style?.glow || '#4fc3f7',
    border: document.getElementById(`quickNodeBorder_${nodeId}`)?.value || node.style?.border || '#4fc3f7',
    parent_edge: {
      color: document.getElementById(`quickParentEdgeColor_${nodeId}`)?.value || node.style?.parent_edge?.color || '#74d39f',
      line_style: document.getElementById(`quickParentEdgeStyle_${nodeId}`)?.value || node.style?.parent_edge?.line_style || 'solid',
      width: Number(document.getElementById(`quickParentEdgeWidth_${nodeId}`)?.value || node.style?.parent_edge?.width || 3),
    },
  };

  try {
    const styleRes = await fetch(`/api/nodes/${nodeId}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({ style: stylePayload }),
    });

    if (!styleRes.ok) {
      showToast('Failed to apply style changes.', 'error');
      return;
    }

    const savedNode = await styleRes.json();
    upsertTreeNode(savedNode);

    const parentSelectId = `parentTarget_${nodeId}`;
    const parentSelect = document.getElementById(parentSelectId);
    const selectedParent = parentSelect ? (parentSelect.value || null) : node.parent;
    if (selectedParent !== (node.parent || null)) {
      await reparentNode(nodeId, parentSelectId);
    }

    const branchTargetEl = document.getElementById(`branchTarget_${nodeId}`);
    if (branchTargetEl && branchTargetEl.value) {
      await connectNodes(
        nodeId,
        `branchTarget_${nodeId}`,
        `branchEdgeColor_${nodeId}`,
        `branchEdgeStyle_${nodeId}`,
        `branchEdgeWidth_${nodeId}`,
      );
      branchTargetEl.value = '';
    }

    showToast('Changes applied.', 'success');
  } catch (_) {
    showToast('Could not apply changes right now.', 'error');
  }
}
window.applyNodeChanges = applyNodeChanges;

async function reparentNode(nodeId, selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;
  const parentId = select.value || null;

  try {
    const res = await fetch(`/api/nodes/${nodeId}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({ parent: parentId }),
    });

    if (!res.ok) {
      const err = await res.json();
      showToast(err.parent?.[0] || err.detail || 'Failed to move node under selected parent.', 'error');
      return;
    }

    const node = nodeMap[nodeId];
    if (node) {
      node.parent = parentId;
      renderTreeInstant();
    }
    document.getElementById('sidebar').classList.remove('open');
    showToast('Parent updated instantly.', 'success');
  } catch (_) {
    showToast('Network error while changing parent.', 'error');
  }
}
window.reparentNode = reparentNode;

async function nudgeRootNode(node, dx, dy) {
  const localNode = nodeMap[node.id] || node;
  const baseX = Number(localNode.pos_x != null ? localNode.pos_x : localNode._x || 0);
  const baseY = Number(localNode.pos_y != null ? localNode.pos_y : localNode._y || 0);
  const payload = {
    pos_x: baseX + dx,
    pos_y: baseY + dy,
  };

  try {
    const res = await fetch(`/api/nodes/${node.id}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      showToast('Failed to move this main branch.', 'error');
      return;
    }

    if (localNode) {
      localNode.pos_x = payload.pos_x;
      localNode.pos_y = payload.pos_y;
      renderTreeInstant();
    } else {
      buildLayout();
      renderTree();
      updateMinimap();
    }
  } catch (_) {
    showToast('Network error while moving branch.', 'error');
  }
}
window.nudgeRootNode = nudgeRootNode;

async function promoteToRoot(node) {
  try {
    const res = await fetch(`/api/nodes/${node.id}/`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      body: JSON.stringify({ parent: null }),
    });

    if (!res.ok) {
      showToast('Failed to promote node to main branch.', 'error');
      return;
    }

    const localNode = nodeMap[node.id];
    if (localNode) {
      localNode.parent = null;
      renderTreeInstant();
    }
    showToast('Node promoted to main branch.', 'success');
  } catch (_) {
    showToast('Network error while promoting node.', 'error');
  }
}
window.promoteToRoot = promoteToRoot;

function getCsrf() {
  const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
  return cookie ? cookie.split('=')[1] : '';
}

function upsertTreeNode(rawNode) {
  if (!rawNode || !rawNode.id) return null;
  const node = {
    ...rawNode,
    id: String(rawNode.id),
    parent: rawNode.parent ? String(rawNode.parent) : null,
  };
  const idx = allNodes.findIndex(n => n.id === node.id);
  if (idx >= 0) {
    allNodes[idx] = { ...allNodes[idx], ...node };
  } else {
    allNodes.push(node);
  }
  nodeMap[node.id] = idx >= 0 ? allNodes[idx] : node;
  window.allNodes = allNodes;
  window.nodeMap = nodeMap;
  renderTreeInstant();
  return nodeMap[node.id];
}

function removeTreeNode(nodeId) {
  const id = String(nodeId);
  allNodes = allNodes.filter(node => node.id !== id);
  allNodes.forEach((node) => {
    if (String(node.parent || '') === id) {
      node.parent = null;
    }
  });
  allEdges = allEdges.filter((edge) => {
    if (!edge) return false;
    const sourceId = String(edge.source || '');
    const targetId = String(edge.target || '');
    return sourceId !== id && targetId !== id;
  });
  delete nodeMap[id];
  nodeMap = {};
  allNodes.forEach((node) => { nodeMap[node.id] = node; });
  window.allNodes = allNodes;
  window.nodeMap = nodeMap;
  renderTreeInstant();
}

function upsertTreeEdge(rawEdge) {
  if (!rawEdge || !rawEdge.id) return;
  const edge = {
    ...rawEdge,
    id: String(rawEdge.id),
    source: String(rawEdge.source),
    target: String(rawEdge.target),
  };
  const idx = allEdges.findIndex(e => String(e.id) === edge.id);
  if (idx >= 0) {
    allEdges[idx] = { ...allEdges[idx], ...edge };
  } else {
    allEdges.push(edge);
  }
  window.allNodes = allNodes;
  window.nodeMap = nodeMap;
  renderTreeInstant();
}

function removeTreeEdge(edgeId) {
  const id = String(edgeId);
  allEdges = allEdges.filter(edge => String(edge.id) !== id);
  window.allNodes = allNodes;
  window.nodeMap = nodeMap;
  renderTreeInstant();
}

// ── Helpers ─────────────────────────────────────────────
function wrapText(text, maxWidth, fontSize) {
  const avgCharW = fontSize * 0.9; // rough estimate
  const maxChars = Math.floor(maxWidth / avgCharW);
  const words = text.split(' ');
  const lines = [];
  let current = '';
  words.forEach(word => {
    if ((current + ' ' + word).trim().length <= maxChars) {
      current = (current + ' ' + word).trim();
    } else {
      if (current) lines.push(current);
      current = word;
    }
  });
  if (current) lines.push(current);
  return lines;
}

function truncate(str, max) {
  return str.length > max ? str.slice(0, max - 1) + '…' : str;
}

// ── Resize handler ──────────────────────────────────────
window.addEventListener('resize', () => {
  getSize();
  bgRect.attr('width', W).attr('height', H);
  updateMinimap();
});

// ── Expose public API for modal ──────────────────────────
window.loadTree = loadTree;
window.panToNode = panToNode;
window.getTheme = getTheme;
window.fitTree = fitTree;
window.renderTreeInstant = renderTreeInstant;
window.upsertTreeNode = upsertTreeNode;
window.removeTreeNode = removeTreeNode;
window.upsertTreeEdge = upsertTreeEdge;
window.removeTreeEdge = removeTreeEdge;
window.allNodes = allNodes;
window.nodeMap = nodeMap;

// ── Init ────────────────────────────────────────────────
getSize();
loadTree();

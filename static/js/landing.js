/* ─── LANDING PAGE JavaScript ───────────────────────── */
(function () {
  'use strict';

  // ── Floating book particles in hero ──
  const COLORS = ['#1c2a1d','#2d3a2b','#3a2f24','#2a1d14','#1f2418','#2f3a28'];
  const container = document.getElementById('heroBooks');

  if (container) {
    ['left', 'right'].forEach((side) => {
      Array.from({ length: 7 }).forEach((_, i) => {
        const el = document.createElement('div');
        el.className = `hero-book hero-book--leaf hero-book--${side}`;
        const rot = side === 'left' ? -5 : 5;
        const driftRot = rot * -1;
        el.style.cssText = `
          ${side}:-20px;
          top:${i * 82 - 8}px;
          --leaf-color:${COLORS[(i + (side === 'right' ? 2 : 0)) % COLORS.length]};
          --rot:${rot}deg;
          --drift-rot:${driftRot}deg;
          animation-delay:${i * 0.22}s;
          animation-duration:${7 + (i % 3)}s;
        `;
        container.appendChild(el);
      });
    });
  }

  // ── Mini tree canvas preview ──
  const canvas = document.getElementById('miniTree');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');

  function roundedRectPath(ctx, x, y, w, h, r, corners) {
    const radius = Math.min(r, w / 2, h / 2);
    const c = Object.assign({ tl: true, tr: true, br: true, bl: true }, corners || {});
    ctx.beginPath();
    ctx.moveTo(x + (c.tl ? radius : 0), y);
    ctx.lineTo(x + w - (c.tr ? radius : 0), y);
    if (c.tr) ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    else ctx.lineTo(x + w, y);
    ctx.lineTo(x + w, y + h - (c.br ? radius : 0));
    if (c.br) ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    else ctx.lineTo(x + w, y + h);
    ctx.lineTo(x + (c.bl ? radius : 0), y + h);
    if (c.bl) ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    else ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + (c.tl ? radius : 0));
    if (c.tl) ctx.quadraticCurveTo(x, y, x + radius, y);
    else ctx.lineTo(x, y);
    ctx.closePath();
  }

  function resize() {
    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;
  }
  resize();
  window.addEventListener('resize', () => { resize(); drawTree(); });

  // Simple animated tree demo
  let tick = 0;
  const NODES = [
    { title: 'Fantasy', author: 'Genre', x: 0.52, y: 0.14, w: 160, h: 88, tone: '#2a3a2a', parent: null },
    { title: 'Sci-Fi', author: 'Genre', x: 0.26, y: 0.16, w: 150, h: 84, tone: '#263228', parent: null },
    { title: 'The Hobbit', author: 'J.R.R. Tolkien', x: 0.45, y: 0.38, w: 150, h: 86, tone: '#31452f', parent: 0 },
    { title: 'Mistborn', author: 'B. Sanderson', x: 0.60, y: 0.44, w: 140, h: 82, tone: '#2a3d30', parent: 0 },
    { title: 'Tolkien', author: 'Author', x: 0.52, y: 0.64, w: 130, h: 78, tone: '#223326', parent: 2 },
    { title: 'Dune', author: 'Frank Herbert', x: 0.22, y: 0.40, w: 140, h: 82, tone: '#2c3b2b', parent: 1 },
    { title: 'Foundation', author: 'I. Asimov', x: 0.32, y: 0.56, w: 136, h: 80, tone: '#243426', parent: 1 },
  ];

  function drawTree() {
    if (!canvas.width) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const W = canvas.width, H = canvas.height;

    // Forest backdrop gradient
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#0c120d');
    bg.addColorStop(0.55, '#101812');
    bg.addColorStop(1, '#0a0f0b');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    const silhouettes = [
      { y: H * 0.76, color: 'rgba(27, 42, 28, 0.8)', amp: 16, step: 120 },
      { y: H * 0.84, color: 'rgba(35, 50, 33, 0.68)', amp: 12, step: 110 },
      { y: H * 0.92, color: 'rgba(41, 57, 37, 0.55)', amp: 10, step: 100 },
    ];
    silhouettes.forEach((layer, index) => {
      ctx.beginPath();
      ctx.moveTo(0, H);
      ctx.lineTo(0, layer.y);
      for (let x = 0; x <= W + layer.step; x += layer.step) {
        const wave = Math.sin((x + index * 33) * 0.015) * layer.amp;
        ctx.lineTo(x, layer.y - wave);
      }
      ctx.lineTo(W, H);
      ctx.closePath();
      ctx.fillStyle = layer.color;
      ctx.fill();
    });

    // Draw edges
    NODES.forEach((n) => {
      if (n.parent !== null) {
        const p = NODES[n.parent];
        const x1 = p.x * W, y1 = p.y * H;
        const x2 = n.x * W, y2 = n.y * H;
        const mid = (y1 + y2) / 2;

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.bezierCurveTo(x1, mid, x2, mid, x2, y2);
        ctx.strokeStyle = 'rgba(143, 193, 146, 0.4)';
        ctx.lineWidth = 1.4;
        ctx.stroke();
      }
    });

    // Draw card nodes
    NODES.forEach((n, i) => {
      const x = n.x * W;
      const y = n.y * H;
      const pulse = Math.sin(tick * 0.02 + i * 0.7) * 2;
      const w = n.w + pulse;
      const h = n.h + pulse;
      const rx = 10;
      const ry = 10;

      ctx.save();
      ctx.translate(x - w / 2, y - h / 2);

      ctx.fillStyle = n.tone;
      ctx.strokeStyle = 'rgba(128, 175, 132, 0.45)';
      ctx.lineWidth = 1.2;
      roundedRectPath(ctx, 0, 0, w, h, rx);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = 'rgba(18, 24, 18, 0.75)';
      roundedRectPath(ctx, 0, 0, w, h * 0.52, rx, { tl: true, tr: true, br: false, bl: false });
      ctx.fill();

      ctx.fillStyle = 'rgba(217, 231, 214, 0.9)';
      ctx.font = '12px "Source Sans 3", sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillText(n.title, 12, h * 0.58);

      ctx.fillStyle = 'rgba(167, 185, 166, 0.9)';
      ctx.font = '10px "Source Sans 3", sans-serif';
      ctx.fillText(n.author, 12, h * 0.72);

      ctx.restore();
    });
  }

  function animate() {
    tick++;
    drawTree();
    requestAnimationFrame(animate);
  }
  animate();

  // ── Scroll-driven entrance animations ──
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) e.target.classList.add('aos-in');
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.content-card, .stat, .preview__canvas').forEach(el => {
    el.setAttribute('data-aos', '');
    observer.observe(el);
  });
})();

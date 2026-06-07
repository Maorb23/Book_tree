/* ─── BOOK PAGE JavaScript ─────────────────────────── */
(function () {
  'use strict';

  const page = document.querySelector('.book-page');
  if (!page) return;

  const titleSeed = (page.dataset.title || '').trim();
  const authorSeed = (page.dataset.author || '').trim();
  const isbnSeed = (page.dataset.isbn || '').trim();
  const genreSeed = (page.dataset.genre || '').trim();
  const yearSeed = (page.dataset.year || '').trim();
  const coverSeed = (page.dataset.coverUrl || '').trim();
  const descriptionSeed = (page.dataset.description || '').trim();

  const queryParts = [];
  if (titleSeed) queryParts.push(titleSeed);
  if (authorSeed) queryParts.push(authorSeed);
  const titleAuthorQuery = queryParts.join(' ').trim();
  const queryCandidates = [
    isbnSeed,
    titleAuthorQuery,
    titleSeed,
  ].filter(Boolean).filter((value, index, values) => values.indexOf(value) === index);
  const query = queryCandidates[0] || '';

  const titleEl = document.getElementById('bookTitle');
  const authorEl = document.getElementById('bookAuthor');
  const coverEl = document.getElementById('bookCover');
  const infoEl = document.getElementById('bookInfo');
  const descEl = document.getElementById('bookDescription');
  const metaList = document.getElementById('bookMetaList');
  const searchLink = document.getElementById('bookSearchLink');
  const criticReviewsEl = document.getElementById('criticReviews');
  const addReviewBtn = document.getElementById('addBookReview');
  const reviewBox = document.getElementById('bookReviewBox');
  let currentInfo = null;
  let currentReview = null;

  function setSearchLink(q) {
    const encoded = encodeURIComponent(q || 'books');
    searchLink.href = `https://www.google.com/search?tbm=bks&q=${encoded}`;
  }

  function setCover(url) {
    if (!url) {
      coverEl.innerHTML = '<span>No cover available</span>';
      return;
    }
    coverEl.innerHTML = `<img src="${url}" alt="Book cover">`;
  }

  function setInfoChips(info) {
    infoEl.innerHTML = '';
    const chips = [];
    if (info.genre) chips.push(info.genre);
    if (info.year) chips.push(info.year);
    if (info.isbn) chips.push(`ISBN ${info.isbn}`);
    if (info.average_rating) {
      const count = info.ratings_count ? ` (${info.ratings_count})` : '';
      chips.push(`Google Books ${info.average_rating}/5${count}`);
    }
    chips.forEach(text => {
      const span = document.createElement('span');
      span.textContent = text;
      infoEl.appendChild(span);
    });
  }

  function setMetaList(info) {
    metaList.innerHTML = '';
    const rows = [
      ['Title', info.title],
      ['Author', info.author],
      ['Genre', info.genre],
      ['Year', info.year],
      ['ISBN', info.isbn],
      ['Google Books rating', info.average_rating ? `${info.average_rating}/5` : ''],
      ['Google Books ratings count', info.ratings_count],
    ];
    rows.forEach(([label, value]) => {
      if (!value) return;
      const li = document.createElement('li');
      li.textContent = `${label}: ${value}`;
      metaList.appendChild(li);
    });
  }

  function renderReview(review) {
    currentReview = review || null;
    if (!reviewBox) return;
    if (!review) {
      reviewBox.hidden = true;
      if (addReviewBtn) addReviewBtn.textContent = 'Add a Review';
      return;
    }
    reviewBox.hidden = false;
    reviewBox.innerHTML = `
      <strong>Your Review${review.rating ? ` · ${'★'.repeat(Math.round(Number(review.rating)))}` : ''}</strong>
      <p>${escapeHtml(review.review)}</p>
      <button class="btn btn--ghost btn--sm" type="button" id="editBookReview">Edit Review</button>
    `;
    if (addReviewBtn) addReviewBtn.textContent = 'Edit Review';
    document.getElementById('editBookReview')?.addEventListener('click', openReviewPrompt);
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

  async function loadReview(info) {
    if (!reviewBox) return;
    const params = new URLSearchParams();
    if (info.isbn) params.set('isbn', info.isbn);
    params.set('title', info.title || titleSeed || '');
    params.set('author', info.author || authorSeed || '');
    try {
      const res = await fetch(`/api/book-reviews/?${params.toString()}`);
      const data = await res.json();
      renderReview((data || [])[0] || null);
    } catch (_) {
      renderReview(null);
    }
  }

  function renderCriticReviews(results, detail) {
    if (!criticReviewsEl) return;
    if (!results || !results.length) {
      criticReviewsEl.innerHTML = `<p class="critic-review-empty">${escapeHtml(detail || 'No critic reviews found for this book yet.')}</p>`;
      return;
    }
    criticReviewsEl.innerHTML = `
      <div class="critic-review-list">
        ${results.map(review => `
          <article class="critic-review">
            <span>${escapeHtml(review.source || 'Critic review')}${review.published_date ? ` · ${escapeHtml(review.published_date)}` : ''}</span>
            <strong>${escapeHtml(review.review_title || review.book_title || 'Review')}</strong>
            ${review.reviewer ? `<span>${escapeHtml(review.reviewer)}</span>` : ''}
            ${review.summary ? `<p>${escapeHtml(review.summary)}</p>` : ''}
            <a class="btn btn--ghost btn--sm" href="${escapeHtml(review.url)}" target="_blank" rel="noopener">Read review</a>
          </article>
        `).join('')}
      </div>
    `;
  }

  async function loadCriticReviews(info) {
    if (!criticReviewsEl) return;
    criticReviewsEl.textContent = 'Looking for critic reviews...';
    const params = new URLSearchParams();
    if (info.title) params.set('title', info.title);
    if (info.author) params.set('author', info.author);
    if (info.isbn) params.set('isbn', info.isbn);
    try {
      const res = await fetch(`/api/critic-reviews/?${params.toString()}`);
      const data = await res.json();
      renderCriticReviews(data.results || [], data.detail || '');
    } catch (_) {
      renderCriticReviews([], 'Critic reviews are unavailable right now.');
    }
  }

  async function openReviewPrompt() {
    const info = currentInfo || {
      title: titleSeed,
      author: authorSeed,
      isbn: isbnSeed,
      cover_url: coverSeed,
    };
    const text = window.prompt(`Review "${info.title || 'this book'}"`, currentReview?.review || '');
    if (text === null) return;
    const review = text.trim();
    if (!review) return;
    const res = await fetch('/api/book-reviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        title: info.title || titleSeed || '',
        author: info.author || authorSeed || '',
        isbn: info.isbn || isbnSeed || '',
        cover_image: info.cover_url || coverSeed || '',
        review,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) renderReview(data);
  }

  function getCsrf() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  addReviewBtn?.addEventListener('click', openReviewPrompt);

  async function loadBook() {
    if (!query) {
      titleEl.textContent = 'Book details';
      authorEl.textContent = 'Provide a title to search.';
      descEl.textContent = 'No book query was provided.';
      setSearchLink('books');
      return;
    }

    titleEl.textContent = 'Searching...';
    authorEl.textContent = '';
    descEl.textContent = 'Looking for this book in the library.';
    setCover(coverSeed);
    setInfoChips({ genre: genreSeed, year: yearSeed, isbn: isbnSeed });
    setSearchLink(query);

    try {
      let result = null;
      for (const candidate of queryCandidates) {
        const response = await fetch(`/api/book-search/?q=${encodeURIComponent(candidate)}`);
        const data = await response.json();
        result = (data.results || [])[0] || null;
        if (result) break;
      }

      if (!result) {
        titleEl.textContent = titleSeed || 'Book not found';
        authorEl.textContent = authorSeed || 'Try a different search.';
        descEl.textContent = 'We could not find details for this book yet.';
        setCover('');
        setInfoChips({});
        setMetaList({});
        return;
      }

      const info = {
        title: result.title || titleSeed || 'Untitled',
        author: result.author || authorSeed || 'Unknown author',
        genre: result.genre || genreSeed || '',
        year: result.year || yearSeed || '',
        isbn: result.isbn || isbnSeed || '',
        description: result.description || descriptionSeed || 'No description available.',
        cover_url: result.cover_url || coverSeed || '',
        average_rating: result.average_rating || '',
        ratings_count: result.ratings_count || '',
      };
      currentInfo = info;

      titleEl.textContent = info.title;
      authorEl.textContent = info.author;
      descEl.textContent = info.description;
      setCover(info.cover_url);
      setInfoChips(info);
      setMetaList(info);
      setSearchLink(`${info.title} ${info.author}`);
      loadReview(info);
      loadCriticReviews(info);
    } catch (err) {
      titleEl.textContent = titleSeed || 'Book details';
      authorEl.textContent = authorSeed || 'Search unavailable';
      descEl.textContent = 'We could not reach the book service.';
      setCover('');
      setInfoChips({});
      setMetaList({});
      loadReview({ title: titleSeed, author: authorSeed, isbn: isbnSeed, cover_url: coverSeed });
      loadCriticReviews({ title: titleSeed, author: authorSeed, isbn: isbnSeed });
    }
  }

  loadBook();
})();

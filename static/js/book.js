/* BOOK PAGE JavaScript */
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
  const importedBookSeed = (page.dataset.importedBook || '').trim();

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
  const descToggle = document.getElementById('bookDescriptionToggle');
  const metaList = document.getElementById('bookMetaList');
  const searchLink = document.getElementById('bookSearchLink');
  const guardianArticlesEl = document.getElementById('criticReviews');
  const communityReviewsEl = document.getElementById('communityReviews');
  const shelfTagsEl = document.getElementById('bookShelfTags');
  const addReviewBtn = document.getElementById('addBookReview');
  const reviewBox = document.getElementById('bookReviewBox');
  const reviewForm = document.getElementById('bookReviewForm');
  const reviewText = document.getElementById('bookReviewText');
  const reviewFormTitle = document.getElementById('reviewFormTitle');
  const reviewFormStatus = document.getElementById('reviewFormStatus');
  const cancelReviewBtn = document.getElementById('cancelBookReview');
  const ratingButtons = Array.from(document.querySelectorAll('#bookReviewRating button'));

  let currentInfo = null;
  let currentReview = null;
  let selectedRating = 0;

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  function getCsrf() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  function setSearchLink(q) {
    const encoded = encodeURIComponent(q || 'books');
    searchLink.href = `https://www.google.com/search?tbm=bks&q=${encoded}`;
  }

  function setCover(url, info = null) {
    if (!url) {
      coverEl.innerHTML = '<span>No cover available</span>';
      fetchFallbackCover(info);
      return;
    }

    coverEl.innerHTML = `<img src="${escapeHtml(url)}" alt="Book cover">`;
    const img = coverEl.querySelector('img');
    img?.addEventListener('error', () => {
      coverEl.innerHTML = '<span>No cover available</span>';
      fetchFallbackCover(info);
    }, { once: true });
    if (!importedBookSeed && url.includes('covers.openlibrary.org') && info?.title) {
      fetchFallbackCover(info);
    }
  }

  async function fetchFallbackCover(info) {
    if (!info || !info.title) return;
    try {
      const params = new URLSearchParams({ title: info.title });
      if (info.author) params.set('author', info.author);
      if (info.isbn) params.set('isbn', info.isbn);
      const res = await fetch(`/api/cover/?${params.toString()}`);
      const data = await res.json();
      if (data.cover_url) {
        coverEl.innerHTML = `<img src="${escapeHtml(data.cover_url)}" alt="Book cover">`;
      }
    } catch (_) {
      // Keep the fallback label.
    }
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

  function setDescription(text) {
    if (!descEl) return;
    const description = text || 'No description available.';
    descEl.textContent = description;
    descEl.classList.add('is-clamped');
    if (!descToggle) return;
    const shouldToggle = description.length > 260;
    descToggle.hidden = !shouldToggle;
    descToggle.textContent = 'Read more';
  }

  descToggle?.addEventListener('click', () => {
    const expanded = !descEl.classList.toggle('is-clamped');
    descToggle.textContent = expanded ? 'Show less' : 'Read more';
  });

  function starText(value) {
    const count = Math.max(0, Math.min(5, Math.round(Number(value) || 0)));
    return '&#9733;'.repeat(count);
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
      <strong>Your Review${review.rating ? ` <span>${starText(review.rating)}</span>` : ''}</strong>
      <p>${escapeHtml(review.review)}</p>
      <button class="btn btn--ghost btn--sm" type="button" id="editBookReview">Edit Review</button>
    `;
    if (addReviewBtn) addReviewBtn.textContent = 'Edit Review';
    document.getElementById('editBookReview')?.addEventListener('click', openReviewForm);
  }

  async function loadReview(info) {
    if (!reviewBox) return;
    const params = new URLSearchParams();
    if (importedBookSeed) params.set('imported_book', importedBookSeed);
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

  function renderCommunityReviews(reviews) {
    if (!communityReviewsEl) return;
    if (!reviews || !reviews.length) {
      communityReviewsEl.innerHTML = '<p class="community-review-empty">No community reviews... yet. The forest is suspiciously quiet.</p>';
      return;
    }
    communityReviewsEl.innerHTML = `
      <div class="community-review-list">
        ${reviews.map(review => `
          <article class="community-review">
            <div>
              <strong>${escapeHtml(review.username || 'Reader')}</strong>
              ${review.rating ? `<span>${starText(review.rating)}</span>` : ''}
            </div>
            <p>${escapeHtml(review.review)}</p>
          </article>
        `).join('')}
      </div>
    `;
  }

  async function loadCommunityReviews(info) {
    if (!communityReviewsEl) return;
    communityReviewsEl.textContent = 'Checking the reading room...';
    const params = new URLSearchParams();
    if (info.title) params.set('title', info.title);
    if (info.author) params.set('author', info.author);
    if (info.isbn) params.set('isbn', info.isbn);
    try {
      const res = await fetch(`/api/book-community-reviews/?${params.toString()}`);
      const data = await res.json();
      renderCommunityReviews(data || []);
    } catch (_) {
      renderCommunityReviews([]);
    }
  }

  function renderShelfTags(shelves) {
    if (!shelfTagsEl) return;
    if (!shelves || !shelves.length) {
      shelfTagsEl.hidden = true;
      shelfTagsEl.innerHTML = '';
      return;
    }
    shelfTagsEl.hidden = false;
    shelfTagsEl.innerHTML = shelves.map(shelf => `<span>${escapeHtml(shelf.label)}</span>`).join('');
  }

  async function loadShelves(info) {
    if (!shelfTagsEl || !addReviewBtn) return;
    const params = new URLSearchParams();
    if (importedBookSeed) params.set('imported_book', importedBookSeed);
    if (info.title) params.set('title', info.title);
    if (info.author) params.set('author', info.author);
    if (info.isbn) params.set('isbn', info.isbn);
    try {
      const res = await fetch(`/api/book-shelves/?${params.toString()}`);
      if (!res.ok) return;
      const data = await res.json();
      renderShelfTags(data.shelves || []);
    } catch (_) {
      renderShelfTags([]);
    }
  }

  function renderGuardianArticles(results, detail) {
    if (!guardianArticlesEl) return;
    if (!results || !results.length) {
      guardianArticlesEl.innerHTML = `<p class="critic-review-empty">${escapeHtml(detail || 'No Guardian article matches found for this book yet.')}</p>`;
      return;
    }
    guardianArticlesEl.innerHTML = `
      <div class="critic-review-list">
        ${results.map(article => `
          <article class="critic-review">
            <span>${escapeHtml(article.source || 'The Guardian')}${article.published_date ? ` &middot; ${escapeHtml(article.published_date)}` : ''}</span>
            <strong>${escapeHtml(article.review_title || article.book_title || 'Article')}</strong>
            ${article.reviewer ? `<span>${escapeHtml(article.reviewer)}</span>` : ''}
            ${article.summary ? `<p>${escapeHtml(article.summary)}</p>` : ''}
            <a class="btn btn--ghost btn--sm" href="${escapeHtml(article.url)}" target="_blank" rel="noopener">Read Guardian article</a>
          </article>
        `).join('')}
      </div>
    `;
  }

  async function loadGuardianArticles(info) {
    if (!guardianArticlesEl) return;
    guardianArticlesEl.textContent = 'Looking for Guardian article matches...';
    const params = new URLSearchParams();
    if (info.title) params.set('title', info.title);
    if (info.author) params.set('author', info.author);
    try {
      const res = await fetch(`/api/critic-reviews/?${params.toString()}`);
      const data = await res.json();
      renderGuardianArticles(data.results || [], data.detail || '');
    } catch (_) {
      renderGuardianArticles([], 'Guardian articles are unavailable right now.');
    }
  }

  function setSelectedRating(value) {
    selectedRating = Number(value || 0);
    ratingButtons.forEach(button => {
      const active = Number(button.dataset.rating) <= selectedRating;
      button.classList.toggle('active', active);
      button.setAttribute('aria-checked', String(Number(button.dataset.rating) === selectedRating));
    });
  }

  function openReviewForm() {
    const info = currentInfo || {
      title: titleSeed,
      author: authorSeed,
      isbn: isbnSeed,
      cover_url: coverSeed,
    };
    if (!reviewForm) return;
    reviewForm.hidden = false;
    reviewFormTitle.textContent = `Review "${info.title || 'this book'}"`;
    reviewText.value = currentReview?.review || '';
    setSelectedRating(currentReview?.rating || 0);
    reviewFormStatus.textContent = '';
    reviewText.focus();
  }

  function closeReviewForm() {
    if (!reviewForm) return;
    reviewForm.hidden = true;
    reviewFormStatus.textContent = '';
  }

  async function submitReview(event) {
    event.preventDefault();
    const info = currentInfo || {
      title: titleSeed,
      author: authorSeed,
      isbn: isbnSeed,
      cover_url: coverSeed,
    };
    const review = (reviewText?.value || '').trim();
    if (!review) {
      reviewFormStatus.textContent = 'Write a few thoughts first.';
      return;
    }
    reviewFormStatus.textContent = 'Saving...';
    const res = await fetch('/api/book-reviews/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({
        title: info.title || titleSeed || '',
        author: info.author || authorSeed || '',
        isbn: info.isbn || isbnSeed || '',
        imported_book: importedBookSeed || null,
        cover_image: info.cover_url || coverSeed || '',
        review,
        rating: selectedRating || null,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      renderReview(data);
      closeReviewForm();
      loadCommunityReviews(info);
    } else {
      reviewFormStatus.textContent = data.detail || 'Could not save review.';
    }
  }

  addReviewBtn?.addEventListener('click', openReviewForm);
  cancelReviewBtn?.addEventListener('click', closeReviewForm);
  reviewForm?.addEventListener('submit', submitReview);
  ratingButtons.forEach(button => {
    button.addEventListener('click', () => setSelectedRating(button.dataset.rating));
  });

  if (titleSeed) {
    loadGuardianArticles({ title: titleSeed, author: authorSeed });
  }

  async function loadBook() {
    if (!query) {
      titleEl.textContent = 'Book details';
      authorEl.textContent = 'Provide a title to search.';
      setDescription('No book query was provided.');
      setSearchLink('books');
      return;
    }

    titleEl.textContent = 'Searching...';
    authorEl.textContent = '';
    setDescription('Looking for this book in the library.');
    setCover(coverSeed, { title: titleSeed, author: authorSeed });
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
        setDescription('We could not find details for this book yet.');
        setCover('', { title: titleSeed, author: authorSeed });
        setInfoChips({});
        setMetaList({});
        return;
      }

      const info = {
        title: titleSeed || result.title || 'Untitled',
        author: authorSeed || result.author || 'Unknown author',
        genre: genreSeed || result.genre || '',
        year: yearSeed || result.year || '',
        isbn: isbnSeed || result.isbn || '',
        description: descriptionSeed || result.description || 'No description available.',
        cover_url: coverSeed || result.cover_url || '',
        average_rating: result.average_rating || '',
        ratings_count: result.ratings_count || '',
      };
      currentInfo = info;

      titleEl.textContent = info.title;
      authorEl.textContent = info.author;
      setDescription(info.description);
      setCover(info.cover_url, info);
      setInfoChips(info);
      setMetaList(info);
      setSearchLink(`${info.title} ${info.author}`);
      loadReview(info);
      loadCommunityReviews(info);
      loadShelves(info);
      loadGuardianArticles(info);
    } catch (err) {
      titleEl.textContent = titleSeed || 'Book details';
      authorEl.textContent = authorSeed || 'Search unavailable';
      setDescription('We could not reach the book service.');
      setCover('', { title: titleSeed, author: authorSeed });
      setInfoChips({});
      setMetaList({});
      const fallbackInfo = { title: titleSeed, author: authorSeed, isbn: isbnSeed, cover_url: coverSeed };
      loadReview(fallbackInfo);
      loadCommunityReviews(fallbackInfo);
      loadShelves(fallbackInfo);
      loadGuardianArticles(fallbackInfo);
    }
  }

  loadBook();
})();

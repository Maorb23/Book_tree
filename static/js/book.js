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
    ];
    rows.forEach(([label, value]) => {
      if (!value) return;
      const li = document.createElement('li');
      li.textContent = `${label}: ${value}`;
      metaList.appendChild(li);
    });
  }

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
      };

      titleEl.textContent = info.title;
      authorEl.textContent = info.author;
      descEl.textContent = info.description;
      setCover(info.cover_url);
      setInfoChips(info);
      setMetaList(info);
      setSearchLink(`${info.title} ${info.author}`);
    } catch (err) {
      titleEl.textContent = titleSeed || 'Book details';
      authorEl.textContent = authorSeed || 'Search unavailable';
      descEl.textContent = 'We could not reach the book service.';
      setCover('');
      setInfoChips({});
      setMetaList({});
    }
  }

  loadBook();
})();

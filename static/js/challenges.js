(function () {
  'use strict';

  const toast = document.getElementById('challengeToast');
  const targetForm = document.getElementById('targetForm');
  const quickLogForm = document.getElementById('quickLogForm');
  const quickDate = document.getElementById('quickDate');

  function getCsrf() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('visible');
    setTimeout(() => toast.classList.remove('visible'), 2400);
  }

  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  if (quickDate && !quickDate.value) quickDate.value = todayIso();

  targetForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const input = document.getElementById('targetBooks');
    const button = targetForm.querySelector('button');
    button.disabled = true;
    button.textContent = 'Updating...';
    try {
      const res = await fetch('/api/challenges/target/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ target_books: input.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not update goal.');
      showToast(`Goal updated: ${data.challenge.target_books} books.`);
      setTimeout(() => window.location.reload(), 450);
    } catch (error) {
      showToast(error.message || 'Could not update goal.');
    } finally {
      button.disabled = false;
      button.textContent = 'Update Goal';
    }
  });

  quickLogForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const select = document.getElementById('quickBook');
    const pagesInput = document.getElementById('quickPages');
    const [source, bookId] = String(select?.value || '').split(':');
    const pages = Number(pagesInput?.value || 0);
    if (!source || !bookId || !pages) {
      showToast('Choose a book and enter pages.');
      return;
    }

    const button = quickLogForm.querySelector('button');
    button.disabled = true;
    button.textContent = 'Logging...';
    try {
      const res = await fetch('/api/reading-updates/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({
          source,
          book_id: bookId,
          pages,
          log_date: quickDate?.value || todayIso(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Could not log pages.');
      showToast(`Logged ${pages} pages. Current streak: ${data.current_page_streak} days.`);
      setTimeout(() => window.location.reload(), 450);
    } catch (error) {
      showToast(error.message || 'Could not log pages.');
    } finally {
      button.disabled = false;
      button.textContent = 'Log';
    }
  });
})();

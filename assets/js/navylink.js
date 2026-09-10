(() => {
  const cards = [...document.querySelectorAll('.link-card')];
  const search = document.querySelector('#link-search');
  const chips = [...document.querySelectorAll('.chip')];
  const count = document.querySelector('#result-count');
  const empty = document.querySelector('#empty-state');
  const clearBtn = document.querySelector('#clear-filters');
  const favoritesBtn = document.querySelector('#favorites-only');
  const storageKey = 'navylink-favorites-v1';
  let category = 'All';
  let favoritesOnly = false;
  let favorites = new Set(JSON.parse(localStorage.getItem(storageKey) || '[]'));

  function normalize(v) { return (v || '').toLowerCase().trim(); }
  function saveFavorites() { localStorage.setItem(storageKey, JSON.stringify([...favorites])); }

  function renderStars() {
    document.querySelectorAll('.star').forEach(btn => {
      const id = btn.dataset.id;
      const saved = favorites.has(id);
      btn.classList.toggle('saved', saved);
      btn.setAttribute('aria-pressed', saved ? 'true' : 'false');
      btn.title = saved ? 'Remove from favorites' : 'Save as favorite';
      btn.textContent = saved ? '★' : '☆';
    });
  }

  function filter() {
    const q = normalize(search.value);
    let visible = 0;
    cards.forEach(card => {
      const matchesQuery = !q || normalize(card.dataset.search).includes(q);
      const matchesCategory = category === 'All' || card.dataset.category === category;
      const matchesFavorite = !favoritesOnly || favorites.has(card.dataset.id);
      const show = matchesQuery && matchesCategory && matchesFavorite;
      card.classList.toggle('hidden', !show);
      if (show) visible++;
    });
    count.textContent = `${visible} link${visible === 1 ? '' : 's'}`;
    empty.classList.toggle('show', visible === 0);
  }

  search.addEventListener('input', filter);
  chips.forEach(chip => chip.addEventListener('click', () => {
    category = chip.dataset.category;
    chips.forEach(c => c.classList.toggle('active', c === chip));
    filter();
  }));

  document.querySelectorAll('.star').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.id;
    favorites.has(id) ? favorites.delete(id) : favorites.add(id);
    saveFavorites();
    renderStars();
    filter();
  }));

  favoritesBtn.addEventListener('click', () => {
    favoritesOnly = !favoritesOnly;
    favoritesBtn.setAttribute('aria-pressed', favoritesOnly ? 'true' : 'false');
    favoritesBtn.textContent = favoritesOnly ? '★ Favorites on' : '☆ Favorites';
    filter();
  });

  clearBtn.addEventListener('click', () => {
    category = 'All';
    favoritesOnly = false;
    search.value = '';
    chips.forEach(c => c.classList.toggle('active', c.dataset.category === 'All'));
    favoritesBtn.setAttribute('aria-pressed', 'false');
    favoritesBtn.textContent = '☆ Favorites';
    filter();
    search.focus();
  });

  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement !== search && !/input|textarea/i.test(document.activeElement.tagName)) {
      e.preventDefault();
      search.focus();
    }
    if (e.key === 'Escape' && document.activeElement === search) {
      search.value = '';
      filter();
      search.blur();
    }
  });

  renderStars();
  filter();
})();

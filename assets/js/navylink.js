(() => {
  const grid = document.querySelector('#link-grid');
  const cards = [...document.querySelectorAll('.link-card')];
  const search = document.querySelector('#link-search');
  const chips = [...document.querySelectorAll('.chip')];
  const count = document.querySelector('#result-count');
  const empty = document.querySelector('#empty-state');
  const clearBtn = document.querySelector('#clear-filters');
  const favoritesBtn = document.querySelector('#favorites-only');
  const sortSelect = document.querySelector('#sort-links');
  const mostUsed = document.querySelector('#most-used-links');
  const refreshUsage = document.querySelector('#refresh-usage');
  const favoriteKey = 'navylink-favorites-v1';
  let category = 'All';
  let favoritesOnly = false;
  let favorites = new Set(JSON.parse(localStorage.getItem(favoriteKey) || '[]'));
  let usage = {};

  cards.forEach((card, index) => card.dataset.originalIndex = index);

  function normalize(v) { return (v || '').toLowerCase().trim(); }
  function saveFavorites() { localStorage.setItem(favoriteKey, JSON.stringify([...favorites])); }
  function uses(id) { return Number(usage[id] || 0); }

  function renderStars() {
    document.querySelectorAll('.star').forEach(btn => {
      const saved = favorites.has(btn.dataset.id);
      btn.classList.toggle('saved', saved);
      btn.setAttribute('aria-pressed', saved ? 'true' : 'false');
      btn.title = saved ? 'Remove from favorites' : 'Save as favorite';
      btn.textContent = saved ? '★' : '☆';
    });
  }

  function sortedCards() {
    const mode = sortSelect.value;
    return [...cards].sort((a, b) => {
      if (mode === 'usage') return uses(b.dataset.id) - uses(a.dataset.id) || a.dataset.name.localeCompare(b.dataset.name);
      if (mode === 'category') return a.dataset.category.localeCompare(b.dataset.category) || a.dataset.name.localeCompare(b.dataset.name);
      if (mode === 'curated') return Number(a.dataset.originalIndex) - Number(b.dataset.originalIndex);
      return a.dataset.name.localeCompare(b.dataset.name, undefined, { sensitivity: 'base' });
    });
  }

  function renderOrder() {
    sortedCards().forEach(card => grid.appendChild(card));
  }

  function renderMostUsed() {
    const ranked = [...cards].sort((a, b) => {
      const countDiff = uses(b.dataset.id) - uses(a.dataset.id);
      if (countDiff) return countDiff;
      const featuredDiff = (b.dataset.featured === 'true') - (a.dataset.featured === 'true');
      if (featuredDiff) return featuredDiff;
      return a.dataset.name.localeCompare(b.dataset.name);
    }).slice(0, 6);

    mostUsed.innerHTML = '';
    ranked.forEach(card => {
      const a = document.createElement('a');
      a.href = card.dataset.url;
      a.dataset.id = card.dataset.id;
      a.className = 'most-used-link';
      const n = uses(card.dataset.id);
      a.innerHTML = `<span>${card.dataset.name}</span><small>${n ? `${n.toLocaleString()} open${n === 1 ? '' : 's'}` : 'Starter shortcut'}</small>`;
      a.addEventListener('click', () => recordUse(card.dataset.id));
      mostUsed.appendChild(a);
    });
  }

  async function loadUsage() {
    if (refreshUsage) {
      refreshUsage.disabled = true;
      refreshUsage.textContent = 'Refreshing…';
    }
    try {
      const response = await fetch('/api/stats', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      usage = {};
      for (const item of (data.links || [])) usage[item.id] = Number(item.total || 0);
      renderMostUsed();
      if (sortSelect.value === 'usage') filter();
    } catch (err) {
      console.warn('[Navylink] Global usage API unavailable; using starter ranking.', err);
      renderMostUsed();
    } finally {
      if (refreshUsage) {
        refreshUsage.disabled = false;
        refreshUsage.textContent = 'Refresh rankings';
      }
    }
  }

  function recordUse(id) {
    if (!id) return;
    usage[id] = uses(id) + 1;
    renderMostUsed();
    if (sortSelect.value === 'usage') renderOrder();
    fetch(`/api/click/${encodeURIComponent(id)}`, {
      method: 'POST',
      keepalive: true,
      headers: { 'Accept': 'application/json' }
    }).catch(err => console.warn('[Navylink] Click count was not recorded.', err));
  }

  function filter() {
    renderOrder();
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
    count.textContent = `${visible} link${visible === 1 ? '' : 's'} · ${sortSelect.options[sortSelect.selectedIndex].text}`;
    empty.classList.toggle('show', visible === 0);
  }

  search.addEventListener('input', filter);
  sortSelect.addEventListener('change', filter);

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

  document.querySelectorAll('.tracked-link').forEach(link => link.addEventListener('click', () => recordUse(link.dataset.id)));

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
    sortSelect.value = 'alpha';
    chips.forEach(c => c.classList.toggle('active', c.dataset.category === 'All'));
    favoritesBtn.setAttribute('aria-pressed', 'false');
    favoritesBtn.textContent = '☆ Favorites';
    filter();
    search.focus();
  });

  if (refreshUsage) refreshUsage.addEventListener('click', loadUsage);

  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement !== search && !/input|textarea|select/i.test(document.activeElement.tagName)) {
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
  renderMostUsed();
  filter();
  loadUsage();
})();

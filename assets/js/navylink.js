(() => {
  const grid = document.querySelector('#link-grid');
  const cards = [...document.querySelectorAll('.link-card')];
  const search = document.querySelector('#link-search');
  const chips = [...document.querySelectorAll('.chip')];
  const navFilters = [...document.querySelectorAll('.nav-filter')];
  const count = document.querySelector('#result-count');
  const activeFilter = document.querySelector('#active-filter');
  const empty = document.querySelector('#empty-state');
  const clearBtn = document.querySelector('#clear-filters');
  const favoritesBtn = document.querySelector('#favorites-only');
  const sortSelect = document.querySelector('#sort-links');
  const mostUsed = document.querySelector('#most-used-links');
  const refreshUsage = document.querySelector('#refresh-usage');
  const favoriteKey = 'navylink-favorites-v1';

  let group = 'All';
  let category = 'All';
  let kind = 'all';
  let favoritesOnly = false;
  let favorites = new Set(JSON.parse(localStorage.getItem(favoriteKey) || '[]'));
  let usage = {};

  cards.forEach((card, index) => card.dataset.originalIndex = index);

  function normalize(v) { return (v || '').toLowerCase().trim(); }
  function saveFavorites() { localStorage.setItem(favoriteKey, JSON.stringify([...favorites])); }
  function uses(id) { return Number(usage[id] || 0); }
  function trackedUrl(id) { return `/api/go/${encodeURIComponent(id)}`; }

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
      if (mode === 'category') return a.dataset.group.localeCompare(b.dataset.group) || a.dataset.category.localeCompare(b.dataset.category) || a.dataset.name.localeCompare(b.dataset.name);
      if (mode === 'curated') return Number(a.dataset.originalIndex) - Number(b.dataset.originalIndex);
      return a.dataset.name.localeCompare(b.dataset.name, undefined, { sensitivity: 'base' });
    });
  }

  function renderOrder() { sortedCards().forEach(card => grid.appendChild(card)); }

  function renderMostUsed() {
    const eligible = cards.filter(card => card.dataset.kind !== 'hub');
    const pool = eligible.length >= 6 ? eligible : cards;
    const ranked = [...pool].sort((a, b) => {
      const countDiff = uses(b.dataset.id) - uses(a.dataset.id);
      if (countDiff) return countDiff;
      const featuredDiff = (b.dataset.featured === 'true') - (a.dataset.featured === 'true');
      if (featuredDiff) return featuredDiff;
      return a.dataset.name.localeCompare(b.dataset.name);
    }).slice(0, 6);

    mostUsed.innerHTML = '';
    ranked.forEach(card => {
      const a = document.createElement('a');
      a.href = trackedUrl(card.dataset.id);
      a.dataset.id = card.dataset.id;
      a.className = 'most-used-link';
      const n = uses(card.dataset.id);
      a.innerHTML = `<span>${card.dataset.name}</span><small>${n ? `${n.toLocaleString()} open${n === 1 ? '' : 's'}` : 'Direct shortcut'}</small>`;
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
      console.warn('[Navylink] Global usage API unavailable.', err);
      renderMostUsed();
    } finally {
      if (refreshUsage) {
        refreshUsage.disabled = false;
        refreshUsage.textContent = 'Refresh rankings';
      }
    }
  }

  function openCard(card) {
    if (!card?.dataset.id) return;
    window.location.href = trackedUrl(card.dataset.id);
  }

  function filterLabel() {
    const pieces = [];
    if (group !== 'All') pieces.push(group);
    if (category !== 'All' && category !== group) pieces.push(category);
    if (kind === 'direct') pieces.push('Direct destinations');
    if (kind === 'hub') pieces.push('Portals & directories');
    if (favoritesOnly) pieces.push('Favorites');
    activeFilter.textContent = pieces.length ? `Showing: ${pieces.join(' · ')}` : 'Showing all resources';
  }

  function syncFilterControls() {
    chips.forEach(chip => chip.classList.toggle('active', chip.dataset.category === category));
    navFilters.forEach(btn => {
      const g = btn.dataset.group || 'All';
      const c = btn.dataset.category || 'All';
      const k = btn.dataset.kind || 'all';
      btn.classList.toggle('active', g === group && c === category && k === kind);
    });
    filterLabel();
  }

  function filter() {
    renderOrder();
    const q = normalize(search.value);
    let visible = 0;
    cards.forEach(card => {
      const matchesQuery = !q || normalize(card.dataset.search).includes(q);
      const matchesGroup = group === 'All' || card.dataset.group === group;
      const matchesCategory = category === 'All' || card.dataset.category === category;
      const matchesKind = kind === 'all' || card.dataset.kind === kind;
      const matchesFavorite = !favoritesOnly || favorites.has(card.dataset.id);
      const show = matchesQuery && matchesGroup && matchesCategory && matchesKind && matchesFavorite;
      card.classList.toggle('hidden', !show);
      if (show) visible++;
    });
    count.textContent = `${visible} resource${visible === 1 ? '' : 's'} · ${sortSelect.options[sortSelect.selectedIndex].text}`;
    empty.classList.toggle('show', visible === 0);
    syncFilterControls();
  }

  search.addEventListener('input', filter);
  sortSelect.addEventListener('change', filter);

  chips.forEach(chip => chip.addEventListener('click', () => {
    category = chip.dataset.category;
    if (category === 'All') group = 'All';
    else {
      const matchingCard = cards.find(card => card.dataset.category === category);
      group = matchingCard ? matchingCard.dataset.group : 'All';
    }
    kind = 'all';
    filter();
  }));

  navFilters.forEach(btn => btn.addEventListener('click', () => {
    group = btn.dataset.group || 'All';
    category = btn.dataset.category || 'All';
    kind = btn.dataset.kind || 'all';
    document.querySelectorAll('.nav-menu[open]').forEach(menu => menu.removeAttribute('open'));
    filter();
    document.querySelector('#link-grid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));

  document.querySelectorAll('.nav-menu').forEach(menu => menu.addEventListener('toggle', () => {
    if (!menu.open) return;
    document.querySelectorAll('.nav-menu[open]').forEach(other => {
      if (other !== menu) other.removeAttribute('open');
    });
  }));

  document.addEventListener('click', event => {
    if (!event.target.closest('.resource-nav')) {
      document.querySelectorAll('.nav-menu[open]').forEach(menu => menu.removeAttribute('open'));
    }
  });

  document.querySelectorAll('.star').forEach(btn => btn.addEventListener('click', event => {
    event.stopPropagation();
    const id = btn.dataset.id;
    favorites.has(id) ? favorites.delete(id) : favorites.add(id);
    saveFavorites();
    renderStars();
    filter();
  }));

  document.querySelectorAll('.tracked-link').forEach(link => link.addEventListener('click', event => event.stopPropagation()));

  cards.forEach(card => {
    card.addEventListener('click', event => {
      if (event.target.closest('a,button,input,select,textarea,label')) return;
      openCard(card);
    });
    card.addEventListener('keydown', event => {
      if (event.target !== card) return;
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openCard(card);
      }
    });
  });

  favoritesBtn.addEventListener('click', () => {
    favoritesOnly = !favoritesOnly;
    favoritesBtn.setAttribute('aria-pressed', favoritesOnly ? 'true' : 'false');
    favoritesBtn.textContent = favoritesOnly ? '★ Favorites on' : '☆ Favorites';
    filter();
  });

  clearBtn.addEventListener('click', () => {
    group = 'All';
    category = 'All';
    kind = 'all';
    favoritesOnly = false;
    search.value = '';
    sortSelect.value = 'alpha';
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
    if (e.key === 'Escape') {
      document.querySelectorAll('.nav-menu[open]').forEach(menu => menu.removeAttribute('open'));
      if (document.activeElement === search) {
        search.value = '';
        filter();
        search.blur();
      }
    }
  });

  renderStars();
  renderMostUsed();
  filter();
  loadUsage();
})();

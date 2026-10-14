const FilterComponent = (function () {
  function getBaseData() {
    return window.allCitationsData || window.citationsData || [];
  }

  function getAvailableYearRanges(baseDados = getBaseData()) {
    const years = (baseDados || [])
      .map(c => parseInt(c.year, 10))
      .filter(year => !Number.isNaN(year));

    if (!years.length) return [];

    const minYear = Math.min(...years);
    const maxYear = Math.max(...years);
    const startBoundary = Math.floor(minYear / 5) * 5;
    const ranges = [];

    for (let start = startBoundary; start <= maxYear; start += 5) {
      const end = start + 4;
      const hasArticlesInRange = years.some(year => year >= start && year <= end);

      if (hasArticlesInRange) {
        ranges.push({ start, end });
      }
    }

    return ranges;
  }

  const activeFilters = {
    years: [],
    authors: [], 
    venues: [],
    citationCount: null,
    orderBy: ''
  };

  function getCitationCount(item) {
    const value = item.citations_count ?? item.citationCount ?? item.cited_by_count;
    if (value === '' || value === '-') return null;
    const count = Number(value);
    return Number.isFinite(count) ? count : null;
  }

  function getChronologicalValue(item) {
    const dateValue = item.publication_date ?? item.publicationDate ?? item.published_date ?? item.publishedDate;
    if (dateValue) {
      const timestamp = Date.parse(String(dateValue));
      if (!Number.isNaN(timestamp)) return timestamp;
    }

    const year = Number.parseInt(item.year, 10);
    return Number.isFinite(year) ? year : null;
  }

  function sortResults(result) {
    const orderBy = activeFilters.orderBy;
    if (!orderBy) return result;

    const direction = orderBy.endsWith('-desc') ? -1 : 1;
    const valueGetter = orderBy.startsWith('citations')
      ? getCitationCount
      : getChronologicalValue;

    return result
      .map((item, index) => ({ item, index, value: valueGetter(item) }))
      .sort((a, b) => {
        if (a.value === null && b.value === null) return a.index - b.index;
        if (a.value === null) return 1;
        if (b.value === null) return -1;
        return (a.value - b.value) * direction || a.index - b.index;
      })
      .map(entry => entry.item);
  }

  function applyCombinedFilters() {
    const baseDados = getBaseData() || [];
    let result = baseDados.slice();

    // Filtro por anos
    if (activeFilters.years && activeFilters.years.length) {
      result = result.filter(c => {
        const year = parseInt(c.year, 10);
        if (isNaN(year)) return false;
        return activeFilters.years.some(r => year >= r.start && year <= r.end);
      });
    }

    // Filtro por autores
    if (activeFilters.authors && activeFilters.authors.length) {
      const lowered = activeFilters.authors.map(a => a.toLowerCase());
      result = result.filter(c => {
        const authors = c.authors || c.author || [];
        let list = [];
        if (Array.isArray(authors)) list = authors.map(a => (a && a.name) ? a.name : String(a));
        else if (typeof authors === 'string') list = authors.split(/;|,|\sand\s/).map(s => s.trim()).filter(Boolean);
        return lowered.some(sel => list.some(name => name.toLowerCase().includes(sel)));
      });
    }

    // Filtro por venues
    if (activeFilters.venues && activeFilters.venues.length) {
      const lowered = activeFilters.venues.map(v => v.toLowerCase());
      result = result.filter(c => {
        const venue = (c.venue || c.journal || c.conference || '').toLowerCase();
        return lowered.some(sel => venue.includes(sel));
      });
    } 

    result = sortResults(result);
    try { window.citationsData = result; } catch (err) {}
    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(result);
    else console.warn('mostrarCitacoes não encontrada para renderizar resultados');
  }

  function renderYearRangeButtons() {
    const submenu = document.getElementById('decadeSubMenu');
    if (!submenu) return;

    const buttonsContainer = submenu.querySelector('.decade-buttons');
    if (!buttonsContainer) return;

    const ranges = getAvailableYearRanges();

    if (!ranges.length) {
      submenu.classList.add('hidden');
      buttonsContainer.innerHTML = '';
      return;
    }

    buttonsContainer.innerHTML = ranges.map(range => (
      `<button type="button" class="btn-decade" data-start="${range.start}" data-end="${range.end}">${range.start} - ${range.end}</button>`
    )).join('') + `
      <div class="custom-range" style="display:inline-flex;align-items:center;gap:6px;margin-left:8px;">
        <input id="startYear" type="number" placeholder="Year" style="width:90px;padding:4px;" />
        <button id="filterBtn" type="button" class="btn btn-sm btn-primary">Apply</button>
      </div>
    `;

    const decadeButtons = buttonsContainer.querySelectorAll('.btn-decade');
    
    // Remarca os botões ativos
    if (activeFilters.years && activeFilters.years.length) {
      decadeButtons.forEach(btn => {
        const s = parseInt(btn.getAttribute('data-start'), 10);
        const e = parseInt(btn.getAttribute('data-end'), 10);
        const match = activeFilters.years.some(r => r.start === s && r.end === e);
        if (match) btn.classList.add('active');
      });
    }

    decadeButtons.forEach(button => {
      button.addEventListener('click', () => {
        button.classList.toggle('active');

        const activeBtns = Array.from(buttonsContainer.querySelectorAll('.btn-decade.active'));
        const selectedRanges = activeBtns.map(btn => ({
          start: parseInt(btn.getAttribute('data-start'), 10),
          end: parseInt(btn.getAttribute('data-end'), 10)
        })).filter(r => !isNaN(r.start) && !isNaN(r.end));

        activeFilters.years = selectedRanges;
        applyCombinedFilters();
      });
    });

    const filterBtn = document.getElementById('filterBtn');
    if (filterBtn) {
      filterBtn.addEventListener('click', () => {
        const startInput = document.getElementById('startYear');
        if (!startInput) return;

        const s = parseInt(startInput.value, 10);
        if (isNaN(s)) return;

        activeFilters.years = [{ start: s, end: s }];
        applyCombinedFilters();
      });

      const startInputEl = document.getElementById('startYear');
      if (startInputEl) {
        startInputEl.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter') {
            ev.preventDefault();
            filterBtn.click();
          }
        });
      }
    }
  }

  function getAuthorsFromData(baseDados = getBaseData()) {
    const counter = Object.create(null);

    (baseDados || []).forEach(item => {
      const authors = item.authors || item.author || item.Author || [];

      let list = [];
      if (Array.isArray(authors)) list = authors.map(a => (a && a.name) ? a.name : String(a));
      else if (typeof authors === 'string') list = authors.split(/;|,|\sand\s/).map(s => s.trim()).filter(Boolean);

      list.forEach(name => {
        const key = (name || '').trim();
        if (!key) return;
        const lower = key.toLowerCase();
        counter[lower] = counter[lower] || { name: key, count: 0 };
        counter[lower].count += 1;
      });
    });

    return Object.values(counter).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }

  function renderAuthorList() {
    const submenu = document.getElementById('authorSubMenu');
    if (!submenu) return;
    const container = submenu.querySelector('.author-list');
    if (!container) return;

    const authors = getAuthorsFromData();
    if (!authors.length) {
      submenu.classList.add('hidden');
      container.innerHTML = '';
      return;
    }

    // Construído por DOM, não por innerHTML: os nomes vêm de OpenAlex/Semantic
    // Scholar/Crossref, bases colaborativas onde qualquer um cadastra metadado.
    // Um autor chamado <img src=x onerror=...> executaria script ao abrir este
    // submenu. textContent e dataset nunca interpretam HTML.
    container.innerHTML = '';
    authors.forEach(a => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-author';
      btn.dataset.author = a.name;
      btn.textContent = `${a.name} (${a.count})`;
      container.appendChild(btn);
    });

    const authorButtons = container.querySelectorAll('.btn-author');
    
    if (activeFilters.authors && activeFilters.authors.length) {
      authorButtons.forEach(btn => {
        const name = (btn.getAttribute('data-author') || '').toLowerCase();
        if (activeFilters.authors.some(a => (a || '').toLowerCase() === name)) btn.classList.add('active');
      });
    }

    authorButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');

        const activeBtns = Array.from(container.querySelectorAll('.btn-author.active'));
        const selectedAuthors = activeBtns.map(b => b.getAttribute('data-author'));

        activeFilters.authors = selectedAuthors;
        applyCombinedFilters();
      });
    });
  }

  function getVenuesFromData(baseDados = getBaseData()) {
    const counter = Object.create(null);
    (baseDados || []).forEach(item => {
      const raw = (item.venue || item.journal || item['container-title'] || item.publisher || '') || '';
      const name = String(raw).trim();
      if (!name) return;
      const lower = name.toLowerCase();
      counter[lower] = counter[lower] || { name, count: 0 };
      counter[lower].count += 1;
    });
    return Object.values(counter).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }

  function renderVenueList() {
    const submenu = document.getElementById('venueSubMenu');
    if (!submenu) return;
    const container = submenu.querySelector('.venue-list');
    if (!container) return;

    const venues = getVenuesFromData();
    if (!venues.length) {
      submenu.classList.add('hidden');
      container.innerHTML = '';
      return;
    }

    container.innerHTML = '';
    venues.forEach(v => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-venue';
      btn.dataset.venue = v.name;
      btn.textContent = `${v.name} (${v.count})`;
      container.appendChild(btn);
    });

    const venueButtons = container.querySelectorAll('.btn-venue');
    if (activeFilters.venues && activeFilters.venues.length) {
      venueButtons.forEach(btn => {
        const name = (btn.getAttribute('data-venue') || '').toLowerCase();
        if (activeFilters.venues.some(a => (a || '').toLowerCase() === name)) btn.classList.add('active');
      });
    }

    venueButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('active');
        const activeBtns = Array.from(container.querySelectorAll('.btn-venue.active'));
        const selected = activeBtns.map(b => b.getAttribute('data-venue'));
        activeFilters.venues = selected;
        applyCombinedFilters();
      });
    });
  }

  function ensureMarkup() {
    if (document.getElementById('status')) return; 
    const wrapper = document.getElementById('filterWrapper');
    if (!wrapper) return;
    wrapper.insertAdjacentHTML('afterbegin', `
      <div class="filter-controls">
        <div class="filter-dropdown">
          <i class="bi bi-filter"></i>
          <span style="font-family: 'Poppins', sans-serif;">Filter By</span>
          <select id="status" name="status">
            <option value="todos">Todos</option>
            <option value="year-range">Year Range</option>
            <option value="author">Author</option>
            <option value="venue">Venue</option>
          </select>
        </div>
        <div class="filter-dropdown order-by-dropdown">
          <i class="bi bi-sort-down"></i>
          <label for="orderBy" class="order-by-label">Order By</label>
          <select id="orderBy" name="orderBy" aria-label="Order results by">
            <option value="">Default</option>
            <option value="citations-asc">Citations (low to high)</option>
            <option value="citations-desc">Citations (high to low)</option>
            <option value="chronological-asc">Chronological (oldest first)</option>
            <option value="chronological-desc">Chronological (newest first)</option>
          </select>
        </div>
      </div>

      <div id="decadeSubMenu" class="submenu hidden">
        <div class="decade-buttons"></div>
      </div>
      <div id="authorSubMenu" class="submenu hidden">
        <div class="author-list"></div>
      </div>
      <div id="venueSubMenu" class="submenu hidden">
        <div class="venue-list"></div>
      </div>
    `);
  }

  function resetFilters() {
    clearActiveFilters();

    const full = getBaseData();
    try { window.citationsData = full; } catch (err) {}
    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(full);
  }

  /**
   * Zera o estado dos filtros e o destaque dos botões, sem mexer nos dados.
   *
   * Usado quando o dataset é trocado por baixo (Citations <-> References): os
   * filtros valiam para a lista anterior, e manter os botões marcados enquanto
   * a tabela mostra tudo faz a UI afirmar algo que não é verdade.
   */
  function clearActiveFilters() {
    activeFilters.years = [];
    activeFilters.authors = [];
    activeFilters.venues = [];

    document
      .querySelectorAll('.btn-decade.active, .btn-author.active, .btn-venue.active')
      .forEach(btn => btn.classList.remove('active'));
  }

  /**
   * Re-renderiza o submenu que estiver aberto, com os dados atuais.
   *
   * Sem isso, trocar de modo deixava as listas de autor e venue exibindo o
   * dataset anterior, com contagens erradas — só o year-range era atualizado.
   */
  function refreshOpenSubmenu() {
    const statusSelect = document.getElementById('status');
    if (!statusSelect) return;

    const renderers = {
      'year-range': renderYearRangeButtons,
      author: renderAuthorList,
      venue: renderVenueList,
    };

    const render = renderers[statusSelect.value];
    if (render) render();
  }

  function setupUiListeners(options = {}) {
    ensureMarkup();

    const selectors = Object.assign({
      status: 'status',
      decadeSubMenu: 'decadeSubMenu',
      filterBtn: 'filterBtn',
      orderByBtn: 'orderByBtn'
    }, options);

    const statusSelect = document.getElementById(selectors.status);
    const orderBySelect = document.getElementById('orderBy');
    const decadeSubMenu = document.getElementById(selectors.decadeSubMenu);
    const authorSubMenu = document.getElementById('authorSubMenu');
    const venueSubMenu = document.getElementById('venueSubMenu');
    const collapseBtn = document.getElementById('filterCollapseBtn');
    const filterWrapper = document.getElementById('filterWrapper');

    function hideAllSubmenus() {
      decadeSubMenu && decadeSubMenu.classList.add('hidden');
      authorSubMenu && authorSubMenu.classList.add('hidden');
      venueSubMenu && venueSubMenu.classList.add('hidden');
    }

    if (statusSelect) {
      statusSelect.addEventListener('change', (event) => {
        const selectedOption = (event.target.value || '').toString();

        hideAllSubmenus();

        if (selectedOption === 'todos' || selectedOption === '') {
          try { resetFilters(); } catch (err) {}
          return;
        }

        if (selectedOption === 'year-range') {
          renderYearRangeButtons();
          const hasDecades = decadeSubMenu && decadeSubMenu.querySelector('.btn-decade');
          if (hasDecades) decadeSubMenu.classList.remove('hidden');

        } else if (selectedOption === 'author') {
          renderAuthorList();
          const hasAuthors = authorSubMenu && authorSubMenu.querySelector('.btn-author');
          if (hasAuthors) authorSubMenu.classList.remove('hidden');

        } else if (selectedOption === 'venue') {
          renderVenueList();
          const hasVenues = venueSubMenu && venueSubMenu.querySelector('.btn-venue');
          if (hasVenues) venueSubMenu.classList.remove('hidden');
        }
      });
    }

    if (orderBySelect) {
      orderBySelect.addEventListener('change', event => {
        activeFilters.orderBy = event.target.value || '';
        applyCombinedFilters();
      });
    }

    let collapsed = false;
    if (collapseBtn) {
      collapseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        collapsed = !collapsed;
        if (collapsed) {
          hideAllSubmenus();
          collapseBtn.textContent = '▸';
        } else {
          collapseBtn.textContent = '▾';
        }
      });
    }

    // Fecha os submenus ao clicar fora da área do filtro
    document.addEventListener('click', (event) => {
      if (!filterWrapper) return;
      if (filterWrapper.contains(event.target)) return; 

      hideAllSubmenus();
    });

    renderYearRangeButtons();
  }

  let initialized = false;

  function init(options) {
    if (initialized) return;
    setupUiListeners(options);
    initialized = true;
  }

  return {
    init,
    renderYearRangeButtons,
    applyCombinedFilters,
    clearActiveFilters,
    refreshOpenSubmenu,
    reset: resetFilters
  };
})();

try {
  if (typeof window !== 'undefined') window.FilterComponent = FilterComponent;
} catch (err) {}
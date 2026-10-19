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

    function getYearBounds(baseDados = getBaseData()) {
    const years = (baseDados || [])
      .map(c => parseInt(c.year, 10))
      .filter(year => !Number.isNaN(year));

    if (!years.length) return null;
    return { min: Math.min(...years), max: Math.max(...years) };
  }

    function renderYearRangeButtons() {
    const submenu = document.getElementById('decadeSubMenu');
    if (!submenu) return;

    const container = submenu.querySelector('.decade-buttons');
    if (!container) return;

    const bounds = getYearBounds();

    if (!bounds) {
      submenu.classList.add('hidden');
      container.innerHTML = '';
      return;
    }

    container.innerHTML = `
      <div class="custom-range">
        <span class="custom-range-label">Year range</span>
        <input id="startYear" class="custom-range-input" type="number" inputmode="numeric"
               placeholder="${bounds.min}" title="Start year (blank = ${bounds.min})" aria-label="Start year" />
        <span class="custom-range-sep">to</span>
        <input id="endYear" class="custom-range-input" type="number" inputmode="numeric"
               placeholder="${bounds.max}" title="End year (blank = ${bounds.max})" aria-label="End year" />
        <button id="filterBtn" type="button" class="btn-apply-range">Apply</button>
        <button id="clearRangeBtn" type="button" class="btn-clear-range">Clear</button>
        <p id="yearRangeError" class="custom-range-error" role="alert" hidden></p>
      </div>
    `;

    const startInput = document.getElementById('startYear');
    const endInput = document.getElementById('endYear');
    const filterBtn = document.getElementById('filterBtn');
    const clearBtn = document.getElementById('clearRangeBtn');
    const errorEl = document.getElementById('yearRangeError');

    function showError(message) {
      errorEl.textContent = message || '';
      errorEl.hidden = !message;
    }

    // Restaura o intervalo aplicado ao reabrir o submenu
    const applied = (activeFilters.years || [])[0];
    if (applied) {
      startInput.value = applied.start;
      endInput.value = applied.end;
    }

    function applyCustomRange() {
      const rawStart = startInput.value.trim();
      const rawEnd = endInput.value.trim();

      if (!rawStart && !rawEnd) {
        showError('Enter at least one year.');
        return;
      }

      // Campo em branco = sem limite naquele lado
      let start = rawStart ? parseInt(rawStart, 10) : bounds.min;
      let end = rawEnd ? parseInt(rawEnd, 10) : bounds.max;

      if (isNaN(start) || isNaN(end) || start < 1000 || start > 9999 || end < 1000 || end > 9999) {
        showError('Enter valid 4-digit years.');
        return;
      }

      // Se vier invertido (ex.: 2024 até 2018), troca em vez de dar erro
      if (start > end) {
        [start, end] = [end, start];
        startInput.value = start;
        endInput.value = end;
      }

      showError('');
      activeFilters.years = [{ start, end }];
      applyCombinedFilters();
    }

    filterBtn.addEventListener('click', applyCustomRange);

    [startInput, endInput].forEach(input => {
      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          applyCustomRange();
        }
      });
    });

    clearBtn.addEventListener('click', () => {
      startInput.value = '';
      endInput.value = '';
      showError('');
      activeFilters.years = [];
      applyCombinedFilters();
    });
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
            <option value="citations-asc">Least to most Cited</option>
            <option value="citations-desc">Most to least Cited</option>
            <option value="chronological-asc">Oldest to newest</option>
            <option value="chronological-desc">Newest to oldest</option>
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

  const selectDropdowns = new Set();

  function closeOtherSelectDropdowns(current) {
    selectDropdowns.forEach(dropdown => {
      if (dropdown !== current) dropdown.close();
    });
  }

 
  function enhanceSelect(select, options = {}) {
    if (!select || select.dataset.enhanced === 'true') return;
    select.dataset.enhanced = 'true';

    const { onOpen = null, emitOnReselect = false } = options;

    const wrapper = document.createElement('div');
    wrapper.className = 'select-dropdown';

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'select-trigger';
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const ariaLabel = select.getAttribute('aria-label');
    if (ariaLabel) trigger.setAttribute('aria-label', ariaLabel);

    const triggerLabel = document.createElement('span');
    triggerLabel.className = 'select-trigger-label';

    const chevron = document.createElement('i');
    chevron.className = 'bi bi-chevron-down select-chevron';
    chevron.setAttribute('aria-hidden', 'true');

    trigger.append(triggerLabel, chevron);

    const menu = document.createElement('ul');
    menu.className = 'select-menu hidden';
    menu.setAttribute('role', 'listbox');

    let focusedIndex = -1;

    const items = Array.from(select.options).map((option, index) => {
      const li = document.createElement('li');
      li.className = 'select-option';
      li.setAttribute('role', 'option');
      li.textContent = option.textContent;
      li.addEventListener('click', () => choose(index));
      menu.appendChild(li);
      return li;
    });

    function sync() {
      const index = Math.max(select.selectedIndex, 0);
      const current = select.options[index];
      triggerLabel.textContent = current ? current.textContent : '';
      items.forEach((li, i) => li.setAttribute('aria-selected', String(i === index)));
    }

    function setFocused(index) {
      focusedIndex = Math.min(Math.max(index, 0), items.length - 1);
      items.forEach((li, i) => li.classList.toggle('is-focused', i === focusedIndex));
      items[focusedIndex].scrollIntoView({ block: 'nearest' });
    }

    function isOpen() {
      return !menu.classList.contains('hidden');
    }

    function open() {
      closeOtherSelectDropdowns(api);   // só um dropdown aberto por vez
      if (onOpen) onOpen();
      menu.classList.remove('hidden');
      trigger.setAttribute('aria-expanded', 'true');
      setFocused(Math.max(select.selectedIndex, 0));
    }

    function close() {
      menu.classList.add('hidden');
      trigger.setAttribute('aria-expanded', 'false');
      items.forEach(li => li.classList.remove('is-focused'));
    }

    function choose(index) {
      const changed = select.selectedIndex !== index;
      select.selectedIndex = index;
      sync();
      close();
      trigger.focus();
      if (changed || emitOnReselect) {
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    const api = { close };
    selectDropdowns.add(api);

    // Sem stopPropagation: o clique precisa chegar ao document para que os
    // outros dropdowns (e os submenus) saibam que o clique foi fora deles.
    trigger.addEventListener('click', () => {
      isOpen() ? close() : open();
    });

    trigger.addEventListener('keydown', (event) => {
      switch (event.key) {
        case 'ArrowDown':
          event.preventDefault();
          if (!isOpen()) open(); else setFocused(focusedIndex + 1);
          break;
        case 'ArrowUp':
          event.preventDefault();
          if (!isOpen()) open(); else setFocused(focusedIndex - 1);
          break;
        case 'Home':
          if (isOpen()) { event.preventDefault(); setFocused(0); }
          break;
        case 'End':
          if (isOpen()) { event.preventDefault(); setFocused(items.length - 1); }
          break;
        case 'Enter':
        case ' ':
          event.preventDefault();
          if (isOpen()) choose(focusedIndex); else open();
          break;
        case 'Escape':
          if (isOpen()) { event.preventDefault(); close(); }
          break;
        case 'Tab':
          close();
          break;
      }
    });

    // Fecha ao clicar fora
    document.addEventListener('click', (event) => {
      if (!wrapper.contains(event.target)) close();
    });

    // Clicar no <label> (ex.: "Order By") foca o novo botão
    if (select.id) {
      const label = document.querySelector(`label[for="${select.id}"]`);
      if (label) {
        label.addEventListener('click', (event) => {
          event.preventDefault();
          trigger.focus();
        });
      }
    }

    select.classList.add('select-native-hidden');
    select.parentNode.insertBefore(wrapper, select);
    wrapper.append(trigger, menu, select);
    sync();
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

    enhanceSelect(statusSelect, { emitOnReselect: true });
    enhanceSelect(orderBySelect, { onOpen: hideAllSubmenus });

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
          const hasRange = decadeSubMenu && decadeSubMenu.querySelector('.custom-range');
          if (hasRange) decadeSubMenu.classList.remove('hidden');
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
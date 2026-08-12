const FilterComponent = (function () {
  function getBaseData() {
    const activeData = window.citationsData || window.allCitationsData || [];
    window.allCitationsData = activeData;
    return activeData;
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
    decadeButtons.forEach(button => {
      button.addEventListener('click', () => {
        const nowActive = button.classList.toggle('active');

        const activeBtns = Array.from(document.querySelectorAll('.btn-decade.active'));
        if (!activeBtns.length) {
          resetFilters();
          return;
        }

        const ranges = activeBtns.map(btn => ({
          start: parseInt(btn.getAttribute('data-start'), 10),
          end: parseInt(btn.getAttribute('data-end'), 10)
        })).filter(r => !isNaN(r.start) && !isNaN(r.end));

        if (ranges.length) aplicarFiltroRanges(ranges);
      });
    });

    const filterBtn = document.getElementById('filterBtn');
    if (filterBtn) {
      filterBtn.addEventListener('click', () => {
        const startInput = document.getElementById('startYear');
        if (!startInput) return;

        const s = parseInt(startInput.value, 10);
        if (isNaN(s)) return;

        aplicarFiltroAno(s, s);
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

  function ensureMarkup() {
    if (document.getElementById('status')) return; 
    const wrapper = document.getElementById('filterWrapper');
    if (!wrapper) return;

    wrapper.insertAdjacentHTML('afterbegin', `
      <div class="filter-dropdown">
        <i class="bi bi-filter"></i>
        <span>Filter By</span>
        <select id="status" name="status">
          <option value="">Todos</option>
          <option value="year-range">Year Range</option>
          <option value="author">Author</option>
          <option value="openAccess">OpenAccess</option>
          <option value="citation-count">Citation Count</option>
          <option value="keyword">Keyword</option>
        </select>
      </div>

      <div id="decadeSubMenu" class="decade-submenu hidden">
        <div class="decade-buttons"></div>
      </div>
    `);
  }

  function aplicarFiltroAno(startYear, endYear) {
    const baseDados = getBaseData();
    if (!baseDados || !baseDados.length) return;

    const filtered = baseDados.filter(c => {
      const year = parseInt(c.year, 10);
      return !isNaN(year) && year >= startYear && year <= endYear;
    });

    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(filtered);
    else console.warn('mostrarCitacoes não encontrada para renderizar resultados');
  }

  function aplicarFiltroRanges(ranges) {
    const baseDados = getBaseData();
    if (!baseDados || !baseDados.length) return;

    const filtered = baseDados.filter(c => {
      const year = parseInt(c.year, 10);
      if (isNaN(year)) return false;
      return ranges.some(r => year >= r.start && year <= r.end);
    });

    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(filtered);
    else console.warn('mostrarCitacoes não encontrada para renderizar resultados');
  }

  function aplicarFiltroAutor(authorName) {
    const baseDados = getBaseData();
    if (!baseDados || !baseDados.length) return;  
    
    const filtered = baseDados.filter(c => {
      return c.authors && c.authors.some(a => a.toLowerCase().includes(authorName.toLowerCase()));
    });

    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(filtered);
    else console.warn('mostrarCitacoes não encontrada para renderizar resultados'); 
  }


  function resetFilters() {
    const baseDados = getBaseData();
    if (typeof mostrarCitacoes === 'function') mostrarCitacoes(baseDados);
  }

  function setupUiListeners(options = {}) {
    ensureMarkup();

    const selectors = Object.assign({
      status: 'status',
      decadeSubMenu: 'decadeSubMenu',
      decadeButtonClass: '.btn-decade',
      filterBtn: 'filterBtn',
      orderByBtn: 'orderByBtn'
    }, options);

    const statusSelect = document.getElementById(selectors.status);
    const decadeSubMenu = document.getElementById(selectors.decadeSubMenu);
    const decadeButtons = document.querySelectorAll(selectors.decadeButtonClass);

    if (statusSelect) {
      statusSelect.addEventListener('change', (event) => {
        const selectedOption = event.target.value;

        if (selectedOption === 'year-range') {
          renderYearRangeButtons();
          if (document.querySelector('.btn-decade')) {
            decadeSubMenu && decadeSubMenu.classList.remove('hidden');
          } else {
            decadeSubMenu && decadeSubMenu.classList.add('hidden');
          }
        } else {
          decadeSubMenu && decadeSubMenu.classList.add('hidden');
          document.querySelectorAll('.btn-decade').forEach(btn => btn.classList.remove('active'));
        }
      });
    }

    renderYearRangeButtons();

    const filterBtn = document.getElementById(selectors.filterBtn);
    if (filterBtn) {
      filterBtn.addEventListener('click', () => {
        const startInput = document.getElementById('startYear');
        if (!startInput) return;

        const s = parseInt(startInput.value, 10);
        if (isNaN(s)) return;

        aplicarFiltroAno(s, s);
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

    const orderByBtn = document.getElementById(selectors.orderByBtn);
    if (orderByBtn) {
      orderByBtn.addEventListener('click', () => {
        console.log('orderByBtn clicked — implementar ordenação aqui se necessário');
      });
    }
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
    applyYearRange: aplicarFiltroAno,
    reset: resetFilters
  };
})();

try {
  if (typeof window !== 'undefined') window.FilterComponent = FilterComponent;
} catch (err) {
}
























function escapeHtml(text) {
  if (text === null || text === undefined) return '-';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function obterPaperIdBd(cit) {
  if (!window.paperIdMap) return cit.paper_id || null;
  if (cit.paper_id) return cit.paper_id;

  const rawId = cit.paperId || '';
  const paperIdSemSufixo = rawId.replace(/-\d+$/, '');

  const titleNormalizado = cit.title 
    ? cit.title.toLowerCase().replace(/[^\w\s]/g, '').trim() 
    : '';

  const candidatas = [
    paperIdSemSufixo,
    cit.doi,
    cit.paperId
  ].filter(Boolean);

  for (const chave of candidatas) {
    if (window.paperIdMap[chave]) {
      return window.paperIdMap[chave];
    }
    const chaveLower = chave.toLowerCase();
    const mapaEncontrado = Object.keys(window.paperIdMap).find(
      k => k.toLowerCase() === chaveLower
    );
    if (mapaEncontrado) {
      return window.paperIdMap[mapaEncontrado];
    }
  }

  for (const [chaveMapa, uuidBd] of Object.entries(window.paperIdMap)) {
    const chaveMapaLower = chaveMapa.toLowerCase();
    const paperIdLower = paperIdSemSufixo.toLowerCase();

    if (paperIdLower && (chaveMapaLower.startsWith(paperIdLower) || paperIdLower.startsWith(chaveMapaLower))) {
      return uuidBd;
    }

    if (titleNormalizado && chaveMapaLower.replace(/[^\w\s]/g, '').trim() === titleNormalizado) {
      return uuidBd;
    }
  }

  return null;
}

function obterSearchIdAtual() {
  const radio = document.querySelector('input[name="snowballMode"]:checked');
  const mode = radio ? radio.value : 'forward';

  return mode === 'backward'
    ? (window.currentSearchIdBackward || null)
    : (window.currentSearchIdForward || null);
}

function determinarAcaoIncludeAll(citationsData) {
  if (!citationsData || citationsData.length === 0) return 'incluir';

  const allIncluded = citationsData.every(c => c.selecionado === 'incluir');
  const allExcluded = citationsData.every(c => c.selecionado === 'excluir');
  const hasNeutro = citationsData.some(c => c.selecionado == null);

  if (allIncluded) return 'excluir';
  if (allExcluded) return 'incluir';
  if (hasNeutro) return 'incluir';
  return 'excluir';
}

async function toggleIncludeAll() {
  if (!window.citationsData || window.citationsData.length === 0) {
    alert('No citations available.');
    return;
  }

  const newState = determinarAcaoIncludeAll(window.citationsData);

  window.citationsData = window.citationsData.map(c => ({
    ...c,
    selecionado: newState
  }));

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();

  const searchId = obterSearchIdAtual();

  if (searchId) {
    const isSelected = (newState === 'incluir');
    console.log(`[DB] Enviando atualização em lote (${newState}) para ${window.citationsData.length} itens...`);

    const updates = window.citationsData.map((cit, index) => {
      const paperIdBd = obterPaperIdBd(cit);

      if (!paperIdBd) {
        console.error(`[ERRO CRÍTICO] Falha ao mapear item ${index}:`, cit);
        return Promise.resolve();
      }

      return fetch('/api/articles/flag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_id: searchId,
          paper_id: paperIdBd,
          selected_first_page: isSelected
        })
      });
    });

    await Promise.all(updates);
    console.log('[DB] Sucesso: Todas as flags da busca foram salvas no PostgreSQL.');
  }
}

function atualizarBotaoIncludeAll() {
  const btn = document.getElementById('includeAllBtn');
  if (!btn) return;

  if (!window.citationsData || window.citationsData.length === 0) return;

  const acao = determinarAcaoIncludeAll(window.citationsData);

  if (acao === 'excluir') {
    btn.innerHTML = `<i class="bi bi-x-square"></i> Exclude All`;
    btn.className = 'btn btn-danger btn-export';
  } else {
    btn.innerHTML = `<i class="bi bi-check2-square"></i> Include All`;
    btn.className = 'btn btn-outline-success btn-export';
  }
}

function formatAuthors(authors) {
  if (!authors) return '-';
  if (Array.isArray(authors)) {
    if (authors.length === 0) return '-';
    return authors.map(a => a?.name || a).join('; ');
  }
  if (typeof authors === 'string') return authors;
  return '-';
}

function formatKeywords(keywords) {
  if (!keywords) return '-';
  if (Array.isArray(keywords)) {
    return keywords.length ? keywords.join(', ') : '-';
  }
  return keywords || '-';
}

function getActionLabel(selecionado) {
  if (selecionado === 'incluir') return 'Include';
  if (selecionado === 'excluir') return 'Exclude';
  return '-';
}

function looksLikeDOI(value) {
  if (!value) return false;
  const text = value.trim();
  return /^10\.\d{4,9}\/\S+$/i.test(text) || /doi\.org\/10\.\d{4,9}\/\S+/i.test(text);
}

function buildSearchURL(inputValue, type) {
  const value = inputValue.trim();
  const params = new URLSearchParams();

  if (looksLikeDOI(value)) {
    params.set('doi', value);
    params.set('title', '-');
  } else {
    params.set('doi', '-');
    params.set('title', value);
  }

  params.set('type', type);
  return `/api/articles/search?${params.toString()}`;
}

function trocarModo() {
  const mode = document.querySelector('input[name="snowballMode"]:checked').value;
  const list = mode === 'forward'
    ? (window.forwardData || [])
    : (window.backwardData || []);

  document.querySelector('#citationsList .table-title').textContent =
    mode === 'forward' ? 'Cited By' : 'References';

  const citationsSectionEl = document.getElementById('citationsSection');
  if (citationsSectionEl) citationsSectionEl.style.display = 'block';

  const mappedList = list.map((c, i) => ({
    ...c,
    paperId: `${c.paperId || c.doi || 'item'}-${i}`,
    selecionado: c.selecionado || null,
    abstractExpanded: false,
    keywordsExpanded: false
  }));
  window.rawCitationsData = mappedList;
  window.citationsData = [...mappedList];
  window.dedupApplied = false;
  const dedupBtn = document.getElementById('dedupBtn');
  if (dedupBtn) dedupBtn.innerHTML = '<i class="bi bi-filter"></i> Remove Duplicates';

  if (window.seedData) {
    mostrarResultado(window.seedData, mode);
  }

  mostrarCitacoes(window.citationsData);
}

async function buscarArtigo() {
  try {
    const input = document.getElementById('searchInput');
    const inputValue = input.value.trim();

    if (inputValue) {
      localStorage.setItem('ultimaPesquisaSnowMap', inputValue);
    }

    input.blur();

    if (!inputValue) {
      alert('Please enter a DOI or title to search.');
      return;
    }

    const navbarSearchInput = document.getElementById('navbarSearchInput');
    if (navbarSearchInput) navbarSearchInput.value = inputValue;
    document.getElementById('loadingSpinner').style.display = 'block';
    document.getElementById('resultado').innerHTML = '';
    document.getElementById('citationsSection').style.display = 'none';

    window.forwardData = null;
    window.backwardData = null;
    window.citationsData = [];
    window.seedData = null;

    const searchPromise = fetch(buildSearchURL(inputValue, 'forward'))
      .then(r => {
        if (!r.ok) throw new Error('Search failed');
        return r.json();
      });

    searchPromise
      .then(fwd => {
        window.currentSearchIdForward = fwd.search_id || null;
        window.currentSearchIdBackward = fwd.search_id_backward || null;
        window.paperIdMap = fwd.paper_id_map || {};
        console.log('[DEBUG] search_id forward:', window.currentSearchIdForward,
                    '| backward:', window.currentSearchIdBackward);
        window.forwardData = fwd.citations || [];
        window.backwardData = fwd.references || [];
        window.seedData = {
          ...fwd,
          abstractExpanded: false,
          keywordsExpanded: false
        };

        localStorage.setItem(
          'seedPaperData',
          JSON.stringify(window.seedData)
        );

        mostrarResultado(window.seedData);

        const currentMode =
          document.querySelector(
            'input[name="snowballMode"]:checked'
          ).value;
        mostrarResultado(window.seedData, currentMode);

        trocarModo();

        document.body.classList.add('busca-realizada');
      })
      .catch(err => {
        console.error(err);
        window.forwardData = [];
        window.backwardData = [];
        document.getElementById('resultado').innerHTML =
          '<p class="text-danger">Search failed.</p>';
      })
      .finally(() => {
        document.getElementById('loadingSpinner').style.display = 'none';
      });
  } catch (err) {
    console.error('buscarArtigo falhou antes de iniciar a busca:', err);
    document.getElementById('loadingSpinner').style.display = 'none';
    const resultadoEl = document.getElementById('resultado');
    if (resultadoEl) {
      resultadoEl.innerHTML = `<p class="text-danger">Unexpected error: ${err.message}</p>`;
    }
  }
}

function buscarArtigoNavbar() {
  const input = document.getElementById('navbarSearchInput');
  document.getElementById('searchInput').value = input.value;
  buscarArtigo();
}

function mostrarResultado(artigo, modo = 'forward') {
  if (!artigo || !artigo.title) {
    document.getElementById('resultado').innerHTML = '<p>Article not found.</p>';
    return;
  }

  const doiToShow = artigo.resolved_doi || artigo.input_doi || artigo.doi || '-';
  const authors = TableComponent.formatAuthors(artigo.authors);

  const contagemCitations = artigo.citations_retrieved ?? artigo.citations_count ?? artigo.citationCount ?? artigo.cited_by_count ?? '-';
  const contagemReferences = artigo.references_retrieved ?? artigo.references_count ?? '-';
  const keywordsToShow = artigo.keywords || [];
  const keywordsText = TableComponent.formatKeywords(keywordsToShow);
  const abstractText = artigo.abstract || '-';

  const cardHTML = `
  <div class="table-wrapper mb-4">
    <div class="table-topbar">
      <div class="table-info">
        <span class="table-title">Seed Paper Analysis</span>
      </div>
    </div>

    <table class="custom-table">
      <thead>
        <tr>
          </tr>
      </thead>

      <tbody>
        <tr>
          <td>
            <div class="paper-doi">
              DOI: ${TableComponent.formatDOILink(doiToShow)}
            </div>

            <div class="paper-title fw-semibold mb-2" style="font-size: 1.2rem;">
              ${TableComponent.escapeHtml(artigo.title || '-')}
            </div>

            <div class="paper-authors text-muted mb-2">
              ${TableComponent.escapeHtml(authors)}
            </div>

            <div class="paper-meta">
              <div class="paper-tags mb-3">
                ${TableComponent.formatResearchIdentityTags(artigo)}
              </div>
            </div>

            <div class="seed-paper-details">
              <div class="seed-detail-line ${window.seedData.abstractExpanded ? 'expanded' : ''}">
                <span class="seed-detail-label">Abstract</span>
                <span class="seed-detail-text">
                  ${
                    window.seedData.abstractExpanded
                      ? TableComponent.escapeHtml(abstractText)
                      : TableComponent.escapeHtml(TableComponent.truncateText(abstractText, 140).replace(/\.\.\.$/, ''))
                  }
                </span>
                ${
                  abstractText && abstractText !== '-' && abstractText.length > 140
                    ? `<span class="seed-detail-ellipsis" data-seed-toggle="abstract" role="button" tabindex="0" aria-expanded="${window.seedData.abstractExpanded ? 'true' : 'false'}">
                        ${window.seedData.abstractExpanded ? ' READ LESS' : '...'}
                      </span>`
                    : ''
                }
              </div>

              <div class="seed-detail-line ${window.seedData.keywordsExpanded ? 'expanded' : ''}">
                <span class="seed-detail-label">Keywords</span>
                <span class="seed-detail-text">
                  ${
                    window.seedData.keywordsExpanded
                      ? TableComponent.escapeHtml(keywordsText)
                      : TableComponent.escapeHtml(TableComponent.truncateText(keywordsText, 110).replace(/\.\.\.$/, ''))
                  }
                </span>
                ${
                  keywordsText && keywordsText !== '-' && keywordsText.length > 110
                    ? `<span class="seed-detail-ellipsis" data-seed-toggle="keywords" role="button" tabindex="0" aria-expanded="${window.seedData.keywordsExpanded ? 'true' : 'false'}">
                        ${window.seedData.keywordsExpanded ? ' READ LESS' : '...'}
                      </span>`
                    : ''
                }
              </div>
            </div>

            <div class="d-flex gap-4 mt-3 pt-3 border-top">
              <div class="citation-box d-flex align-items-center gap-2">
                <div class="citation-dot" style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;"></div>
                <div>
                  <span class="citation-number fw-bold">${TableComponent.escapeHtml(String(contagemCitations))}</span>
                  <span class="citation-label text-muted" style="font-size: 0.85rem;"> Citations</span>
                </div>
              </div>

              <div class="citation-box d-flex align-items-center gap-2">
                <div class="citation-dot" style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;"></div>
                <div>
                  <span class="citation-number fw-bold">${TableComponent.escapeHtml(String(contagemReferences))}</span>
                  <span class="citation-label text-muted" style="font-size: 0.85rem;"> References</span>
                </div>
              </div>
            </div>

          </td>
        </tr>
      </tbody>
    </table>
  </div>
  `;
  document.getElementById('resultado').innerHTML = cardHTML;

  document.getElementById('resultado').onclick = function (e) {
    const toggle = e.target.closest('[data-seed-toggle]');
    if (toggle) {
      const target = toggle.dataset.seedToggle;
      if (target === 'abstract') {
        window.seedData.abstractExpanded = !window.seedData.abstractExpanded;
      }
      if (target === 'keywords') {
        window.seedData.keywordsExpanded = !window.seedData.keywordsExpanded;
      }
      const currentMode = document.querySelector('input[name="snowballMode"]:checked').value;
      mostrarResultado(window.seedData, currentMode);
    }
  };

  document.getElementById('resultado').onkeydown = function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const toggle = e.target.closest('[data-seed-toggle]');
    if (!toggle) return;
    e.preventDefault();
    toggle.click();
  };
}

function mostrarCitacoes(citacoes) {
  const tbody = document.querySelector('#tabela-triagem tbody');
  if (!tbody) return;

  if (typeof TableComponent === 'undefined') {
    console.error('TableComponent não foi encontrado. Verifique se o table.js foi carregado.');
    return;
  }

  TableComponent.render({
    target: tbody,
    data: citacoes,
    showActions: true,
    onAction: async (item, acao) => {
      const paperIdBd = obterPaperIdBd(item);
      const searchId = obterSearchIdAtual();

      if (paperIdBd && searchId) {
        const isSelected = (acao === 'incluir');
        await fetch('/api/articles/flag', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            search_id: searchId,
            paper_id: paperIdBd,
            selected_first_page: isSelected
          })
        });
      }

      if (typeof atualizarContadores === 'function') {
        atualizarContadores();
      }
      if (typeof atualizarBotaoIncludeAll === 'function') {
        atualizarBotaoIncludeAll();
      }
      mostrarCitacoes(citacoes);
    }
  });

  if (typeof atualizarContadores === 'function') {
    atualizarContadores();
  }
}

function marcarArtigoLocal(paperId, acao) {
  const cit = window.citationsData.find(c => c.paperId === paperId);
  if (!cit) {
    alert('Citation not found for local marking.');
    return;
  }

  cit.selecionado = acao;
  mostrarCitacoes(window.citationsData);
}

function baixarCitationsCSV() {
  const citations = (window.citationsData || []).filter(
    c => c.selecionado === 'incluir' || c.selecionado === 'excluir'
  );

  if (!citations.length) {
    alert('No selected citations to export.');
    return;
  }

  let csvContent = "Title,Abstract,Authors,Year,Venue,DOI,Cited by,Open Access,URL,Keywords,Language,Pages,Actions\n";

  citations.forEach(cit => {
    const title = `"${String(cit.title || '-').replace(/"/g, '""')}"`;
    const abstract = `"${String(cit.abstract || '-').replace(/"/g, '""')}"`;
    const authors = `"${TableComponent.formatAuthors(cit.authors).replace(/"/g, '""')}"`;
    const year = `"${String(cit.year || '-').replace(/"/g, '""')}"`;
    const venue = `"${String(cit.venue || '-').replace(/"/g, '""')}"`;
    const doi = `"${String(cit.doi || '-').replace(/"/g, '""')}"`;
    const citedBy = `"${String(cit.citations_count ?? cit.citationCount ?? cit.cited_by_count ?? '-').replace(/"/g, '""')}"`;
    const openAccess = `"${String(cit.open_access ?? '-').replace(/"/g, '""')}"`;
    const url = `"${String(cit.url || '-').replace(/"/g, '""')}"`;
    const keywords = `"${(cit.keywords || []).join('; ').replace(/"/g, '""')}"`;
    const language = `"${String(cit.language || '-').replace(/"/g, '""')}"`;
    const pages = `"${String(cit.numpages != null ? cit.numpages : cit.pages || '-').replace(/"/g, '""')}"`;
    const action = `"${String(getActionLabel(cit.selecionado)).replace(/"/g, '""')}"`;

    csvContent += `${title},${abstract},${authors},${year},${venue},${doi},${citedBy},${openAccess},${url},${keywords},${language},${pages},${action}\n`;
  });

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = 'selected_citations.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function irParaTriagem() {
  if (!window.citationsData || window.citationsData.length === 0) {
    alert('No citations to send to screening.');
    return;
  }
  window.name = JSON.stringify(window.citationsData);
  window.location.href = 'analysis.html';
}

function normalizeDoi(doi) {
  if (!doi || doi === '-') return null;
  return doi.trim().toLowerCase()
    .replace(/^https?:\/\/doi\.org\//, '')
    .replace(/^doi:/, '');
}

function normalizeTitleJs(title) {
  if (!title || title === '-') return '';
  return title.trim().toLowerCase().replace(/[^\w\s]/g, '').replace(/\s+/g, ' ');
}

function findDuplicateGroups(list) {
  const groups = {};
  list.forEach(item => {
    const doi = normalizeDoi(item.doi);
    const key = doi ? `doi:${doi}` : `title:${normalizeTitleJs(item.title)}`;
    if (!key || key === 'doi:null' || key === 'title:') return;
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  });
  return Object.values(groups).filter(g => g.length > 1);
}

function openDedupModal() {
  const groups = findDuplicateGroups(window.citationsData || []);
  const body = document.getElementById('dedupModalBody');

  if (groups.length === 0) {
    body.innerHTML = '<p class="text-muted">No duplicates found in the current list.</p>';
  } else {
    body.innerHTML = groups.map((group, gi) => `
      <div class="mb-4">
        <div class="fw-bold mb-2 text-secondary" style="font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">
          Group ${gi + 1} — ${group.length} duplicates
        </div>
        ${group.map(item => `
          <div class="d-flex align-items-start gap-2 p-2 mb-1 rounded" style="border:1px solid #e0e0e0; background:#fafafa;">
            <input type="checkbox" class="dedup-checkbox form-check-input mt-1 flex-shrink-0" value="${TableComponent.escapeHtml(item.paperId)}" id="dedup-${TableComponent.escapeHtml(item.paperId)}">
            <label for="dedup-${TableComponent.escapeHtml(item.paperId)}" class="mb-0" style="cursor:pointer; font-size:0.9rem;">
              <div class="fw-semibold">${TableComponent.escapeHtml(item.title || '-')}</div>
              <div class="text-muted" style="font-size:0.8rem;">
                ${TableComponent.escapeHtml(String(item.year || '-'))} · ${TableComponent.escapeHtml(item.venue || '-')} · DOI: ${TableComponent.escapeHtml(item.doi || '-')}
              </div>
            </label>
          </div>
        `).join('')}
      </div>
    `).join('<hr>');
  }

  new bootstrap.Modal(document.getElementById('dedupModal')).show();
}

async function removeDedupSelected() {
  const checked = new Set(
    [...document.querySelectorAll('.dedup-checkbox:checked')].map(cb => cb.value)
  );

  if (checked.size === 0) return;

  const itensParaRemover = (window.citationsData || []).filter(c => checked.has(c.paperId));
  const searchId = obterSearchIdAtual();

  if (searchId && itensParaRemover.length > 0) {
    console.log(`[DB] Marcando ${itensParaRemover.length} itens como excluded_duplicate no PostgreSQL...`);

    const updates = itensParaRemover.map(cit => {
      const paperIdBd = obterPaperIdBd(cit);

      if (!paperIdBd) {
        console.error('[ERRO DB] Não foi possível obter UUID para a duplicata:', cit);
        return Promise.resolve();
      }

      return fetch('/api/articles/flag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          search_id: searchId,
          paper_id: paperIdBd,
          excluded_duplicate: true
        })
      });
    });

    await Promise.all(updates);
    console.log('[DB] Sucesso: Duplicatas atualizadas com excluded_duplicate = TRUE.');
  }

  window.citationsData = (window.citationsData || []).filter(c => !checked.has(c.paperId));

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();

  const modalElem = document.getElementById('dedupModal');
  if (modalElem) {
    const modalInstance = bootstrap.Modal.getInstance(modalElem);
    if (modalInstance) modalInstance.hide();
  }
}

document.querySelectorAll('input[name="snowballMode"]').forEach(radio => {
  radio.addEventListener('change', () => {
    const navRadio = document.getElementById(radio.value === 'forward' ? 'navbarModeForward' : 'navbarModeBackward');
    if (navRadio) navRadio.checked = true;
    if (window.forwardData !== null && window.backwardData !== null) trocarModo();
  });
});

document.addEventListener('DOMContentLoaded', () => {
  const downloadBtn = document.getElementById('downloadBtn');
  const includeAllBtn = document.getElementById('includeAllBtn');

  if (downloadBtn) downloadBtn.onclick = baixarCitationsCSV;
  if (includeAllBtn) includeAllBtn.onclick = toggleIncludeAll;

  atualizarBotaoIncludeAll();

  const linkAnalise = document.querySelector('a.nav-link[href="analysis.html"]');
  if (linkAnalise) {
    linkAnalise.addEventListener('click', e => {
      e.preventDefault();
      if (!window.citationsData || window.citationsData.length === 0) {
        alert('No citations to send to screening.');
        return;
      }

      const incluidos = window.citationsData.filter(c => c.selecionado === 'incluir');

      if (incluidos.length === 0) {
        alert('No article marked as "Include"');
        return;
      }

      window.name = JSON.stringify(window.citationsData);
      window.location.href = 'analysis.html';
    });
  }

  const linkCriterios = document.querySelector('a.nav-link[href="criterios.html"]');
  if (linkCriterios) {
    linkCriterios.addEventListener('click', e => {
      e.preventDefault();

      if (!window.citationsData || window.citationsData.length === 0) {
        alert('No citations to send.');
        return;
      }

      const incluidos = window.citationsData.filter(c => c.selecionado === 'incluir');

      if (incluidos.length === 0) {
        alert('No article marked as "Include"');
        return;
      }

      window.name = JSON.stringify(incluidos);
      window.location.href = 'criterios.html';
    });
  }
});
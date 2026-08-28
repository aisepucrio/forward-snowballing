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

// Mudanças de flag marcadas na tela mas ainda não gravadas no banco.
// Chave: "search_id:paper_id" -> { search_id, paper_id, selected_first_page?, excluded_duplicate? }
// Só viram UPDATE de fato quando o usuário clica em "Save Research State",
// pra não abrir uma conexão com o Postgres a cada clique de include/exclude.
window.pendingFlagChanges = window.pendingFlagChanges || {};

function queueFlagChange({ searchId, paperId, selectedFirstPage, excludedDuplicate }) {
  if (!searchId || !paperId) return;

  const key = `${searchId}:${paperId}`;
  const existing = window.pendingFlagChanges[key] || { search_id: searchId, paper_id: paperId };

  if (selectedFirstPage !== undefined) existing.selected_first_page = selectedFirstPage;
  if (excludedDuplicate !== undefined) existing.excluded_duplicate = excludedDuplicate;

  window.pendingFlagChanges[key] = existing;
  atualizarBotaoSalvar();
}

function atualizarBotaoSalvar() {
  const btn = document.getElementById('saveStateBtn');
  if (!btn) return;

  const count = Object.keys(window.pendingFlagChanges || {}).length;
  btn.disabled = count === 0;
  btn.innerHTML = count > 0
    ? `<i class="bi bi-cloud-arrow-up"></i> Save Research State (${count})`
    : `<i class="bi bi-cloud-check"></i> Save Research State`;
}

async function salvarEstadoPesquisa() {
  const updates = Object.values(window.pendingFlagChanges || {});
  if (updates.length === 0) return;

  const btn = document.getElementById('saveStateBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
  }

  try {
    const res = await fetch('/api/articles/flag/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates })
    });

    if (!res.ok) throw new Error('Save failed');

    window.pendingFlagChanges = {};
    console.log(`[DB] Sucesso: ${updates.length} mudança(s) gravada(s) no PostgreSQL.`);

    if (btn) {
      btn.innerHTML = '<i class="bi bi-check2"></i> Saved!';
      setTimeout(atualizarBotaoSalvar, 1500);
    }
  } catch (err) {
    console.error('[ERRO DB] Falha ao salvar estado da pesquisa:', err);
    alert('Failed to save research state. Your selections are kept locally — please try again.');
    atualizarBotaoSalvar();
  }
}

function haPendenciasNaoSalvas() {
  return Object.keys(window.pendingFlagChanges || {}).length > 0;
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

    window.citationsData.forEach((cit, index) => {
      const paperIdBd = obterPaperIdBd(cit);

      if (!paperIdBd) {
        console.error(`[ERRO CRÍTICO] Falha ao mapear item ${index}:`, cit);
        return;
      }

      queueFlagChange({ searchId, paperId: paperIdBd, selectedFirstPage: isSelected });
    });
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

// O card do seed article ("Seed Paper Analysis") mostra Citations/References
// a partir de window.seedData.citations_retrieved / references_retrieved —
// um snapshot estático tirado direto da busca original. Remover duplicatas
// no popup só mexe em window.citationsData (a lista da tabela abaixo); sem
// isso aqui, o card do seed nunca refletia a remoção, mesmo com a tabela já
// atualizada.
function sincronizarContagemSeed() {
  if (!window.seedData) return;

  const modeInput = document.querySelector('input[name="snowballMode"]:checked');
  const mode = modeInput ? modeInput.value : 'forward';
  const count = (window.citationsData || []).length;

  if (mode === 'forward') {
    window.seedData.citations_retrieved = count;
  } else {
    window.seedData.references_retrieved = count;
  }

  mostrarResultado(window.seedData, mode);
}

function trocarModo() {
  const mode = document.querySelector('input[name="snowballMode"]:checked').value;
  const list = mode === 'forward'
    ? (window.forwardData || [])
    : (window.backwardData || []);

  document.querySelector('#citationsList .table-title').textContent =
    mode === 'forward' ? 'Cited By' : 'References';

  const citationsSectionEl = document.getElementById('citationsList');
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
  window.dedupRemovedHistory = []; // reset on new search, so old removals don't bleed into a new dataset
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

    const citationsSectionEl = document.getElementById('citationsList');
    if (citationsSectionEl) citationsSectionEl.style.display = 'none';

    window.forwardData = null;
    window.backwardData = null;
    window.citationsData = [];
    window.seedData = null;
    window.pendingFlagChanges = {}; // nova busca, nova search_id: descarta pendências da busca anterior
    atualizarBotaoSalvar();

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
    onAction: (item, acao) => {
      const paperIdBd = obterPaperIdBd(item);
      const searchId = obterSearchIdAtual();

      if (paperIdBd && searchId) {
        const isSelected = (acao === 'incluir');
        queueFlagChange({ searchId, paperId: paperIdBd, selectedFirstPage: isSelected });
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

// A busca já funde automaticamente quando o DOI bate exato (ver
// build_dedup_key no backend) — o que sobra pra revisão manual é sobretudo
// o caso em que só um dos dois lados tem DOI (ou nenhum), mas o título é
// idêntico. Um dicionário com uma chave só (doi OU título, com prioridade)
// não pega esse caso, porque os dois itens caem em chaves diferentes
// ("doi:X" vs "title:Y") mesmo sendo o mesmo artigo. Por isso agrupa por
// união: dois itens ficam no mesmo grupo se compartilham DOI OU título
// idêntico (normalizado, sem fuzzy match).
function findDuplicateGroups(list) {
  const parent = list.map((_, i) => i);
  function find(i) {
    while (parent[i] !== i) {
      parent[i] = parent[parent[i]];
      i = parent[i];
    }
    return i;
  }
  function union(a, b) {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  }

  const byDoi = {};
  const byTitle = {};
  list.forEach((item, i) => {
    const doi = normalizeDoi(item.doi);
    if (doi) {
      if (byDoi[doi] !== undefined) union(i, byDoi[doi]);
      else byDoi[doi] = i;
    }

    const title = normalizeTitleJs(item.title);
    if (title) {
      if (byTitle[title] !== undefined) union(i, byTitle[title]);
      else byTitle[title] = i;
    }
  });

  const groups = {};
  list.forEach((item, i) => {
    const root = find(i);
    if (!groups[root]) groups[root] = [];
    groups[root].push(item);
  });
  return Object.values(groups).filter(g => g.length > 1);
}

// Duplicate review follows the "Visualiza duplicatas -> Compara 2 duplicatas ->
// Existem novas duplicatas?" loop from process.bpmn: one pair is shown at a time,
// instead of every duplicate group at once with bulk checkboxes.
function openDedupModal() {
  const groups = findDuplicateGroups(window.citationsData || []).map(group => [...group]);

  window.dedupState = {
    groups,
    groupIndex: 0,
    toRemove: new Set() // paperId -> marked for removal once the review is confirmed
  };

  document.getElementById('dedupModalBody').innerHTML = `
    <div id="dedupRemovedSection"></div>
    <div id="dedupActiveSection"></div>
  `;
  renderDedupRemovedSection();
  renderDedupStep();
  new bootstrap.Modal(document.getElementById('dedupModal')).show();
}

// Shows duplicates already removed in this session (across previous times the
// modal was opened/closed), each with an "Desfazer" button, so reopening the
// modal after a removal doesn't hide what was already decided.
function renderDedupRemovedSection() {
  const el = document.getElementById('dedupRemovedSection');
  if (!el) return;

  const history = window.dedupRemovedHistory || [];
  if (history.length === 0) {
    el.innerHTML = '';
    return;
  }

  el.innerHTML = `
    <div class="mb-3">
      <div class="fw-bold mb-2 text-secondary" style="font-size:0.8rem; text-transform:uppercase; letter-spacing:0.05em;">
        Duplicatas já removidas (${history.length})
      </div>
      ${history.map(entry => `
        <div class="d-flex justify-content-between align-items-start gap-2 p-2 mb-1 rounded" style="border:1px solid #f0d0d0; background:#fff5f5;">
          <div style="font-size:0.85rem; min-width:0;">
            <div class="fw-semibold">${TableComponent.escapeHtml(entry.item.title || '-')}</div>
            <div class="text-muted" style="font-size:0.78rem;">
              ${TableComponent.escapeHtml(String(entry.item.year || '-'))} · DOI: ${TableComponent.escapeHtml(entry.item.doi || '-')}
            </div>
          </div>
          <button type="button" class="btn btn-outline-primary btn-sm flex-shrink-0" onclick="undoDedupRemoval('${TableComponent.escapeHtml(entry.item.paperId)}')">
            Desfazer
          </button>
        </div>
      `).join('')}
    </div>
    <hr>
  `;
}

function undoDedupRemoval(paperId) {
  const history = window.dedupRemovedHistory || [];
  const idx = history.findIndex(entry => entry.item.paperId === paperId);
  if (idx === -1) return;

  const [entry] = history.splice(idx, 1);
  window.citationsData = [...(window.citationsData || []), entry.item];

  const searchId = obterSearchIdAtual();
  const paperIdBd = obterPaperIdBd(entry.item);
  if (searchId && paperIdBd) {
    queueFlagChange({ searchId, paperId: paperIdBd, excludedDuplicate: false });
  }

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
  sincronizarContagemSeed();
  renderDedupRemovedSection();
}

function currentDedupPair() {
  const state = window.dedupState;
  if (!state) return null;

  while (state.groupIndex < state.groups.length) {
    const group = state.groups[state.groupIndex];
    if (group.length >= 2) {
      return { left: group[0], right: group[1] };
    }
    state.groupIndex++;
  }
  return null;
}

function countRemainingDedupPairs() {
  const state = window.dedupState;
  if (!state) return 0;
  return state.groups
    .slice(state.groupIndex)
    .reduce((total, group) => total + Math.max(group.length - 1, 0), 0);
}

function renderDedupCard(item, keepAction) {
  const abstract = item.abstract && item.abstract !== '-' ? item.abstract : '';
  const snippet = abstract.length > 220 ? `${abstract.slice(0, 220)}…` : abstract;

  return `
    <div class="flex-fill p-3 rounded" style="border:1px solid #e0e0e0; background:#fafafa; min-width:0;">
      <div class="fw-semibold mb-1">${TableComponent.escapeHtml(item.title || '-')}</div>
      <div class="text-muted mb-2" style="font-size:0.8rem;">
        ${TableComponent.escapeHtml(String(item.year || '-'))} · ${TableComponent.escapeHtml(item.venue || '-')}<br>
        DOI: ${TableComponent.escapeHtml(item.doi || '-')}
      </div>
      ${snippet ? `<p class="mb-3" style="font-size:0.82rem;">${TableComponent.escapeHtml(snippet)}</p>` : ''}
      <button type="button" class="btn btn-outline-danger btn-sm w-100" onclick="resolveDedupPair('${keepAction}')">
        Manter este, remover o outro
      </button>
    </div>
  `;
}

function renderDedupStep() {
  const body = document.getElementById('dedupActiveSection') || document.getElementById('dedupModalBody');
  const state = window.dedupState;
  const pair = currentDedupPair();

  if (!pair) {
    const reviewed = state && state.toRemove.size > 0;
    const hadGroups = state && state.groups.length > 0;
    body.innerHTML = `<p class="text-muted mb-0">${
      reviewed
        ? 'Revisão concluída. Feche para aplicar as remoções.'
        : hadGroups
          ? 'Nenhuma duplicata pendente — todos os grupos já foram revisados.'
          : 'Nenhuma duplicata encontrada na lista atual.'
    }</p>`;
    return;
  }

  const remaining = countRemainingDedupPairs();
  const groupNumber = state.groupIndex + 1;
  const totalGroups = state.groups.length;
  body.innerHTML = `
    <p class="text-muted small mb-3">
      Grupo ${groupNumber} de ${totalGroups} — restam ${remaining} ${remaining === 1 ? 'comparação' : 'comparações'} no total.
    </p>
    <div class="d-flex gap-3 flex-column flex-md-row">
      ${renderDedupCard(pair.left, 'keep-left')}
      ${renderDedupCard(pair.right, 'keep-right')}
    </div>
    <div class="text-center mt-3">
      <button type="button" class="btn btn-outline-secondary btn-sm" onclick="resolveDedupPair('keep-both')">
        Não são duplicatas — manter os dois
      </button>
    </div>
  `;
}

function resolveDedupPair(decision) {
  const state = window.dedupState;
  if (!state) return;

  const group = state.groups[state.groupIndex];
  if (!group || group.length < 2) return;

  if (decision === 'keep-left') {
    state.toRemove.add(group[1].paperId);
    group.splice(1, 1);
  } else if (decision === 'keep-right') {
    state.toRemove.add(group[0].paperId);
    group.shift();
  } else {
    // keep-both: not duplicates, stop comparing this pair but keep both articles
    group.splice(1, 1);
  }

  renderDedupStep();
}

// Triggered by the modal's own 'hidden.bs.modal' event, so any way of closing it
// (X button, backdrop click, Escape, or the Close button) applies whatever
// duplicate decisions were made so far — matching the BPMN's "Existem novas
// duplicatas? -> Não -> Seleciona artigos" transition.
function finishDedupReview() {
  const state = window.dedupState;
  window.dedupState = null;

  if (!state || state.toRemove.size === 0) return;

  const itensParaRemover = (window.citationsData || []).filter(c => state.toRemove.has(c.paperId));

  // A tabela atualiza já, na hora — não espera o POST no banco. Antes disso
  // vinha depois de um `await Promise.all(updates)` sem try/catch: se
  // qualquer POST falhasse (rede, banco fora do ar), a exceção não tratada
  // abortava a função e as duplicatas nunca saíam da tabela, mesmo com o
  // popup já fechado.
  window.citationsData = (window.citationsData || []).filter(c => !state.toRemove.has(c.paperId));
  window.dedupRemovedHistory = [
    ...(window.dedupRemovedHistory || []),
    ...itensParaRemover.map(item => ({ item, removedAt: Date.now() }))
  ];

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
  sincronizarContagemSeed();

  const searchId = obterSearchIdAtual();
  if (searchId && itensParaRemover.length > 0) {
    itensParaRemover.forEach(cit => {
      const paperIdBd = obterPaperIdBd(cit);

      if (!paperIdBd) {
        console.error('[ERRO DB] Não foi possível obter UUID para a duplicata:', cit);
        return;
      }

      queueFlagChange({ searchId, paperId: paperIdBd, excludedDuplicate: true });
    });

    Promise.all(updates)
      .then(() => console.log('[DB] Sucesso: Duplicatas atualizadas com excluded_duplicate = TRUE.'))
      .catch(err => console.error('[ERRO DB] Falha ao gravar excluded_duplicate:', err));
  }
}

const dedupModalElem = document.getElementById('dedupModal');
if (dedupModalElem) {
  dedupModalElem.addEventListener('hidden.bs.modal', finishDedupReview);
}

// Avisa antes de fechar/recarregar a aba se houver marcações ainda não
// gravadas no banco (o usuário precisa clicar em "Save Research State").
window.addEventListener('beforeunload', (e) => {
  if (haPendenciasNaoSalvas()) {
    e.preventDefault();
    e.returnValue = '';
  }
});

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
  const saveStateBtn = document.getElementById('saveStateBtn');

  if (downloadBtn) downloadBtn.onclick = baixarCitationsCSV;
  if (includeAllBtn) includeAllBtn.onclick = toggleIncludeAll;
  if (saveStateBtn) saveStateBtn.onclick = salvarEstadoPesquisa;

  atualizarBotaoIncludeAll();
  atualizarBotaoSalvar();

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

      if (haPendenciasNaoSalvas() && !confirm('You have unsaved changes to the research state. Leave this page and discard them?')) {
        return;
      }

      // guarda o search_id ativo pra sobreviver à navegação (analysis.html
      // e, a partir dela, criterios.html precisam dele pra gravar criteria/
      // criteria_logs, mas window.currentSearchId* só existe em memória aqui)
      localStorage.setItem('currentSearchId', obterSearchIdAtual() || '');

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

      if (haPendenciasNaoSalvas() && !confirm('You have unsaved changes to the research state. Leave this page and discard them?')) {
        return;
      }

      // idem: criterios.js lê isso do localStorage pra saber a qual search_id
      // gravar os critérios/vereditos da LLM
      localStorage.setItem('currentSearchId', obterSearchIdAtual() || '');

      window.name = JSON.stringify(incluidos);
      window.location.href = 'criterios.html';
    });
  }
});
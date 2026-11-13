const SEED_STATUS_OK = ['ok'];

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
    persistirEstado();
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

  window.citationsData.forEach(c => {
    c.selecionado = newState;
  });

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

  persistirEstado();
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

function obterModoAtual() {
  const radio = document.querySelector('input[name="snowballMode"]:checked');
  return radio ? radio.value : 'forward';
}

function seedTemResultado(seed) {
  return !!seed && SEED_STATUS_OK.includes(seed.status);
}

function listaDaAba(mode, aba = window.activeSeedTab) {
  const base = mode === 'forward' ? window.forwardData : window.backwardData;
  if (!Array.isArray(base)) return [];

  let lista = base;
  if (aba !== 'all' && aba !== null && aba !== undefined && Array.isArray(window.seedsInfo)) {
    const seed = window.seedsInfo[aba];
    const chaves = seed ? (mode === 'forward' ? seed.citation_keys : seed.reference_keys) : [];
    const porChave = mode === 'forward' ? window.forwardByKey : window.backwardByKey;
    lista = (chaves || []).map(chave => porChave && porChave.get(chave)).filter(Boolean);
  }

  return lista.filter(item => !item.removedAsDuplicate);
}

function objetoDoCardAtual() {
  if (window.activeSeedTab === 'all') return window.allSeedsSummary || null;
  return (window.seedsInfo || [])[window.activeSeedTab] || null;
}

function selecionarAbaSeed(aba) {
  window.activeSeedTab = aba === 'all' ? 'all' : Number(aba);
  trocarModo();
}

function estudosIncluidos() {
  return SearchState.unicosIncluidos(window.forwardData, window.backwardData);
}

function sincronizarContagemSeed() {
  const card = objetoDoCardAtual();
  if (!card) return;

  card.citations_retrieved = listaDaAba('forward').length;
  card.references_retrieved = listaDaAba('backward').length;
  window.seedData = card;

  mostrarResultado(card, obterModoAtual());
}

function trocarModo() {
  const mode = obterModoAtual();

  document.querySelector('#citationsList .table-title').textContent =
    mode === 'forward' ? 'Cited By' : 'References';

  const citationsSectionEl = document.getElementById('citationsList');
  if (citationsSectionEl) citationsSectionEl.style.display = 'block';

  const lista = listaDaAba(mode);
  window.rawCitationsData = lista;
  window.citationsData = [...lista];
  window.allCitationsData = window.citationsData;
  window.dedupApplied = false;
  window.dedupHistoryByMode = window.dedupHistoryByMode || {};
  window.dedupRemovedHistory = window.dedupHistoryByMode[mode] || [];

  if (window.FilterComponent) {
    if (typeof window.FilterComponent.clearActiveFilters === 'function') {
      window.FilterComponent.clearActiveFilters();
    }
    if (typeof window.FilterComponent.refreshOpenSubmenu === 'function') {
      window.FilterComponent.refreshOpenSubmenu();
    }
  }
  const dedupBtn = document.getElementById('dedupBtn');
  if (dedupBtn) dedupBtn.innerHTML = '<i class="bi bi-filter"></i> Remove Duplicates';

  sincronizarContagemSeed();

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
  persistirEstado();
}

function persistirEstado() {
  SearchState.salvarTriagem({
    forward: window.forwardData,
    backward: window.backwardData,
    view: { tab: window.activeSeedTab, mode: obterModoAtual() },
    pending: window.pendingFlagChanges || {},
  });

  try {
    localStorage.setItem('currentSearchId', obterSearchIdAtual() || '');
  } catch {
  }
}

function limparTriagemDeArtigosOcultos(baseDados, artigosVisiveis) {
  const modo = obterModoAtual();
  const visiveis = new Set((artigosVisiveis || []).map(item => item.paperId));
  const ocultos = (baseDados || []).filter(item => !visiveis.has(item.paperId));

  if (!ocultos.length) return;

  const searchId = obterSearchIdAtual();
  ocultos.forEach(item => {
    if (item.selecionado !== 'incluir' && item.selecionado !== 'excluir') return;

    item.selecionado = null;
    const paperIdBd = obterPaperIdBd(item);
    if (paperIdBd && searchId) {
      queueFlagChange({
        searchId,
        paperId: paperIdBd,
        selectedFirstPage: false,
      });
    }
  });

  SearchState.limparTriagem(ocultos, modo);
  persistirEstado();
}

window.onTableFilterApplied = limparTriagemDeArtigosOcultos;

function aplicarResultadoBusca(resultado) {
  const estado = SearchState.ler();

  window.currentSearchIdForward = resultado.search_id || null;
  window.currentSearchIdBackward = resultado.search_id_backward || null;
  window.paperIdMap = resultado.paper_id_map || {};

  window.forwardData = SearchState.aplicarTriagem(
    SearchState.prepararEstudos(resultado.citations), 'forward', estado);
  window.backwardData = SearchState.aplicarTriagem(
    SearchState.prepararEstudos(resultado.references), 'backward', estado);
  window.forwardByKey = new Map(window.forwardData.map(item => [item.paperId, item]));
  window.backwardByKey = new Map(window.backwardData.map(item => [item.paperId, item]));

  const removidas = lista => lista
    .filter(item => item.removedAsDuplicate)
    .map(item => ({ item, removedAt: Date.now() }));
  window.dedupHistoryByMode = {
    forward: removidas(window.forwardData),
    backward: removidas(window.backwardData),
  };

  window.pendingFlagChanges = estado.pending || {};

  window.seedsInfo = (resultado.seeds || []).map(seed => ({
    ...seed,
    abstractExpanded: false,
    keywordsExpanded: false
  }));
  window.allSeedsSummary = {
    isSummary: true,
    title: 'All seeds',
    citations_retrieved: window.forwardData.length,
    references_retrieved: window.backwardData.length,
  };

  const abaSalva = estado.view && estado.view.tab;
  const abaValida = abaSalva === 'all' ||
    (Number.isInteger(abaSalva) && abaSalva >= 0 && abaSalva < window.seedsInfo.length);
  window.activeSeedTab = window.seedsInfo.length > 1 ? (abaValida ? abaSalva : 'all') : 0;
  window.mostrarTagsSeed = true;

  const modoSalvo = estado.view && estado.view.mode === 'backward' ? 'backward' : 'forward';
  const radio = document.getElementById(modoSalvo === 'backward' ? 'modeBackward' : 'modeForward');
  if (radio) radio.checked = true;

  const toggle = document.getElementById('snowballModeToggle');
  if (toggle) toggle.style.display = '';

  const saveStateBtn = document.getElementById('saveStateBtn');
  if (saveStateBtn) {
    saveStateBtn.style.display = (window.currentSearchIdForward || window.currentSearchIdBackward) ? '' : 'none';
  }

  try {
    const seedsParaDashboard = window.seedsInfo
      .filter(seedTemResultado)
      .map(({ citation_keys, reference_keys, ...seed }) => seed);
    localStorage.setItem('seedsData', JSON.stringify(seedsParaDashboard));
    localStorage.removeItem('seedPaperData');
  } catch (err) {
    console.warn('Não foi possível guardar as seeds para o dashboard:', err);
  }

  atualizarBotaoSalvar();
  trocarModo();
}

function mostrarSemResultados(mensagem = 'There is no search result to show yet.') {
  document.getElementById('resultado').innerHTML =
    `<p class="text-muted">${escapeHtml(mensagem)} <a href="index.html">Go to the seed search</a>.</p>`;
}

async function carregarResultados() {
  const loading = document.getElementById('loadingSpinner');
  try {
    const resultado = await SearchState.buscarUltimoResultado();
    if (!resultado || resultado.error) {
      mostrarSemResultados();
      return;
    }
    aplicarResultadoBusca(resultado);
  } catch (err) {
    console.error(err);
    mostrarSemResultados('Could not load your last search. Try again, or start a new search.');
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

function buscarArtigoNavbar() {
  const input = document.getElementById('navbarSearchInput');
  const valor = input ? input.value.trim() : '';
  window.location.href = valor ? `index.html?search=${encodeURIComponent(valor)}` : 'index.html';
}

function construirAbasSeeds() {
  const seeds = window.seedsInfo;
  if (!Array.isArray(seeds) || seeds.length < 2) return '';

  const ativa = window.activeSeedTab;
  const aba = (valor, conteudo, titulo, extraClasse = '') => {
    const selecionada = String(ativa) === String(valor);
    return `
      <button type="button" class="seed-tab ${selecionada ? 'active' : ''} ${extraClasse}" role="tab"
              aria-selected="${selecionada ? 'true' : 'false'}" data-seed-tab="${valor}" title="${escapeHtml(titulo)}">
        ${conteudo}
      </button>`;
  };

  const abas = [aba('all', '<i class="bi bi-collection"></i> All seeds', 'All seeds')];
  seeds.forEach((seed, i) => {
    const nome = seed.title || seed.input_value || `Seed ${i + 1}`;
    const falhou = !seedTemResultado(seed);
    abas.push(aba(
      i,
      `<span class="seed-tab-index">S${i + 1}</span>
       <span class="seed-tab-name">${escapeHtml(TableComponent.truncateText(nome, 32))}</span>
       ${falhou ? '<i class="bi bi-exclamation-circle seed-tab-alert" aria-label="No results"></i>' : ''}`,
      nome,
      falhou ? 'seed-tab-failed' : ''
    ));
  });

  return `<div class="seed-tabs" role="tablist" aria-label="Seed papers">${abas.join('')}</div>`;
}

function rotuloStatusSeed(seed) {
  if (seed.status === 'not_found') return 'Not found';
  if (seed.status === 'duplicate') return `Same paper as S${(seed.duplicate_of ?? 0) + 1}`;
  if (seed.status === 'error') return 'Search failed';
  return 'OK';
}

function caixaContagem(numero, rotulo) {
  return `
    <div class="citation-box d-flex align-items-center gap-2">
      <div class="citation-dot" style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;"></div>
      <div>
        <span class="citation-number fw-bold">${TableComponent.escapeHtml(String(numero))}</span>
        <span class="citation-label text-muted" style="font-size: 0.85rem;"> ${rotulo}</span>
      </div>
    </div>`;
}

function conteudoCardResumo(resumo) {
  const seeds = window.seedsInfo || [];
  const comResultado = seeds.filter(seedTemResultado).length;

  return `
    <div class="paper-title fw-semibold mb-2" style="font-size: 1.2rem;">All seeds</div>
    <div class="paper-authors text-muted mb-3">
      ${comResultado} of ${seeds.length} seeds returned results · studies found by more than one seed appear once
    </div>
    <ul class="seed-summary-list">
      ${seeds.map((seed, i) => `
        <li class="seed-summary-item">
          <button type="button" class="seed-summary-link" data-seed-tab="${i}">
            <span class="seed-tab-index">S${i + 1}</span>
            <span class="seed-summary-name">${escapeHtml(seed.title || seed.input_value || '-')}</span>
          </button>
          <span class="seed-status seed-status-${escapeHtml(seed.status)}">${escapeHtml(rotuloStatusSeed(seed))}</span>
          ${seedTemResultado(seed)
            ? `<span class="seed-summary-counts text-muted">${seed.citations_retrieved ?? 0} citations · ${seed.references_retrieved ?? 0} references</span>`
            : ''}
        </li>`).join('')}
    </ul>
    <div class="d-flex gap-4 mt-3 pt-3 border-top">
      ${caixaContagem(resumo.citations_retrieved ?? '-', 'Citations')}
      ${caixaContagem(resumo.references_retrieved ?? '-', 'References')}
    </div>`;
}

function conteudoCardSeedSemResultado(seed) {
  const mensagens = {
    not_found: 'No source found this paper. Check the DOI or title.',
    duplicate: `This is the same paper as seed S${(seed.duplicate_of ?? 0) + 1}; its results are in that tab.`,
    error: 'The search for this seed failed. Try again later.',
  };

  return `
    <div class="paper-doi">${seed.input_type === 'doi' ? 'DOI' : 'Title'}: ${escapeHtml(seed.input_value || '-')}</div>
    <div class="paper-title fw-semibold mb-2" style="font-size: 1.2rem;">${escapeHtml(rotuloStatusSeed(seed))}</div>
    <p class="text-muted mb-0">${escapeHtml(mensagens[seed.status] || mensagens.error)}</p>`;
}

function conteudoCardSeed(artigo) {
  const doiToShow = artigo.resolved_doi || artigo.input_doi || artigo.doi || '-';
  const authors = TableComponent.formatAuthors(artigo.authors);

  const contagemCitations = artigo.citations_retrieved ?? artigo.citations_count ?? artigo.citationCount ?? artigo.cited_by_count ?? '-';
  const contagemReferences = artigo.references_retrieved ?? artigo.references_count ?? '-';
  const keywordsText = TableComponent.formatKeywords(artigo.keywords || []);
  const abstractText = artigo.abstract || '-';

  return `
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
      <div class="seed-detail-line ${artigo.abstractExpanded ? 'expanded' : ''}">
        <span class="seed-detail-label">Abstract</span>
        <span class="seed-detail-text">
          ${
            artigo.abstractExpanded
              ? TableComponent.escapeHtml(abstractText)
              : TableComponent.escapeHtml(TableComponent.truncateText(abstractText, 140).replace(/\.\.\.$/, ''))
          }
        </span>
        ${
          abstractText && abstractText !== '-' && abstractText.length > 140
            ? `<span class="seed-detail-ellipsis" data-seed-toggle="abstract" role="button" tabindex="0" aria-expanded="${artigo.abstractExpanded ? 'true' : 'false'}">
                ${artigo.abstractExpanded ? ' READ LESS' : '...'}
              </span>`
            : ''
        }
      </div>

      <div class="seed-detail-line ${artigo.keywordsExpanded ? 'expanded' : ''}">
        <span class="seed-detail-label">Keywords</span>
        <span class="seed-detail-text">
          ${
            artigo.keywordsExpanded
              ? TableComponent.escapeHtml(keywordsText)
              : TableComponent.escapeHtml(TableComponent.truncateText(keywordsText, 110).replace(/\.\.\.$/, ''))
          }
        </span>
        ${
          keywordsText && keywordsText !== '-' && keywordsText.length > 110
            ? `<span class="seed-detail-ellipsis" data-seed-toggle="keywords" role="button" tabindex="0" aria-expanded="${artigo.keywordsExpanded ? 'true' : 'false'}">
                ${artigo.keywordsExpanded ? ' READ LESS' : '...'}
              </span>`
            : ''
        }
      </div>
    </div>

    <div class="d-flex gap-4 mt-3 pt-3 border-top">
      ${caixaContagem(contagemCitations, 'Citations')}
      ${caixaContagem(contagemReferences, 'References')}
    </div>`;
}

function mostrarResultado(artigo, modo = 'forward') {
  if (!artigo || (!artigo.title && !artigo.status)) {
    document.getElementById('resultado').innerHTML = '<p>Article not found.</p>';
    return;
  }

  let conteudo;
  if (artigo.isSummary) conteudo = conteudoCardResumo(artigo);
  else if (artigo.status && !seedTemResultado(artigo)) conteudo = conteudoCardSeedSemResultado(artigo);
  else conteudo = conteudoCardSeed(artigo);

  const cardHTML = `
  <div class="table-wrapper mb-4">
    <div class="table-topbar">
      <div class="table-info seed-tabs-info">
        <span class="table-title">Seed Paper Analysis</span>
        ${construirAbasSeeds()}
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
            ${conteudo}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  `;
  document.getElementById('resultado').innerHTML = cardHTML;

  document.getElementById('resultado').onclick = function (e) {
    const aba = e.target.closest('[data-seed-tab]');
    if (aba) {
      selecionarAbaSeed(aba.dataset.seedTab);
      return;
    }

    const toggle = e.target.closest('[data-seed-toggle]');
    if (toggle && window.seedData) {
      const target = toggle.dataset.seedToggle;
      if (target === 'abstract') {
        window.seedData.abstractExpanded = !window.seedData.abstractExpanded;
      }
      if (target === 'keywords') {
        window.seedData.keywordsExpanded = !window.seedData.keywordsExpanded;
      }
      mostrarResultado(window.seedData, obterModoAtual());
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

      persistirEstado();

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

  let csvContent = "Title,Abstract,Authors,Year,Venue,DOI,Cited by,Open Access,URL,Keywords,Language,Pages,Actions,Seeds,Direction\n";
  const direction = obterModoAtual() === 'forward' ? 'Citation' : 'Reference';

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

    const seeds = `"${seedsDoEstudo(cit).replace(/"/g, '""')}"`;

    csvContent += `${title},${abstract},${authors},${year},${venue},${doi},${citedBy},${openAccess},${url},${keywords},${language},${pages},${action},${seeds},"${direction}"\n`;
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

function seedsDoEstudo(cit) {
  const seeds = window.seedsInfo || [];
  return (cit.found_via_seeds || [])
    .map(i => `Seed ${i + 1}: ${(seeds[i] && (seeds[i].title || seeds[i].input_value)) || '-'}`)
    .join('; ');
}

function irParaTriagem() {
  window.location.href = 'analysis.html';
}

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

function openDedupModal() {
  const groups = findDuplicateGroups(window.citationsData || []).map(group => [...group]);

  window.dedupState = {
    groups,
    groupIndex: 0,
    toRemove: new Set()
  };

  document.getElementById('dedupModalBody').innerHTML = `
    <div id="dedupRemovedSection"></div>
    <div id="dedupActiveSection"></div>
  `;
  renderDedupRemovedSection();
  renderDedupStep();
  new bootstrap.Modal(document.getElementById('dedupModal')).show();
}

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
  entry.item.removedAsDuplicate = false;
  window.dedupHistoryByMode = window.dedupHistoryByMode || {};
  window.dedupHistoryByMode[obterModoAtual()] = history;

  if (listaDaAba(obterModoAtual()).includes(entry.item)) {
    window.citationsData = [...(window.citationsData || []), entry.item];
    window.allCitationsData = [...(window.allCitationsData || []), entry.item];
  }

  const searchId = obterSearchIdAtual();
  const paperIdBd = obterPaperIdBd(entry.item);
  if (searchId && paperIdBd) {
    queueFlagChange({ searchId, paperId: paperIdBd, excludedDuplicate: false });
  }

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
  sincronizarContagemSeed();
  renderDedupRemovedSection();
  persistirEstado();
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
    group.splice(1, 1);
  }

  renderDedupStep();
}

function finishDedupReview() {
  const state = window.dedupState;
  window.dedupState = null;

  if (!state || state.toRemove.size === 0) return;

  const itensParaRemover = (window.citationsData || []).filter(c => state.toRemove.has(c.paperId));

  window.citationsData = (window.citationsData || []).filter(c => !state.toRemove.has(c.paperId));
  itensParaRemover.forEach(item => { item.removedAsDuplicate = true; });
  window.dedupRemovedHistory = [
    ...(window.dedupRemovedHistory || []),
    ...itensParaRemover.map(item => ({ item, removedAt: Date.now() }))
  ];
  window.dedupHistoryByMode = window.dedupHistoryByMode || {};
  window.dedupHistoryByMode[obterModoAtual()] = window.dedupRemovedHistory;

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
  }

  const semRemovidos = (itens) => (itens || []).filter(c => !state.toRemove.has(c.paperId));
  window.citationsData = semRemovidos(window.citationsData);
  window.allCitationsData = semRemovidos(window.allCitationsData);

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
  persistirEstado();
}

const dedupModalElem = document.getElementById('dedupModal');
if (dedupModalElem) {
  dedupModalElem.addEventListener('hidden.bs.modal', finishDedupReview);
}


document.addEventListener('DOMContentLoaded', () => {
  const downloadBtn = document.getElementById('downloadBtn');
  const includeAllBtn = document.getElementById('includeAllBtn');
  const saveStateBtn = document.getElementById('saveStateBtn');

  if (downloadBtn) downloadBtn.onclick = baixarCitationsCSV;
  if (includeAllBtn) includeAllBtn.onclick = toggleIncludeAll;
  if (saveStateBtn) saveStateBtn.onclick = salvarEstadoPesquisa;

  document.querySelectorAll('input[name="snowballMode"]').forEach(radio => {
    radio.addEventListener('change', () => {
      if (window.forwardData || window.backwardData) trocarModo();
    });
  });

  atualizarBotaoIncludeAll();
  atualizarBotaoSalvar();

  ['analysis.html', 'criterios.html'].forEach(destino => {
    const link = document.querySelector(`a.nav-link[href="${destino}"]`);
    if (!link) return;

    link.addEventListener('click', e => {
      if (!window.forwardData && !window.backwardData) return;

      if (estudosIncluidos().length === 0) {
        e.preventDefault();
        alert('No article marked as "Include"');
        return;
      }

      persistirEstado();
    });
  });

  if (window.FilterComponent && typeof FilterComponent.init === 'function') {
    try { FilterComponent.init(); } catch (err) { console.warn('Falha ao inicializar FilterComponent:', err); }
  }

  carregarResultados();
});

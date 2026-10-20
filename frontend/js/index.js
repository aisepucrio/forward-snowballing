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

  // Mutação in-place, e não .map criando objetos novos: citationsData e
  // allCitationsData compartilham os mesmos objetos, então recriá-los aqui
  // fazia a marcação sumir assim que qualquer filtro fosse aplicado (o filtro
  // parte de allCitationsData, que ficava com os objetos antigos). É também o
  // que o toggle individual já faz.
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

// ---------------------------------------------------------------------------
// Seeds de entrada
//
// O usuário monta uma lista de seeds, cada uma com o tipo escolhido no
// seletor DOI | Title — não há adivinhação pelo formato. A lista inteira vai
// numa busca só (POST /api/articles/search/multi), que devolve citations e
// references de cada seed e a união das listas sem duplicatas.
// ---------------------------------------------------------------------------
const MAX_SEEDS = 20;
const SEEDS_STORAGE_KEY = 'snowmapSeeds';
const SEED_STATUS_OK = ['ok', 'partial'];

window.seedInputs = [];

function tipoSeedSelecionado() {
  const radio = document.querySelector('input[name="seedType"]:checked');
  return radio ? radio.value : 'doi';
}

function chaveSeed(type, value) {
  return type === 'doi' ? `doi:${normalizeDoi(value)}` : `title:${normalizeTitleJs(value)}`;
}

function mostrarErroSeed(mensagem) {
  const el = document.getElementById('seedError');
  if (el) el.textContent = mensagem || '';
}

function salvarSeedsLocal() {
  try {
    localStorage.setItem(SEEDS_STORAGE_KEY, JSON.stringify(window.seedInputs));
  } catch {
    // Sem localStorage a lista só não sobrevive ao recarregar a página.
  }
}

function carregarSeedsLocal() {
  try {
    const salvas = JSON.parse(localStorage.getItem(SEEDS_STORAGE_KEY) || '[]');
    if (Array.isArray(salvas)) {
      window.seedInputs = salvas
        .filter(s => s && ['doi', 'title'].includes(s.type) && typeof s.value === 'string' && s.value.trim())
        .slice(0, MAX_SEEDS);
    }
  } catch {
    window.seedInputs = [];
  }
}

// Devolve true quando a seed entrou na lista (buscarArtigo usa isso para
// não buscar com um valor digitado que acabou recusado).
function adicionarSeed() {
  const input = document.getElementById('searchInput');
  const value = (input ? input.value : '').trim();
  if (!value) {
    mostrarErroSeed('Type a DOI or a title first.');
    return false;
  }

  const type = tipoSeedSelecionado();
  if (type === 'doi' && !looksLikeDOI(value)) {
    mostrarErroSeed(`"${value}" is not a DOI. Choose "Title" to search by title.`);
    return false;
  }
  if (window.seedInputs.length >= MAX_SEEDS) {
    mostrarErroSeed(`Up to ${MAX_SEEDS} seeds per search.`);
    return false;
  }

  const chave = chaveSeed(type, value);
  if (window.seedInputs.some(s => chaveSeed(s.type, s.value) === chave)) {
    mostrarErroSeed('This seed is already in the list.');
    return false;
  }

  window.seedInputs.push({ type, value });
  input.value = '';
  mostrarErroSeed('');
  salvarSeedsLocal();
  renderListaSeeds();
  input.focus();
  return true;
}

function removerSeed(index) {
  window.seedInputs.splice(index, 1);
  mostrarErroSeed('');
  salvarSeedsLocal();
  renderListaSeeds();
}

function atualizarPlaceholderSeed() {
  const input = document.getElementById('searchInput');
  if (!input) return;
  input.placeholder = tipoSeedSelecionado() === 'doi'
    ? 'e.g., 10.1145/3025453.3025795'
    : 'e.g., Guidelines for snowballing in systematic literature studies';
}

function renderListaSeeds() {
  const lista = document.getElementById('seedList');
  const contador = document.getElementById('seedCounter');
  const addBtn = document.getElementById('addSeedBtn');
  const searchBtn = document.getElementById('searchSeedsBtn');
  const total = window.seedInputs.length;

  if (lista) {
    lista.innerHTML = window.seedInputs.map((seed, i) => `
      <div class="seed-chip" title="${escapeHtml(seed.value)}">
        <span class="seed-chip-index">${i + 1}</span>
        <span class="seed-chip-type">${seed.type === 'doi' ? 'DOI' : 'Title'}</span>
        <span class="seed-chip-value">${escapeHtml(seed.value)}</span>
        <button type="button" class="seed-chip-remove" onclick="removerSeed(${i})" aria-label="Remove seed ${i + 1}">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
    `).join('');
  }

  if (contador) contador.textContent = `${total}/${MAX_SEEDS} seeds`;
  if (addBtn) addBtn.disabled = total >= MAX_SEEDS;
  if (searchBtn) {
    searchBtn.innerHTML = total > 1
      ? `<i class="bi bi-search"></i> Search ${total} seeds`
      : '<i class="bi bi-search"></i> Search';
  }
}

// ---------------------------------------------------------------------------
// Abas de seed
//
// window.forwardData / window.backwardData guardam a união (aba "All seeds"),
// um objeto por estudo. As abas de cada seed reaproveitam OS MESMOS objetos
// (pelas chaves citation_keys / reference_keys), então incluir/excluir um
// estudo numa aba vale em todas, e trocar de aba não perde nada.
// ---------------------------------------------------------------------------
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

  // Duplicata removida na revisão manual some de todas as abas.
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

// Todos os estudos incluídos, de todas as abas e das duas direções, uma vez
// cada — é o que segue para o dashboard e para a triagem, sem distinção de
// seed.
function estudosIncluidos() {
  const vistos = new Set();
  const incluidos = [];
  [...(window.forwardData || []), ...(window.backwardData || [])].forEach(item => {
    if (item.removedAsDuplicate || item.selecionado !== 'incluir') return;
    const chave = item.study_key || item.paperId;
    if (vistos.has(chave)) return;
    vistos.add(chave);
    incluidos.push(item);
  });
  return incluidos;
}

// O card mostra Citations/References da aba ativa. Remover duplicatas no
// popup só mexe em window.citationsData (a lista da tabela); sem isso aqui, o
// card nunca refletia a remoção, mesmo com a tabela já atualizada.
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
  // O histórico de duplicatas removidas é por direção e sobrevive à troca de
  // aba (a remoção vale em todas); só uma busca nova o zera.
  window.dedupHistoryByMode = window.dedupHistoryByMode || {};
  window.dedupRemovedHistory = window.dedupHistoryByMode[mode] || [];

  // Citations e References são populações diferentes: os autores, venues e anos
  // de uma não valem para a outra. Zerar os filtros e reconstruir a lista aberta
  // com os dados novos evita dois problemas — a tabela voltar sem filtro
  // enquanto os botões seguem marcados, e as listas de autor/venue continuarem
  // mostrando o dataset anterior com contagens erradas.
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
}

// ---------------------------------------------------------------------------
// Progresso da busca
//
// O servidor responde em NDJSON: uma linha por marco enquanto o Python roda e,
// na última, o resultado. Isso existe porque a busca leva ~50s (podendo passar
// de 3 minutos) e antes a tela só mostrava um spinner — sem como distinguir
// "está vindo" de "travou" ou "deu erro".
// ---------------------------------------------------------------------------
let progressoTimer = null;

function iniciarProgresso() {
  const status = document.getElementById('progressStatus');
  const elapsed = document.getElementById('progressElapsed');

  if (status) status.textContent = 'Searching…';

  const inicio = Date.now();
  if (elapsed) elapsed.textContent = '0s';

  clearInterval(progressoTimer);
  progressoTimer = setInterval(() => {
    if (!elapsed) return;
    const seg = Math.floor((Date.now() - inicio) / 1000);
    elapsed.textContent = seg < 60 ? `${seg}s` : `${Math.floor(seg / 60)}m${String(seg % 60).padStart(2, '0')}s`;
  }, 1000);
}

function pararProgresso() {
  clearInterval(progressoTimer);
  progressoTimer = null;
}

function registrarProgresso(evento) {
  const status = document.getElementById('progressStatus');
  if (!status || !evento.message) return;

  // Substitui a linha, não acumula histórico: o único marco publicado é a
  // contagem final, que é a informação que o usuário veria na tela seguinte.
  status.textContent = evento.message;
}

// Lê o corpo NDJSON conforme ele chega, entregando um objeto por linha.
async function* lerLinhasNdjson(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const linhas = buffer.split('\n');
    // A última pode estar pela metade: fica no buffer até o próximo chunk.
    buffer = linhas.pop();

    for (const linha of linhas) {
      if (!linha.trim()) continue;
      try {
        yield JSON.parse(linha);
      } catch {
        // Linha truncada ou ruído: progresso é acessório, seguir em frente.
      }
    }
  }

  if (buffer.trim()) {
    try { yield JSON.parse(buffer); } catch { /* idem */ }
  }
}

async function buscarComProgresso(url, opcoes = {}) {
  const res = await fetch(url, {
    ...opcoes,
    headers: { ...(opcoes.headers || {}), Accept: 'application/x-ndjson' },
  });

  if (!res.ok) throw new Error('Search failed');

  // Se o servidor não streamou (consumidor antigo, ou erro antes do Python
  // começar), a resposta é o JSON único de sempre.
  const tipo = res.headers.get('Content-Type') || '';
  if (!tipo.includes('application/x-ndjson')) {
    return res.json();
  }

  let resultado = null;
  for await (const evento of lerLinhasNdjson(res)) {
    if (evento.type === 'progress') registrarProgresso(evento);
    else if (evento.type === 'result') resultado = evento.data;
    else if (evento.type === 'error') throw new Error(evento.error || 'Search failed');
  }

  if (!resultado) throw new Error('Search ended without returning a result.');
  return resultado;
}

function prepararEstudos(lista) {
  return (lista || []).map((c, i) => ({
    ...c,
    // study_key (DOI ou título normalizado) é único por direção e é a chave
    // que liga as abas de seed à união.
    paperId: c.study_key || `${c.paperId || c.doi || 'item'}-${i}`,
    selecionado: c.selecionado || null,
    abstractExpanded: false,
    keywordsExpanded: false
  }));
}

function aplicarResultadoBusca(resultado) {
  window.currentSearchIdForward = resultado.search_id || null;
  window.currentSearchIdBackward = resultado.search_id_backward || null;
  window.paperIdMap = resultado.paper_id_map || {};

  window.forwardData = prepararEstudos(resultado.citations);
  window.backwardData = prepararEstudos(resultado.references);
  window.forwardByKey = new Map(window.forwardData.map(item => [item.paperId, item]));
  window.backwardByKey = new Map(window.backwardData.map(item => [item.paperId, item]));
  window.dedupHistoryByMode = {};

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
    seeds_failed: resultado.seeds_failed || 0,
    partial_result: !!resultado.partial_result,
  };

  // Com uma seed só não há o que alternar: o card é o da própria seed, como
  // antes, sem barra de abas.
  window.activeSeedTab = window.seedsInfo.length > 1 ? 'all' : 0;
  window.mostrarTagsSeed = window.seedsInfo.length > 1;

  // Save Research State depende do banco (search_id); com o banco desligado
  // o botão não faz sentido.
  const saveStateBtn = document.getElementById('saveStateBtn');
  if (saveStateBtn) {
    saveStateBtn.style.display = (window.currentSearchIdForward || window.currentSearchIdBackward) ? '' : 'none';
  }

  // O dashboard (analysis.html) lista as seeds que deram resultado. Sem as
  // chaves dos estudos, que só servem às abas daqui e pesam no localStorage.
  try {
    const seedsParaDashboard = window.seedsInfo
      .filter(seedTemResultado)
      .map(({ citation_keys, reference_keys, ...seed }) => seed);
    localStorage.setItem('seedsData', JSON.stringify(seedsParaDashboard));
    localStorage.removeItem('seedPaperData');
  } catch (err) {
    console.warn('Não foi possível guardar as seeds para o dashboard:', err);
  }

  trocarModo();
  document.body.classList.add('busca-realizada');
}

async function buscarArtigo() {
  try {
    const input = document.getElementById('searchInput');

    // Valor digitado e não adicionado entra na lista antes de buscar — é o
    // caso de quem busca uma seed só e clica direto em Search.
    if (input && input.value.trim() && !adicionarSeed()) {
      return;
    }

    const seeds = window.seedInputs || [];
    if (seeds.length === 0) {
      mostrarErroSeed('Add at least one DOI or title to search.');
      return;
    }

    if (input) input.blur();
    mostrarErroSeed('');

    const navbarSearchInput = document.getElementById('navbarSearchInput');
    if (navbarSearchInput) navbarSearchInput.value = '';
    document.getElementById('loadingSpinner').style.display = 'block';
    document.getElementById('resultado').innerHTML = '';

    const hint = document.getElementById('progressHint');
    if (hint) {
      hint.textContent = seeds.length > 1
        ? `Searching ${seeds.length} seeds, one at a time — about a minute per seed.`
        : 'This usually takes under a minute.';
    }

    const citationsSectionEl = document.getElementById('citationsList');
    if (citationsSectionEl) citationsSectionEl.style.display = 'none';

    window.forwardData = null;
    window.backwardData = null;
    window.citationsData = [];
    window.seedData = null;
    window.seedsInfo = null;
    window.pendingFlagChanges = {}; // nova busca, nova search_id: descarta pendências da busca anterior
    atualizarBotaoSalvar();

    iniciarProgresso();

    // Uma busca por vez: um segundo clique dispararia outro processo Python
    // disputando o mesmo limite de requisições das APIs.
    const searchBtn = document.getElementById('searchSeedsBtn');
    if (searchBtn) searchBtn.disabled = true;

    buscarComProgresso('/api/articles/search/multi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seeds: seeds.map(({ type, value }) => ({ type, value })) })
    })
      .then(aplicarResultadoBusca)
      .catch(err => {
        // A causa real (artigo não encontrado, API fora, timeout) fica no
        // console e no log do servidor, que é onde os testes a leem. Na tela
        // vai uma linha neutra: o usuário final não tem o que fazer com o
        // detalhe técnico, e ele só polui a interface.
        console.error(err);
        window.forwardData = [];
        window.backwardData = [];
        document.getElementById('resultado').innerHTML =
          '<p class="text-muted">No results for this search. Check the DOIs or titles and try again.</p>';
      })
      .finally(() => {
        pararProgresso();
        if (searchBtn) searchBtn.disabled = false;
        document.getElementById('loadingSpinner').style.display = 'none';
      });
  } catch (err) {
    console.error('buscarArtigo falhou antes de iniciar a busca:', err);
    document.getElementById('loadingSpinner').style.display = 'none';
    const resultadoEl = document.getElementById('resultado');
    if (resultadoEl) {
      resultadoEl.innerHTML = `<p class="text-danger">Unexpected error: ${escapeHtml(err.message)}</p>`;
    }
  }
}

// A busca da navbar não tem seletor de tipo: ela volta para a montagem da
// lista de seeds com o texto já no campo, e o usuário escolhe DOI ou Title.
function buscarArtigoNavbar() {
  const navbarInput = document.getElementById('navbarSearchInput');
  const input = document.getElementById('searchInput');
  if (input && navbarInput) input.value = navbarInput.value.trim();

  document.body.classList.remove('busca-realizada');
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (input) input.focus();
}

// O pipeline já calcula `warning` e `partial_result` quando uma das fontes
// falha (Semantic Scholar fora do ar, editora bloqueando a lista de
// referências, work IDs que o OpenAlex não resolve mais), mas até aqui esses
// campos morriam no JSON: a tela mostrava só os números. O efeito era o pior
// possível numa revisão sistemática — a mesma busca devolvia 19 ou 132
// citações dependendo do dia, sem nada na interface indicando que o resultado
// tinha vindo de uma fonte só.
function construirAvisoResultadoParcial(artigo) {
  if (!artigo) return '';

  let texto = null;
  if (artigo.isSummary) {
    if (artigo.seeds_failed > 0) {
      texto = `${artigo.seeds_failed} ${artigo.seeds_failed === 1 ? 'seed returned' : 'seeds returned'} no results — see the seed tabs.`;
    } else if (artigo.partial_result) {
      texto = "Some sources didn't respond for some seeds — the counts below may be incomplete.";
    }
  } else if (artigo.partial_result || artigo.warning) {
    // O texto detalhado do pipeline (quais fontes falharam, quantos IDs não
    // resolveram) continua no JSON, no log e nos testes — não na tela. Aqui só
    // o que muda a leitura do resultado: os números podem estar incompletos.
    texto = "Some sources didn't respond — the counts below may be incomplete.";
  }

  if (!texto) return '';
  return `
    <div class="alert alert-warning d-flex gap-2 mb-3 py-2 px-3" role="alert" style="font-size:0.85rem;">
      <i class="bi bi-exclamation-triangle-fill flex-shrink-0" style="line-height:1.4;"></i>
      <div>${escapeHtml(texto)}</div>
    </div>
  `;
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
  if (seed.status === 'partial') return 'Partial';
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
  ${construirAvisoResultadoParcial(artigo)}
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

// "S1: Título da seed; S3: ..." — de quais seeds o estudo veio.
function seedsDoEstudo(cit) {
  const seeds = window.seedsInfo || [];
  return (cit.found_via_seeds || [])
    .map(i => `S${i + 1}: ${(seeds[i] && (seeds[i].title || seeds[i].input_value)) || '-'}`)
    .join('; ');
}

function irParaTriagem() {
  const incluidos = estudosIncluidos();
  if (incluidos.length === 0) {
    alert('No citations to send to screening.');
    return;
  }
  window.name = JSON.stringify(incluidos);
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
  entry.item.removedAsDuplicate = false;
  window.dedupHistoryByMode = window.dedupHistoryByMode || {};
  window.dedupHistoryByMode[obterModoAtual()] = history;

  // Restaurado nas duas listas, pelo mesmo motivo da remoção: allCitationsData
  // é a base que os filtros leem. Só volta para a tabela se o estudo pertence
  // à aba aberta — o histórico vale para todas as abas da direção.
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
  // Os objetos são os mesmos em todas as abas: marcar aqui tira a duplicata
  // das outras abas de seed da mesma direção também.
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

    Promise.all(updates)
      .then(() => console.log('[DB] Sucesso: Duplicatas atualizadas com excluded_duplicate = TRUE.'))
      .catch(err => console.error('[ERRO DB] Falha ao gravar excluded_duplicate:', err));
  }

  // A remoção precisa valer também na base que o filtro usa. Sem isso, aplicar
  // qualquer filtro depois partia de allCitationsData — que ainda continha as
  // duplicatas — e elas reapareciam na tabela.
  const semRemovidos = (itens) => (itens || []).filter(c => !state.toRemove.has(c.paperId));
  window.citationsData = semRemovidos(window.citationsData);
  window.allCitationsData = semRemovidos(window.allCitationsData);

  mostrarCitacoes(window.citationsData);
  atualizarBotaoIncludeAll();
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

  carregarSeedsLocal();
  document.querySelectorAll('input[name="seedType"]').forEach(radio => {
    radio.addEventListener('change', () => {
      atualizarPlaceholderSeed();
      mostrarErroSeed('');
    });
  });
  atualizarPlaceholderSeed();

  // analysis.html manda a busca da navbar para cá em ?search=: o texto vai
  // para o campo e o usuário escolhe o tipo antes de adicionar.
  const buscaRecebida = new URLSearchParams(window.location.search).get('search');
  const inputSeed = document.getElementById('searchInput');
  if (buscaRecebida && inputSeed) inputSeed.value = buscaRecebida;
  renderListaSeeds();

  const linkAnalise = document.querySelector('a.nav-link[href="analysis.html"]');
  if (linkAnalise) {
    linkAnalise.addEventListener('click', e => {
      e.preventDefault();
      if (!window.forwardData && !window.backwardData) {
        alert('No citations to send to screening.');
        return;
      }

      // Tudo o que foi incluído, em qualquer aba de seed e nas duas direções.
      const incluidos = estudosIncluidos();

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

      window.name = JSON.stringify(incluidos);
      window.location.href = 'analysis.html';
    });
  }

  const linkCriterios = document.querySelector('a.nav-link[href="criterios.html"]');
  if (linkCriterios) {
    linkCriterios.addEventListener('click', e => {
      e.preventDefault();

      if (!window.forwardData && !window.backwardData) {
        alert('No citations to send.');
        return;
      }

      const incluidos = estudosIncluidos();

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

  // Inicializa o componente de filtro, se disponível
  if (window.FilterComponent && typeof FilterComponent.init === 'function') {
    try { FilterComponent.init(); } catch (err) { console.warn('Falha ao inicializar FilterComponent:', err); }
  }
});

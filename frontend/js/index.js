
function looksLikeDOI(value) {
  if (!value) return false;
  const text = value.trim();
  return /^10\.\d{4,9}\/\S+$/i.test(text) || /doi\.org\/10\.\d{4,9}\/\S+/i.test(text);
}

function extrairDoi(value) {
  const match = String(value || '').trim().match(/10\.\d{4,9}\/\S+$/i);
  return match ? match[0] : String(value || '').trim();
}

// ---------------------------------------------------------------------------
// Seeds de entrada
//
// O usuário monta uma lista de seeds num campo só; o tipo de cada uma (DOI ou
// título) sai do formato do texto, por looksLikeDOI. A lista inteira vai
// numa busca só (POST /api/articles/search/multi), que devolve citations e
// references de cada seed e a união das listas sem duplicatas.
// ---------------------------------------------------------------------------
const MAX_SEEDS = 20;
const SEEDS_STORAGE_KEY = 'snowmapSeeds';

window.seedInputs = [];

// Guarda só o DOI (10.xxxx/...): looksLikeDOI aceita links como
// https://dx.doi.org/10..., que o normalize_doi do Python não limpa — e uma
// seed com DOI inválido derruba a busca inteira no parse_seeds.
function seedDoTexto(texto) {
  const value = String(texto || '').trim();
  return looksLikeDOI(value)
    ? { type: 'doi', value: extrairDoi(value) }
    : { type: 'title', value };
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

  const { type, value: seedValue } = seedDoTexto(value);

  const chave = chaveSeed(type, seedValue);
  if (window.seedInputs.some(s => chaveSeed(s.type, s.value) === chave)) {
    mostrarErroSeed('This seed is already in the list.');
    return false;
  }
  if (window.seedInputs.length >= MAX_SEEDS) {
    mostrarErroSeed(`Up to ${MAX_SEEDS} seeds per search.`);
    return false;
  }

  window.seedInputs.push({ type, value: seedValue });
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

async function buscarArtigo() {
  const searchBtn = document.getElementById('searchSeedsBtn');
  let redirecionando = false;

  try {
    const input = document.getElementById('searchInput');

    // Valor digitado e não adicionado entra na lista antes de buscar — é o
    // caso de quem busca uma seed só e clica direto em Search.
    // Se o texto já está na lista (ex.: veio da busca da navbar), não é erro:
    // limpa o campo e busca a lista como está.
    if (input && input.value.trim()) {
      const { type, value } = seedDoTexto(input.value);
      const chave = chaveSeed(type, value);
      if (window.seedInputs.some(s => chaveSeed(s.type, s.value) === chave)) {
        input.value = '';
      } else if (!adicionarSeed()) {
        return;
      }
    }

    const seeds = window.seedInputs || [];
    if (seeds.length === 0) {
      mostrarErroSeed('Add at least one DOI or title to search.');
      return;
    }

    if (input) input.blur();
    mostrarErroSeed('');
    document.getElementById('loadingSpinner').style.display = 'block';

    const hint = document.getElementById('progressHint');
    if (hint) {
      hint.textContent = seeds.length > 1
        ? `Searching ${seeds.length} seeds, one at a time — about a minute per seed.`
        : 'This usually takes under a minute.';
    }

    iniciarProgresso();

    // Uma busca por vez: um segundo clique dispararia outro processo Python
    // disputando o mesmo limite de requisições das APIs.
    if (searchBtn) searchBtn.disabled = true;

    buscarComProgresso('/api/articles/search/multi', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seeds: seeds.map(({ type, value }) => ({ type, value })) })
    })
      .then(() => {
        SearchState.reiniciar();
        redirecionando = true;
        window.location.href = 'results.html';
      })
      .catch(err => {
        // A causa real (artigo não encontrado, API fora, timeout) fica no
        // console e no log do servidor, que é onde os testes a leem. Na tela
        // vai uma linha neutra: o usuário final não tem o que fazer com o
        // detalhe técnico, e ele só polui a interface.
        console.error(err);
        mostrarErroSeed('No results for this search. Check the DOIs or titles and try again.');
      })
      .finally(() => {
        pararProgresso();
        if (redirecionando) return;
        if (searchBtn) searchBtn.disabled = false;
        document.getElementById('loadingSpinner').style.display = 'none';
      });
  } catch (err) {
    console.error('buscarArtigo falhou antes de iniciar a busca:', err);
    document.getElementById('loadingSpinner').style.display = 'none';
    mostrarErroSeed(`Unexpected error: ${err.message}`);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  carregarSeedsLocal();

  const buscaRecebida = new URLSearchParams(window.location.search).get('search');
  const inputSeed = document.getElementById('searchInput');
  if (buscaRecebida && inputSeed) inputSeed.value = buscaRecebida;

  renderListaSeeds();
});

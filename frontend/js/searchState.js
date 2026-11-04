function escapeHtml(text) {
  if (text === null || text === undefined) return '-';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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

const SearchState = (function () {
  const STORAGE_KEY = 'snowmapTriage';
  const RESULT_URL = '/api/articles/last-result';

  function vazio() {
    return {
      inc: [],
      exc: [],
      dup: [],
      view: { tab: 'all', mode: 'forward' },
      pending: {},
    };
  }

  function ler() {
    try {
      const salvo = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (salvo && typeof salvo === 'object') return { ...vazio(), ...salvo };
    } catch {
    }
    return vazio();
  }

  function gravar(estado) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(estado));
      return true;
    } catch (err) {
      console.warn('Não foi possível guardar o estado da triagem:', err);
      return false;
    }
  }

  function reiniciar() {
    return gravar(vazio());
  }

  const chave = (modo, item) => `${modo}:${item.paperId}`;

  function salvarTriagem({ forward, backward, view, pending }) {
    const estado = { ...vazio(), view: view || vazio().view, pending: pending || {} };

    [['forward', forward], ['backward', backward]].forEach(([modo, lista]) => {
      (lista || []).forEach(item => {
        const k = chave(modo, item);
        if (item.removedAsDuplicate) estado.dup.push(k);
        if (item.selecionado === 'incluir') estado.inc.push(k);
        else if (item.selecionado === 'excluir') estado.exc.push(k);
      });
    });

    return gravar(estado);
  }

  function aplicarTriagem(lista, modo, estado = ler()) {
    const inc = new Set(estado.inc);
    const exc = new Set(estado.exc);
    const dup = new Set(estado.dup);

    (lista || []).forEach(item => {
      const k = chave(modo, item);
      item.selecionado = inc.has(k) ? 'incluir' : exc.has(k) ? 'excluir' : null;
      item.removedAsDuplicate = dup.has(k);
    });
    return lista;
  }

  async function buscarUltimoResultado() {
    const res = await fetch(RESULT_URL, { headers: { Accept: 'application/json' } });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error('Could not load the last search result.');
    return res.json();
  }

  function prepararEstudos(lista) {
    return (lista || []).map((c, i) => ({
      ...c,
      paperId: c.study_key || `${c.paperId || c.doi || 'item'}-${i}`,
      selecionado: c.selecionado || null,
      abstractExpanded: false,
      keywordsExpanded: false,
    }));
  }

  function unicosIncluidos(forward, backward) {
    const vistos = new Set();
    const incluidos = [];
    [...(forward || []), ...(backward || [])].forEach(item => {
      if (item.removedAsDuplicate || item.selecionado !== 'incluir') return;
      const k = item.study_key || item.paperId;
      if (vistos.has(k)) return;
      vistos.add(k);
      incluidos.push(item);
    });
    return incluidos;
  }

  async function carregarIncluidos() {
    const resultado = await buscarUltimoResultado();
    if (!resultado) return [];

    const estado = ler();
    const forward = aplicarTriagem(prepararEstudos(resultado.citations), 'forward', estado);
    const backward = aplicarTriagem(prepararEstudos(resultado.references), 'backward', estado);
    return unicosIncluidos(forward, backward);
  }

  return {
    ler, reiniciar, salvarTriagem, aplicarTriagem,
    buscarUltimoResultado, prepararEstudos, unicosIncluidos, carregarIncluidos,
  };
})();

window.SearchState = SearchState;

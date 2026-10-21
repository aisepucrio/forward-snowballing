const { readOutput, writeOutput } = require('./sessionState');
const { PythonRunner } = require('./pythonRunner');

// A busca roda sem timeout (defaultTimeoutMs: 0), mas um update de flag é rápido
// e não deve segurar a requisição indefinidamente se o banco não responder.
const FLAG_UPDATE_TIMEOUT_MS = 30 * 1000;

// Mesmo padrão do Python (SNOWMAP_MAX_SEEDS); o Python revalida.
const MAX_SEEDS = Number(process.env.SNOWMAP_MAX_SEEDS) > 0 ? Number(process.env.SNOWMAP_MAX_SEEDS) : 20;
// Com 20 seeds a união pode passar dos 10 MB padrão do PythonRunner.
const MULTI_MAX_OUTPUT_BYTES = 64 * 1024 * 1024;

class ArticleSearchService {
  constructor({ pythonRunner = new PythonRunner({ defaultTimeoutMs: 0 }) } = {}) {
    this.pythonRunner = pythonRunner;
  }

  getCitations(sessionId) {
    const data = readOutput(sessionId);
    if (!data || !Array.isArray(data.citations)) {
      return null;
    }

    return data.citations;
  }

  // Uma busca só devolve as duas listas: run_forward.py traz `citations` e
  // `references`. Havia aqui um desvio para run_backward.py quando
  // type === 'backward', mas aquele script coletava as referências pelo mesmo
  // caminho e a mais nada — era subconjunto estrito, e a interface nunca o
  // pedia (o toggle "Citations/References" alterna entre as duas listas desta
  // mesma resposta, sem nova requisição).
  async search({ sessionId, doi, title, abortEmitter = null, onProgress = null }) {
    const normalizedDoi = this.normalizeInput(doi);
    const normalizedTitle = this.normalizeInput(title);

    if (!normalizedDoi && !normalizedTitle) {
      const err = new Error('DOI ou título devem ser informados');
      err.statusCode = 400;
      throw err;
    }

    const data = await this.pythonRunner.runJsonScript('run_forward.py', {
      args: [normalizedDoi || '-', normalizedTitle || '-'],
      abortEmitter,
      onStderrLine: onProgress,
    });

    writeOutput(sessionId, data);
    return data;
  }

  // Busca com várias seeds (run_multi.py). Cada seed traz citations e
  // references, como a busca de uma seed só; o resultado junta as listas sem
  // duplicatas e diz de qual seed veio cada estudo. A validação fina (formato
  // do DOI, seeds repetidas) fica no Python, que é quem resolve a seed — aqui
  // só se barra o que não deveria nem iniciar um processo.
  async searchMulti({ sessionId, seeds, abortEmitter = null, onProgress = null }) {
    if (!Array.isArray(seeds) || seeds.length === 0) {
      throw this.badRequest('Informe ao menos uma seed.');
    }
    if (seeds.length > MAX_SEEDS) {
      throw this.badRequest(`Máximo de ${MAX_SEEDS} seeds por busca.`);
    }

    const cleanSeeds = seeds.map((seed, i) => {
      const type = String(seed?.type || '').trim().toLowerCase();
      const value = this.normalizeInput(seed?.value);
      if (!['doi', 'title'].includes(type)) {
        throw this.badRequest(`Seed ${i + 1}: tipo deve ser 'doi' ou 'title'.`);
      }
      if (!value) {
        throw this.badRequest(`Seed ${i + 1}: valor vazio.`);
      }
      return { type, value };
    });

    const data = await this.pythonRunner.runJsonScript('run_multi.py', {
      input: { seeds: cleanSeeds },
      abortEmitter,
      onStderrLine: onProgress,
      maxOutputBytes: MULTI_MAX_OUTPUT_BYTES,
    });

    writeOutput(sessionId, data);
    return data;
  }

  badRequest(message) {
    const err = new Error(message);
    err.statusCode = 400;
    return err;
  }

  async updateFlag({ searchId, paperId, selectedFirstPage, excludedDuplicate, duplicateOf }) {
    if (!searchId || !paperId) {
      const err = new Error('search_id e paper_id são obrigatórios');
      err.statusCode = 400;
      throw err;
    }

    const payload = JSON.stringify({
      search_id: searchId,
      paper_id: paperId,
      selected_first_page: selectedFirstPage ?? null,
      excluded_duplicate: excludedDuplicate ?? null,
      duplicate_of: duplicateOf ?? null,
    });

    return this.pythonRunner.runJsonScript('update_flag.py', {
      args: [payload],
      timeoutMs: FLAG_UPDATE_TIMEOUT_MS,
    });
  }

  // Aplica várias flags numa única conexão com o banco, em vez de uma
  // conexão por item — usada pelo botão "Save Research State" da triagem,
  // para não sobrecarregar o Postgres com um processo por clique.
  async updateFlagBatch(updates) {
    if (!Array.isArray(updates) || updates.length === 0) {
      const err = new Error('updates deve ser uma lista não vazia');
      err.statusCode = 400;
      throw err;
    }

    const invalid = updates.some((u) => !u || !u.search_id || !u.paper_id);
    if (invalid) {
      const err = new Error('Cada item de updates precisa de search_id e paper_id');
      err.statusCode = 400;
      throw err;
    }

    const payload = JSON.stringify(updates);

    return this.pythonRunner.runJsonScript('update_flags_batch.py', {
      args: [payload],
      timeoutMs: FLAG_UPDATE_TIMEOUT_MS,
    });
  }

  markArticle(sessionId, paperId, status) {
    if (!paperId || !status) {
      const err = new Error('paperId e status são obrigatórios');
      err.statusCode = 400;
      throw err;
    }

    const data = readOutput(sessionId);
    if (!data || !Array.isArray(data.citations)) {
      const err = new Error('Erro ao carregar as citações');
      err.statusCode = 500;
      throw err;
    }

    const artigo = data.citations.find((a) => a.paperId === paperId);
    if (!artigo) {
      const err = new Error('Artigo não encontrado');
      err.statusCode = 404;
      throw err;
    }

    artigo.selecionado = status;
    writeOutput(sessionId, data);
  }

  getIncludedArticles(sessionId) {
    const data = readOutput(sessionId);
    if (!data || !Array.isArray(data.citations)) {
      const err = new Error('Erro ao carregar as citações');
      err.statusCode = 500;
      throw err;
    }

    return data.citations.filter((a) => a.selecionado === 'incluir');
  }

  normalizeInput(value) {
    if (value === undefined || value === null) return null;
    const normalized = String(value).trim();
    return ['', '-', 'null', 'None'].includes(normalized) ? null : normalized;
  }
}

module.exports = {
  ArticleSearchService,
};

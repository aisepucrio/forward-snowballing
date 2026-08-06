const { readOutput, writeOutput } = require('./sessionState');
const { PythonRunner } = require('./pythonRunner');

// A busca roda sem timeout (defaultTimeoutMs: 0), mas um update de flag é rápido
// e não deve segurar a requisição indefinidamente se o banco não responder.
const FLAG_UPDATE_TIMEOUT_MS = 30 * 1000;

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

  async search({ sessionId, doi, title, type, abortEmitter = null }) {
    const normalizedDoi = this.normalizeInput(doi);
    const normalizedTitle = this.normalizeInput(title);

    if (!normalizedDoi && !normalizedTitle) {
      const err = new Error('DOI ou título devem ser informados');
      err.statusCode = 400;
      throw err;
    }

    const scriptName = type === 'backward' ? 'run_backward.py' : 'run_forward.py';
    const data = await this.pythonRunner.runJsonScript(scriptName, {
      args: [normalizedDoi || '-', normalizedTitle || '-'],
      abortEmitter,
    });

    writeOutput(sessionId, data);
    return data;
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

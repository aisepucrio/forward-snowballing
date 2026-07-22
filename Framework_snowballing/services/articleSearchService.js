const { readOutput, writeOutput } = require('./sessionState');
const { PythonRunner } = require('./pythonRunner');

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

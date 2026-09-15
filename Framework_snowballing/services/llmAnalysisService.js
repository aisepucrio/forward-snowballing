const { PythonRunner } = require('./pythonRunner');
const crypto = require('crypto');

const MAX_CACHE_ENTRIES = 100;
// Cada artigo custa chamada paga na OpenRouter; o frontend manda lotes de 40.
const MAX_ARTICLES_PER_REQUEST = 100;

class LlmAnalysisService {
  constructor({ pythonRunner = new PythonRunner({ defaultTimeoutMs: 5 * 60 * 1000 }) } = {}) {
    this.pythonRunner = pythonRunner;
    this.cache = new Map();
  }

  async analyze(payload, { abortEmitter = null } = {}) {
    const artigos = Array.isArray(payload.artigos) ? payload.artigos : [];
    if (artigos.length === 0) {
      const err = new Error('Nenhum artigo enviado.');
      err.statusCode = 400;
      throw err;
    }
    if (artigos.length > MAX_ARTICLES_PER_REQUEST) {
      const err = new Error(`Máximo de ${MAX_ARTICLES_PER_REQUEST} artigos por requisição.`);
      err.statusCode = 400;
      throw err;
    }

    // Modelo, chave e parâmetros da LLM vêm só do .env (lido pelo Python);
    // nada disso é aceito do request.
    const input = {
      criteriosInclusao: payload.criteriosInclusao,
      criteriosExclusao: payload.criteriosExclusao,
      criteriaMetadata: payload.criteriaMetadata,
      artigos,
      extraPrompt: payload.extraPrompt,
    };
    const cacheKey = crypto
      .createHash('sha256')
      .update(JSON.stringify(input))
      .digest('hex');

    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    const result = await this.pythonRunner.runJsonScript('analisys_LLM.py', {
      input: {
        ...input,
      },
      abortEmitter,
    });

    const hasErrors = result.some((article) =>
      Object.values(article.results || {}).some((value) => value === 'error')
    );
    if (!hasErrors) {
      if (this.cache.size >= MAX_CACHE_ENTRIES) {
        this.cache.delete(this.cache.keys().next().value);
      }
      this.cache.set(cacheKey, result);
    }

    return result;
  }

  // Grava os critérios de inclusão/exclusão e o veredito da LLM por artigo
  // no banco, numa única conexão — chamado uma vez ao fim da análise em
  // criterios.html, não por artigo.
  async saveCriteriaResults({ searchId, criteria, results }) {
    if (!searchId) {
      const err = new Error('searchId é obrigatório');
      err.statusCode = 400;
      throw err;
    }

    return this.pythonRunner.runJsonScript('save_criteria_results.py', {
      input: {
        search_id: searchId,
        criteria: criteria || {},
        results: results || [],
      },
    });
  }
}

module.exports = {
  LlmAnalysisService,
};

const { PythonRunner } = require('./pythonRunner');
const crypto = require('crypto');

const MAX_CACHE_ENTRIES = 100;

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

    const input = {
      criteriosInclusao: payload.criteriosInclusao,
      criteriosExclusao: payload.criteriosExclusao,
      artigos,
      model: payload.model,
      temperature: payload.temperature,
      tokens: payload.tokens,
      ollamaUrl: payload.ollamaUrl,
      extraPrompt: payload.extraPrompt,
      maxWorkers: payload.maxWorkers,
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
}

module.exports = {
  LlmAnalysisService,
};

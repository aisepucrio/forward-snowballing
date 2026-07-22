const { PythonRunner } = require('./pythonRunner');

class LlmAnalysisService {
  constructor({ pythonRunner = new PythonRunner({ defaultTimeoutMs: 5 * 60 * 1000 }) } = {}) {
    this.pythonRunner = pythonRunner;
  }

  async analyze(payload, { abortEmitter = null } = {}) {
    const artigos = Array.isArray(payload.artigos) ? payload.artigos : [];
    if (artigos.length === 0) {
      const err = new Error('Nenhum artigo enviado.');
      err.statusCode = 400;
      throw err;
    }

    return this.pythonRunner.runJsonScript('analisys_LLM.py', {
      input: {
        criteriosInclusao: payload.criteriosInclusao,
        criteriosExclusao: payload.criteriosExclusao,
        artigos,
        model: payload.model,
        temperature: payload.temperature,
        tokens: payload.tokens,
        ollamaUrl: payload.ollamaUrl,
        extraPrompt: payload.extraPrompt,
        maxWorkers: payload.maxWorkers,
      },
      abortEmitter,
    });
  }
}

module.exports = {
  LlmAnalysisService,
};

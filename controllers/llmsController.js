const { LlmAnalysisService } = require('../services/llmAnalysisService');
const { handlePythonRunnerError } = require('./pythonRunnerErrorHandler');

class LlmsController {
  constructor({ llmAnalysisService = new LlmAnalysisService() } = {}) {
    this.llmAnalysisService = llmAnalysisService;
    this.analisar = this.analisar.bind(this);
    this.salvarCriterios = this.salvarCriterios.bind(this);
  }

  async analisar(req, res) {
    const { artigos } = req.body;
    console.log('[LLM] artigos recebidos:', Array.isArray(artigos) ? artigos.length : 0);

    try {
      const resultados = await this.llmAnalysisService.analyze(req.body, { abortEmitter: req });
      res.json(resultados);
    } catch (err) {
      if (err.statusCode !== 499 && err.message && err.message.includes('excedeu')) {
        console.error('Erro na análise LLM:', err.stderr || err.stdout || err.message);
        return res.status(504).json({
          error: 'A análise demorou demais. Tente menos artigos ou um modelo mais rápido.',
        });
      }

      handlePythonRunnerError(err, res, {
        logPrefix: 'Erro na análise LLM',
        genericMessage: 'Erro ao processar os artigos.',
      });
    }
  }

  // Grava critérios + veredito da LLM (criteria/criteria_logs) no banco,
  // chamado uma vez ao fim da análise em criterios.html.
  async salvarCriterios(req, res) {
    try {
      const { search_id: searchId, criteria, results } = req.body;
      const resultado = await this.llmAnalysisService.saveCriteriaResults({ searchId, criteria, results });
      res.json(resultado);
    } catch (err) {
      handlePythonRunnerError(err, res, {
        logPrefix: 'Erro ao salvar critérios',
        genericMessage: 'Erro ao salvar critérios no banco.',
      });
    }
  }
}

module.exports = new LlmsController();
module.exports.LlmsController = LlmsController;

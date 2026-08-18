const { LlmAnalysisService } = require('../services/llmAnalysisService');
const { handlePythonRunnerError } = require('./pythonRunnerErrorHandler');

class LlmsController {
  constructor({ llmAnalysisService = new LlmAnalysisService() } = {}) {
    this.llmAnalysisService = llmAnalysisService;
    this.analisar = this.analisar.bind(this);
  }

  async analisar(req, res) {
    const { artigos, model, ollamaUrl } = req.body;
    console.log('Entrou no llmsController.analisar');
    console.log('[DEBUG] ollamaUrl recebido:', ollamaUrl);
    console.log('[DEBUG] model recebido:', model);
    console.log('[DEBUG] artigos count:', artigos ? artigos.length : 0);

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
}

module.exports = new LlmsController();
module.exports.LlmsController = LlmsController;

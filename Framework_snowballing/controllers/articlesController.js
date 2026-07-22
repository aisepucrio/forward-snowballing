const { ArticleSearchService } = require('../services/articleSearchService');
const { handlePythonRunnerError } = require('./pythonRunnerErrorHandler');

class ArticlesController {
  constructor({ articleSearchService = new ArticleSearchService() } = {}) {
    this.articleSearchService = articleSearchService;
    this.getMockPapers = this.getMockPapers.bind(this);
    this.searchByDOI = this.searchByDOI.bind(this);
    this.marcarArtigo = this.marcarArtigo.bind(this);
    this.getArtigosIncluidos = this.getArtigosIncluidos.bind(this);
  }

  getMockPapers(req, res) {
    const citations = this.articleSearchService.getCitations(req.sessionId);
    if (!citations) {
      return res.status(404).json({ error: 'Citações não encontradas para esta sessão.' });
    }

    res.json(citations);
  }

  async searchByDOI(req, res) {
    try {
      const data = await this.articleSearchService.search({
        sessionId: req.sessionId,
        doi: req.query.doi,
        title: req.query.title,
        type: req.query.type || 'forward',
        abortEmitter: req,
      });

      res.json(data);
    } catch (err) {
      handlePythonRunnerError(err, res, {
        logPrefix: 'Erro ao buscar artigo',
        genericMessage: 'Erro ao buscar o artigo via script Python.',
      });
    }
  }

  marcarArtigo(req, res) {
    try {
      const { paperId, status } = req.body;
      this.articleSearchService.markArticle(req.sessionId, paperId, status);
      res.json({ success: true });
    } catch (err) {
      res.status(err.statusCode || 500).json({ error: err.message || 'Erro ao salvar o status' });
    }
  }

  getArtigosIncluidos(req, res) {
    try {
      res.json(this.articleSearchService.getIncludedArticles(req.sessionId));
    } catch (err) {
      res.status(err.statusCode || 500).json({ error: err.message || 'Erro ao carregar as citações' });
    }
  }
}

module.exports = new ArticlesController();
module.exports.ArticlesController = ArticlesController;

const { ArticleSearchService } = require('../services/articleSearchService');
const { handlePythonRunnerError } = require('./pythonRunnerErrorHandler');

class ArticlesController {
  constructor({ articleSearchService = new ArticleSearchService() } = {}) {
    this.articleSearchService = articleSearchService;
    this.getMockPapers = this.getMockPapers.bind(this);
    this.searchByDOI = this.searchByDOI.bind(this);
    this.marcarArtigo = this.marcarArtigo.bind(this);
    this.getArtigosIncluidos = this.getArtigosIncluidos.bind(this);
    this.updateFlag = this.updateFlag.bind(this);
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

  // Atualiza as flags de um paper no PostgreSQL:
  // selected_first_page, excluded_duplicate, duplicate_of
  async updateFlag(req, res) {
    try {
      const result = await this.articleSearchService.updateFlag({
        searchId: req.body.search_id,
        paperId: req.body.paper_id,
        selectedFirstPage: req.body.selected_first_page,
        excludedDuplicate: req.body.excluded_duplicate,
        duplicateOf: req.body.duplicate_of,
      });

      res.json(result);
    } catch (err) {
      handlePythonRunnerError(err, res, {
        logPrefix: 'Erro ao atualizar flag',
        genericMessage: 'Erro ao atualizar flag no banco.',
      });
    }
  }
}

module.exports = new ArticlesController();
module.exports.ArticlesController = ArticlesController;

const { ArticleSearchService } = require('../services/articleSearchService');
const { handlePythonRunnerError } = require('./pythonRunnerErrorHandler');
const { EventEmitter } = require('events');
const { parseProgressLine } = require('../services/searchProgress');

class ArticlesController {
  constructor({ articleSearchService = new ArticleSearchService() } = {}) {
    this.articleSearchService = articleSearchService;
    this.getMockPapers = this.getMockPapers.bind(this);
    this.searchByDOI = this.searchByDOI.bind(this);
    this.searchMulti = this.searchMulti.bind(this);
    this.marcarArtigo = this.marcarArtigo.bind(this);
    this.getArtigosIncluidos = this.getArtigosIncluidos.bind(this);
    this.updateFlag = this.updateFlag.bind(this);
    this.updateFlagBatch = this.updateFlagBatch.bind(this);
  }

  getMockPapers(req, res) {
    const citations = this.articleSearchService.getCitations(req.sessionId);
    if (!citations) {
      return res.status(404).json({ error: 'Citações não encontradas para esta sessão.' });
    }

    res.json(citations);
  }

  // A busca leva ~50s e pode passar de 3 minutos. Quem pede NDJSON recebe os
  // marcos de progresso conforme eles acontecem e o resultado na última linha;
  // quem não pede continua recebendo o mesmo JSON único de antes, para não
  // quebrar nenhum consumidor que já exista.
  async searchByDOI(req, res) {
    // req.query.type não é mais lido: a busca é sempre a completa, que já
    // devolve citations e references. Uma chamada antiga com ?type=backward
    // continua funcionando e recebe as referências que pedia — agora
    // acompanhadas das citações.
    return this.streamSearch(req, res, (onProgress, abortEmitter) => this.articleSearchService.search({
      sessionId: req.sessionId,
      doi: req.query.doi,
      title: req.query.title,
      abortEmitter,
      onProgress,
    }), {
      logPrefix: 'Erro ao buscar artigo',
      genericMessage: 'Erro ao buscar o artigo via script Python.',
    });
  }

  // Várias seeds numa busca só. Mesmo protocolo de searchByDOI (NDJSON com
  // progresso, ou JSON único); com N seeds a espera é N vezes maior, então o
  // progresso por seed é o que diz ao usuário que a busca está andando.
  async searchMulti(req, res) {
    return this.streamSearch(req, res, (onProgress, abortEmitter) => this.articleSearchService.searchMulti({
      sessionId: req.sessionId,
      seeds: req.body && req.body.seeds,
      abortEmitter,
      onProgress,
    }), {
      logPrefix: 'Erro na busca com várias seeds',
      genericMessage: 'Erro ao buscar as seeds via script Python.',
    });
  }

  async streamSearch(req, res, runSearch, { logPrefix, genericMessage }) {
    const wantsStream = String(req.headers.accept || '').includes('application/x-ndjson');

    let streaming = false;
    let ultimaMensagem = null;

    // Cliente que desiste (fecha a aba, cancela o fetch) precisa matar o
    // processo Python. req 'aborted' não dispara no Node atual depois que o
    // corpo da requisição já foi lido — e o processo seguia consumindo o
    // limite das APIs por minutos. O 'close' da resposta antes de ela
    // terminar é o sinal confiável.
    const abortEmitter = new EventEmitter();
    res.on('close', () => {
      if (!res.writableFinished) abortEmitter.emit('aborted');
    });

    const enviarProgresso = (linha) => {
      if (!streaming) return;

      const progresso = parseProgressLine(linha);
      // O mesmo marco pode sair repetido (o aviso de banco indisponível sai uma
      // vez por direção gravada, por exemplo) — repetir na tela só faz parecer
      // que a busca está patinando.
      if (!progresso || progresso.message === ultimaMensagem) return;

      ultimaMensagem = progresso.message;
      res.write(`${JSON.stringify({ type: 'progress', ...progresso })}\n`);
    };

    try {
      const data = await runSearch(wantsStream
        ? (linha) => {
          if (!streaming) {
            streaming = true;
            res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8');
            res.setHeader('Cache-Control', 'no-store');
            // Sem isso o nginx segura a resposta inteira no buffer e o
            // progresso só apareceria junto com o resultado — ou seja, nunca.
            res.setHeader('X-Accel-Buffering', 'no');
            res.write(`${JSON.stringify({ type: 'progress', stage: 'start', message: 'Starting search…' })}\n`);
          }
          enviarProgresso(linha);
        }
        : null, abortEmitter);

      if (streaming) {
        res.write(`${JSON.stringify({ type: 'result', data })}\n`);
        res.end();
        return;
      }

      res.json(data);
    } catch (err) {
      // Erro depois que a resposta já começou não pode mais virar status HTTP:
      // vai como última linha do stream, e o cliente decide o que mostrar.
      if (res.headersSent || streaming) {
        if (err.statusCode !== 499) {
          console.error(logPrefix, err.stderr || err.message);
          res.write(`${JSON.stringify({ type: 'error', error: err.message || genericMessage })}\n`);
        }
        res.end();
        return;
      }

      handlePythonRunnerError(err, res, { logPrefix, genericMessage });
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

  // Grava várias flags de uma vez (botão "Save Research State" da triagem),
  // numa única conexão com o banco em vez de uma por item.
  async updateFlagBatch(req, res) {
    try {
      const result = await this.articleSearchService.updateFlagBatch(req.body.updates);
      res.json(result);
    } catch (err) {
      handlePythonRunnerError(err, res, {
        logPrefix: 'Erro ao atualizar flags em lote',
        genericMessage: 'Erro ao atualizar flags no banco.',
      });
    }
  }
}

module.exports = new ArticlesController();
module.exports.ArticlesController = ArticlesController;

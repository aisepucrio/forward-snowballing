const express = require('express');
const router = express.Router();
const articlesController = require('../controllers/articlesController');
const llmsController = require('../controllers/llmsController'); // nome corrigido aqui

// Rota para os mock papers (triagem)
router.get('/mock-papers', articlesController.getMockPapers);

router.get('/search', articlesController.searchByDOI);
router.post('/marcar', articlesController.marcarArtigo);
router.get('/artigos/incluidos', articlesController.getArtigosIncluidos);

// atualizando flags do BD
router.post('/flag', articlesController.updateFlag);
router.post('/flag/batch', articlesController.updateFlagBatch);

// Rota que recebe os critérios e os artigos
router.post('/', llmsController.analisar); // nome corrigido aqui também
router.post('/analisar', llmsController.analisar);

// Grava critérios de inclusão/exclusão + veredito da LLM no banco
router.post('/criteria', llmsController.salvarCriterios);

module.exports = router;

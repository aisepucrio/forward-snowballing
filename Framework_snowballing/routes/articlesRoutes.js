const express = require('express');
const router = express.Router();
const articlesController = require('../controllers/articlesController');
const llmsController = require('../controllers/llmsController'); // nome corrigido aqui

// Rota para os mock papers (triagem)
router.get('/mock-papers', articlesController.getMockPapers);

router.get('/search', articlesController.searchByDOI);
router.post('/marcar', articlesController.marcarArtigo);
router.get('/artigos/incluidos', articlesController.getArtigosIncluidos);

// Rota que recebe os critérios e os artigos
router.post('/', llmsController.analisar); // nome corrigido aqui também
router.post('/analisar', llmsController.analisar);

module.exports = router;

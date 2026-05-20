const path = require('path');
const { exec, execSync } = require('child_process');
const { readOutput, writeOutput } = require('../services/sessionState');


function lerOutput(req) {
  return readOutput(req.sessionId);
}

function escapeShellArg(value) {
  if (value === undefined || value === null) return '-';
  return String(value).replace(/"/g, '\\"');
}

function tryCommand(command) {
  try {
    return execSync(command, { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
  } catch {
    return null;
  }
}

function findPythonExecutable() {
  if (process.platform === 'win32') {
    return tryCommand('where python') || tryCommand('where python3');
  }

  return tryCommand('which python3') || tryCommand('which python');
}

// Retorna as citações do output.json da sessão atual
exports.getMockPapers = (req, res) => {
  const data = lerOutput(req);
  if (!data || !Array.isArray(data.citations)) {
    return res.status(404).json({ error: 'Citações não encontradas para esta sessão.' });
  }

  res.json(data.citations);
};

// Busca o artigo pelo DOI ou título, executando o script Python
exports.searchByDOI = (req, res) => {
  const doi = req.query.doi || '-';
  const title = req.query.title || '-';
  const type = req.query.type || 'forward';
  const scriptName = type === 'backward' ? 'run_backward.py' : 'run_forward.py';
  const pathToPythonScript = path.join(__dirname, '..', 'scripts', scriptName);

  if ((!doi || doi === '-') && (!title || title === '-')) {
    return res.status(400).json({ error: 'DOI ou título devem ser informados' });
  }

  const safeDoi = escapeShellArg(doi);
  const safeTitle = escapeShellArg(title);

  const pythonPath = findPythonExecutable();
  const command = `"${pythonPath}" -X utf8 "${pathToPythonScript}" "${safeDoi}" "${safeTitle}"`;

  console.log('Executando comando:', command);
  console.log('DOI recebido:', doi);
  console.log('TITLE recebido:', title);

  exec(command, (error, stdout, stderr) => {
    if (error) {
      console.error('Erro executando script Python:', stderr || stdout || error.message);
      return res.status(500).json({
        error: stderr || stdout || 'Erro ao buscar o artigo via script Python.'
      });
    }

    try {
      const data = JSON.parse(stdout);
      writeOutput(req.sessionId, data);
      res.json(data);
    } catch (e) {
      console.error('Erro ao processar JSON do script Python:', e);
      console.error('STDOUT recebido:', stdout);
      console.error('STDERR recebido:', stderr);
      res.status(500).json({ error: 'Erro ao processar resposta do script Python.' });
    }
  });
};

// Marca o artigo com status ("incluir", "excluir", "talvez")
exports.marcarArtigo = (req, res) => {
  const { paperId, status } = req.body;

  if (!paperId || !status) {
    return res.status(400).json({ error: 'paperId e status são obrigatórios' });
  }

  const data = lerOutput(req);
  if (!data || !Array.isArray(data.citations)) {
    return res.status(500).json({ error: 'Erro ao carregar as citações' });
  }

  const artigo = data.citations.find((a) => a.paperId === paperId);
  if (!artigo) {
    return res.status(404).json({ error: 'Artigo não encontrado' });
  }

  artigo.selecionado = status;

  try {
    writeOutput(req.sessionId, data);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Erro ao salvar o status' });
  }
};

// Retorna os artigos marcados como "incluir"
exports.getArtigosIncluidos = (req, res) => {
  const data = lerOutput(req);
  if (!data || !Array.isArray(data.citations)) {
    return res.status(500).json({ error: 'Erro ao carregar as citações' });
  }

  const incluidos = data.citations.filter((a) => a.selecionado === 'incluir');
  res.json(incluidos);
};

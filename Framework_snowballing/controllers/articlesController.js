const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

const outputPath = path.join(__dirname, '../output.json');



function lerOutput() {
  if (!fs.existsSync(outputPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(outputPath, 'utf-8'));
  } catch {
    return null;
  }
}

function escapeShellArg(value) {
  if (value === undefined || value === null) return '-';
  return String(value).replace(/"/g, '\\"');
}

const { execSync } = require('child_process');

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

// Retorna as citações do output.json
exports.getMockPapers = (req, res) => {
  const data = lerOutput();
  if (!data || !Array.isArray(data.citations)) {
    return res.status(404).json({ error: 'Citações não encontradas no output.json' });
  }

  res.json(data.citations);
};

// Busca o artigo pelo DOI ou título, executando o script Python
exports.searchByDOI = (req, res) => {
  const doi = req.query.doi || '-';
  const title = req.query.title || '-';
  const scriptName = 'run_backward.py';
  const pathToPythonScript = path.join(__dirname, '..', 'scripts', scriptName); 

  if ((!doi || doi === '-') && (!title || title === '-')) {
    return res.status(400).json({ error: 'DOI ou título devem ser informados' });
  }

  const safeDoi = escapeShellArg(doi);
  const safeTitle = escapeShellArg(title);

  const pythonPath = findPythonExecutable()
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
      fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf-8');
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

  const data = lerOutput();
  if (!data || !Array.isArray(data.citations)) {
    return res.status(500).json({ error: 'Erro ao carregar as citações' });
  }

  const artigo = data.citations.find(a => a.paperId === paperId);
  if (!artigo) {
    return res.status(404).json({ error: 'Artigo não encontrado' });
  }

  artigo.selecionado = status;

  try {
    fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf-8');
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'Erro ao salvar o status' });
  }
};

// Retorna os artigos marcados como "incluir"
exports.getArtigosIncluidos = (req, res) => {
  const data = lerOutput();
  if (!data || !Array.isArray(data.citations)) {
    return res.status(500).json({ error: 'Erro ao carregar as citações' });
  }

  const incluidos = data.citations.filter(a => a.selecionado === 'incluir');
  res.json(incluidos);
};
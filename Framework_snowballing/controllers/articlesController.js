const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

const outputPath = path.join(__dirname, '../output.json');
const pathToPythonScript = path.join(__dirname, '..', 'scripts', 'run_forward.py');
const pathToForward = path.join(__dirname, '..', 'scripts', 'run_forward.py');
const pathToBackward = path.join(__dirname, '..', 'scripts', 'run_backward.py');

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

// Retorna as citações do output.json
exports.getMockPapers = (req, res) => {
  const data = lerOutput();
  if (!data) return res.status(404).json({ error: 'Dados não encontrados' });

  // Se for backward, os dados estão em 'references'. Se forward, em 'citations'.
  const papers = data.references || data.citations || [];
  res.json(papers);
};

// Busca o artigo pelo DOI ou título, executando o script Python
exports.searchByDOI = (req, res) => {
  const doi = req.query.doi || '-';
  const title = req.query.title || '-';
  const type = req.query.type || 'forward'; // Novo: 'forward' ou 'backward'

  if ((!doi || doi === '-') && (!title || title === '-')) {
    return res.status(400).json({ error: 'DOI ou título devem ser informados' });
  }

  const safeDoi = escapeShellArg(doi);
  const safeTitle = escapeShellArg(title);
  
  // Escolhe o script com base no tipo
  const scriptPath = type === 'backward' ? pathToBackward : pathToForward;
  const command = `python3 "${scriptPath}" "${safeDoi}" "${safeTitle}"`;

  console.log(`Executando ${type}:`, command);

  exec(command, (error, stdout, stderr) => {
    if (error) {
      return res.status(500).json({ error: stderr || 'Erro ao executar script Python.' });
    }

    try {
      const data = JSON.parse(stdout);
      fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf-8');
      res.json(data);
    } catch (e) {
      res.status(500).json({ error: 'Erro ao processar resposta do script.' });
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
const path = require('path');
const fs = require('fs');
const { exec } = require('child_process');

const outputPath = path.join(__dirname, '../output.json');
const pathToPythonScript = path.join(__dirname, '..', 'scripts', 'run_forward.py');
function lerOutput() {
  if (!fs.existsSync(outputPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(outputPath, 'utf-8'));
  } catch {
    return null;
  }
}

// Retorna as citações do output.json
exports.getMockPapers = (req, res) => {
  const data = lerOutput();
  if (!data || !Array.isArray(data.citations)) {
    return res.status(404).json({ error: 'Citações não encontradas no output.json' });
  }

  res.json(data.citations);
};

// Busca o artigo pelo DOI, executando o script Python para atualizar os dados
exports.searchByDOI = (req, res) => {
  const { doi } = req.query;

  if (!doi) {
    return res.status(400).json({ error: 'DOI não fornecido' });
  }

  // Comando com aspas para proteger espaços e caracteres especiais
  const command = `python3 "${pathToPythonScript}" ${doi}`;

  exec(command, (error, stdout, stderr) => {
    if (error) {
      console.error('Erro executando script Python:', stderr);
      return res.status(500).json({ error: 'Erro ao buscar o artigo via script Python.' });
    }

    try {
      const data = JSON.parse(stdout);
      fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf-8');
      res.json(data);
    } catch (e) {
      console.error('Erro ao processar JSON do script Python:', e);
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

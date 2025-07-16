const path = require('path');
const { spawn } = require('child_process');

exports.analisar = (req, res) => {
  const { criteriosInclusao, criteriosExclusao, artigos } = req.body;
  console.log('Entrou no llmsController.analisar');
  if (!artigos || artigos.length === 0) {
    return res.status(400).json({ error: "Nenhum artigo enviado." });
  }

  const input = JSON.stringify({ criteriosInclusao, criteriosExclusao, artigos });

  // Caminho absoluto para o script Python:
  const scriptPath = path.join(__dirname, '..', 'scripts', 'analisa.py');

  const pythonProcess = spawn('python3', [scriptPath]);

  let output = '';
  let errorOutput = '';

  pythonProcess.stdout.on('data', (data) => { output += data.toString(); });
  pythonProcess.stderr.on('data', (data) => { errorOutput += data.toString(); });

  pythonProcess.on('close', (code) => {
    if (code !== 0) {
      console.error('Erro no script Python:', errorOutput);
      return res.status(500).json({ error: 'Erro ao processar os artigos.' });
    }
    try {
      const resultados = JSON.parse(output);
      res.json(resultados);
    } catch (err) {
      console.error('Erro ao parsear JSON do Python:', err);
      res.status(500).json({ error: 'Resposta inválida do script Python.' });
    }
  });

  pythonProcess.stdin.write(input);
  pythonProcess.stdin.end();
};

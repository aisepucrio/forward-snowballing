const path = require('path');
const { spawn, execSync } = require('child_process');

function findPythonExecutable() {
  const cmd = process.platform === 'win32' ? 'where' : 'which';
  for (const name of ['python3', 'python']) {
    try {
      return execSync(`${cmd} ${name}`, { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
    } catch {}
  }
  return 'python3';
}

const pythonPath = findPythonExecutable();

exports.analisar = (req, res) => {
  const { criteriosInclusao, criteriosExclusao, artigos } = req.body;
  if (!artigos || artigos.length === 0) {
    return res.status(400).json({ error: "Nenhum artigo enviado." });
  }

  const input = JSON.stringify({ criteriosInclusao, criteriosExclusao, artigos });
  const scriptPath = path.join(__dirname, '..', 'scripts', 'analisys_LLM.py');
  const pythonProcess = spawn(pythonPath, [scriptPath]);

  let output = '';
  let errorOutput = '';

  pythonProcess.on('error', (err) => {
    console.error('Falha ao iniciar Python:', err.message);
    res.status(500).json({ error: 'Não foi possível iniciar o interpretador Python.' });
  });

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

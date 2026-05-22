const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

function tryCommand(command) {
  try {
    return execSync(command, { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
  } catch {
    return null;
  }
}

function findPythonExecutable() {
  const projectRoot = path.join(__dirname, '..');
  const venvCandidates = process.platform === 'win32'
    ? [
        path.join(projectRoot, '.venv', 'Scripts', 'python.exe'),
        path.join(projectRoot, 'venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.join(projectRoot, '.venv', 'bin', 'python'),
        path.join(projectRoot, 'venv', 'bin', 'python'),
      ];

  for (const candidate of venvCandidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  if (process.platform === 'win32') {
    return tryCommand('where python') || tryCommand('where python3');
  }

  return tryCommand('which python3') || tryCommand('which python');
}

exports.analisar = (req, res) => {
  const { criteriosInclusao, criteriosExclusao, artigos } = req.body;
  console.log('Entrou no llmsController.analisar');
  if (!artigos || artigos.length === 0) {
    return res.status(400).json({ error: "Nenhum artigo enviado." });
  }

  const input = JSON.stringify({ criteriosInclusao, criteriosExclusao, artigos });

  // Caminho absoluto para o script Python:
  const scriptPath = path.join(__dirname, '..', 'scripts', 'analisys_LLM.py');
  const pythonPath = findPythonExecutable();

  if (!pythonPath) {
    return res.status(500).json({ error: 'Python não encontrado no servidor.' });
  }

  const pythonProcess = spawn(pythonPath, [scriptPath]);

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

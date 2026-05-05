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

  let pythonProcess;
  try {
    pythonProcess = spawn(pythonPath, [scriptPath]);
  } catch (spawnErr) {
    console.error('Erro ao fazer spawn do Python:', spawnErr.message);
    return res.status(500).json({ error: 'Não foi possível iniciar o interpretador Python.' });
  }

  let output = '';
  let errorOutput = '';
  let responded = false;

  function sendError(status, msg) {
    if (!responded) {
      responded = true;
      res.status(status).json({ error: msg });
    }
  }

  pythonProcess.on('error', (err) => {
    console.error('Falha ao iniciar Python:', err.message);
    sendError(500, 'Não foi possível iniciar o interpretador Python.');
  });

  pythonProcess.stdin.on('error', () => {});

  pythonProcess.stdout.on('data', (data) => { output += data.toString(); });
  pythonProcess.stderr.on('data', (data) => { errorOutput += data.toString(); });

  pythonProcess.on('close', (code) => {
    if (code !== 0) {
      console.error('Erro no script Python:', errorOutput);
      return sendError(500, 'Erro ao processar os artigos.');
    }
    try {
      const resultados = JSON.parse(output);
      if (!responded) {
        responded = true;
        res.json(resultados);
      }
    } catch (err) {
      console.error('Erro ao parsear JSON do Python:', err.message);
      console.error('Output recebido:', output.substring(0, 300));
      sendError(500, 'Resposta inválida do script Python.');
    }
  });

  try {
    pythonProcess.stdin.write(input);
    pythonProcess.stdin.end();
  } catch (writeErr) {
    console.error('Erro ao escrever no stdin:', writeErr.message);
    sendError(500, 'Erro ao enviar dados para o script Python.');
  }
};

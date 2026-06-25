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
  const { criteriosInclusao, criteriosExclusao, artigos, model, temperature, tokens, ollamaUrl, extraPrompt, maxWorkers } = req.body;
  console.log('Entrou no llmsController.analisar');
  console.log('[DEBUG] ollamaUrl recebido:', ollamaUrl);
  console.log('[DEBUG] model recebido:', model);
  console.log('[DEBUG] artigos count:', artigos ? artigos.length : 0);
  if (!artigos || artigos.length === 0) {
    return res.status(400).json({ error: "Nenhum artigo enviado." });
  }

  const input = JSON.stringify({ criteriosInclusao, criteriosExclusao, artigos, model, temperature, tokens, ollamaUrl, extraPrompt, maxWorkers });

  // Caminho absoluto para o script Python:
  const scriptPath = path.join(__dirname, '..', 'scripts', 'analisys_LLM.py');
  const pythonPath = findPythonExecutable();

  if (!pythonPath) {
    return res.status(500).json({ error: 'Python não encontrado no servidor.' });
  }

  console.log('[DEBUG] Python LLM path:', pythonPath);
  const pythonProcess = spawn(pythonPath, [scriptPath]);
  let finished = false;

  const timeoutMs = 5 * 60 * 1000;
  const timeout = setTimeout(() => {
    if (finished) return;
    finished = true;
    pythonProcess.kill('SIGTERM');
    console.error(`Análise LLM excedeu ${timeoutMs / 1000}s e foi interrompida.`);
    if (!res.headersSent) {
      res.status(504).json({
        error: 'A análise demorou demais. Tente menos artigos ou um modelo mais rápido.'
      });
    }
  }, timeoutMs);

  req.on('aborted', () => {
    if (finished) return;
    console.error('Cliente abortou a análise LLM; aguardando processo Python finalizar.');
  });

  let output = '';
  let errorOutput = '';

  pythonProcess.stdout.on('data', (data) => { output += data.toString(); });
  pythonProcess.stderr.on('data', (data) => { errorOutput += data.toString(); });
  pythonProcess.on('error', (err) => {
    if (finished) return;
    finished = true;
    clearTimeout(timeout);
    console.error('Erro ao iniciar script Python:', err);
    if (!res.headersSent) {
      res.status(500).json({ error: 'Erro ao iniciar o script Python.' });
    }
  });

  pythonProcess.on('close', (code) => {
    if (finished) return;
    finished = true;
    clearTimeout(timeout);
    console.log('[DEBUG] Python LLM finalizou com code:', code);
    if (errorOutput) {
      console.error('[DEBUG] Python LLM stderr:', errorOutput);
    }
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

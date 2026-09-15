const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

const MAX_OUTPUT_BYTES = 10 * 1024 * 1024;

// Lê a mensagem de {"error": "..."} que os scripts imprimem no stdout ao
// falhar de forma esperada. Devolve null quando o stdout não é esse formato,
// para quem chama cair no stderr.
function extractScriptError(stdout) {
  const text = String(stdout || '').trim();
  if (!text) return null;

  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed.error === 'string' ? parsed.error : null;
  } catch {
    return null;
  }
}

class PythonRunner {
  constructor({ projectRoot, defaultTimeoutMs = 5 * 60 * 1000 } = {}) {
    this.projectRoot = projectRoot || path.join(__dirname, '..');
    this.scriptsDir = path.join(this.projectRoot, 'scripts');
    this.defaultTimeoutMs = defaultTimeoutMs;
    this.resolvedExecutable = null;
  }

  findExecutable() {
    if (this.resolvedExecutable) {
      return this.resolvedExecutable;
    }

    const venvCandidates = process.platform === 'win32'
      ? [
          path.join(this.projectRoot, '.venv', 'Scripts', 'python.exe'),
          path.join(this.projectRoot, 'venv', 'Scripts', 'python.exe'),
        ]
      : [
          path.join(this.projectRoot, '.venv', 'bin', 'python'),
          path.join(this.projectRoot, 'venv', 'bin', 'python'),
        ];

    for (const candidate of venvCandidates) {
      if (fs.existsSync(candidate)) {
        this.resolvedExecutable = candidate;
        return this.resolvedExecutable;
      }
    }

    this.resolvedExecutable = process.platform === 'win32'
      ? this.tryCommand('where python') || this.tryCommand('where python3')
      : this.tryCommand('which python3') || this.tryCommand('which python');

    return this.resolvedExecutable;
  }

  tryCommand(command) {
    try {
      return execSync(command, { encoding: 'utf8' }).split(/\r?\n/)[0].trim();
    } catch {
      return null;
    }
  }

  runJsonScript(scriptName, { args = [], input = null, timeoutMs = this.defaultTimeoutMs, abortEmitter = null, onStderrLine = null } = {}) {
    return new Promise((resolve, reject) => {
      const pythonPath = this.findExecutable();
      if (!pythonPath) {
        reject(new Error('Python não encontrado no servidor.'));
        return;
      }

      const scriptPath = path.join(this.scriptsDir, scriptName);
      // stdin/stdout em UTF-8, igual ao que o Node escreve e lê. Sem isso o
      // Python no Windows usa cp1252: a entrada chega corrompida aos scripts e
      // a saída só "funciona" porque a corrupção se desfaz na volta.
      const pythonProcess = spawn(pythonPath, [scriptPath, ...args], {
        cwd: this.projectRoot,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      });

      let output = '';
      let errorOutput = '';
      let finished = false;

      const finish = (callback) => {
        if (finished) return false;
        finished = true;
        if (timeout) clearTimeout(timeout);
        if (abortEmitter) {
          abortEmitter.removeListener('aborted', onAbort);
        }
        callback();
        return true;
      };

      const onAbort = () => {
        finish(() => {
          pythonProcess.kill('SIGTERM');
          const err = new Error('Cliente abortou a requisição.');
          err.statusCode = 499;
          reject(err);
        });
      };

      const timeout = timeoutMs
        ? setTimeout(() => {
          finish(() => {
            pythonProcess.kill('SIGTERM');
            reject(new Error(`Script Python excedeu ${timeoutMs / 1000}s.`));
          });
        }, timeoutMs)
        : null;

      if (abortEmitter) {
        abortEmitter.once('aborted', onAbort);
      }

      const onMaxBufferExceeded = () => {
        finish(() => {
          pythonProcess.kill('SIGTERM');
          reject(new Error('Saída do script Python excedeu o limite permitido.'));
        });
      };

      pythonProcess.stdout.on('data', (data) => {
        output += data.toString();
        if (output.length > MAX_OUTPUT_BYTES) {
          onMaxBufferExceeded();
        }
      });

      // O stderr continua sendo acumulado (é ele que vira mensagem de erro
      // quando o script falha), mas agora também é entregue linha a linha
      // enquanto o processo roda. Os scripts já imprimem marcos de progresso
      // ali ([SOURCE COUNTS], [OPENALEX REFERENCES], [DEDUP COUNTS]); sem isso
      // eles morriam no buffer e a interface ficava girando sem informação.
      // O corte é por linha porque um chunk do stream pode partir uma linha ao
      // meio — repassar o chunk cru entregaria marcos truncados.
      let stderrPending = '';

      pythonProcess.stderr.on('data', (data) => {
        const chunk = data.toString();
        errorOutput += chunk;

        if (onStderrLine) {
          stderrPending += chunk;
          const lines = stderrPending.split(/\r?\n/);
          stderrPending = lines.pop();
          for (const line of lines) {
            if (line.trim()) {
              try {
                onStderrLine(line);
              } catch {
                // Progresso é acessório: se o consumidor falhar (cliente já
                // desconectado, por exemplo), a busca segue normalmente.
              }
            }
          }
        }

        if (errorOutput.length > MAX_OUTPUT_BYTES) {
          onMaxBufferExceeded();
        }
      });

      pythonProcess.on('error', (err) => {
        finish(() => reject(err));
      });

      pythonProcess.on('close', (code) => {
        finish(() => {
          if (code !== 0) {
            // Os scripts sinalizam falha esperada (artigo não encontrado, DOI
            // inválido) escrevendo {"error": "..."} no STDOUT e saindo com 1.
            // Montar a mensagem a partir do stderr fazia o usuário receber a
            // primeira linha de diagnóstico — literalmente "[CACHE MISS]" —
            // em vez do motivo real. O stderr continua sendo o recurso quando
            // não há erro estruturado (traceback, crash).
            const err = new Error(
              extractScriptError(output) || errorOutput || output || 'Erro ao executar script Python.'
            );
            err.code = code;
            err.stderr = errorOutput;
            err.stdout = output;
            reject(err);
            return;
          }

          try {
            resolve(JSON.parse(output));
          } catch (err) {
            err.stdout = output;
            err.stderr = errorOutput;
            reject(err);
          }
        });
      });

      if (input !== null && input !== undefined) {
        pythonProcess.stdin.write(typeof input === 'string' ? input : JSON.stringify(input));
      }
      pythonProcess.stdin.end();
    });
  }
}

module.exports = {
  PythonRunner,
};

const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

const MAX_OUTPUT_BYTES = 10 * 1024 * 1024;

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

  runJsonScript(scriptName, { args = [], input = null, timeoutMs = this.defaultTimeoutMs, abortEmitter = null } = {}) {
    return new Promise((resolve, reject) => {
      const pythonPath = this.findExecutable();
      if (!pythonPath) {
        reject(new Error('Python não encontrado no servidor.'));
        return;
      }

      const scriptPath = path.join(this.scriptsDir, scriptName);
      const pythonProcess = spawn(pythonPath, [scriptPath, ...args], {
        cwd: this.projectRoot,
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

      pythonProcess.stderr.on('data', (data) => {
        errorOutput += data.toString();
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
            const err = new Error(errorOutput || output || 'Erro ao executar script Python.');
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

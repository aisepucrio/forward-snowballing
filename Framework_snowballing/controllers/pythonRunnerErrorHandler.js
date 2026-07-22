function handlePythonRunnerError(err, res, { logPrefix, genericMessage }) {
  if (err.statusCode === 499) {
    console.error(`${logPrefix}: cliente abortou a requisição; processo Python interrompido.`);
    return;
  }

  console.error(logPrefix, err.stderr || err.stdout || err.message);
  res.status(err.statusCode || 500).json({
    error: err.message || genericMessage,
  });
}

module.exports = {
  handlePythonRunnerError,
};

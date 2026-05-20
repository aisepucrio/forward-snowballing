const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const SESSION_COOKIE_NAME = 'snowballing_session';
const SESSIONS_DIR = path.join(__dirname, '..', 'sessions');

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function parseCookies(cookieHeader) {
  const cookies = {};
  if (!cookieHeader) return cookies;

  for (const part of cookieHeader.split(';')) {
    const [rawName, ...rawValue] = part.split('=');
    const name = rawName && rawName.trim();
    if (!name) continue;
    cookies[name] = decodeURIComponent(rawValue.join('=').trim());
  }

  return cookies;
}

function ensureSession(req, res, next) {
  ensureDir(SESSIONS_DIR);

  const cookies = parseCookies(req.headers.cookie);
  let sessionId = cookies[SESSION_COOKIE_NAME];

  if (!sessionId) {
    sessionId = crypto.randomUUID();
    res.setHeader(
      'Set-Cookie',
      `${SESSION_COOKIE_NAME}=${encodeURIComponent(sessionId)}; Path=/; HttpOnly; SameSite=Lax`
    );
  }

  req.sessionId = sessionId;
  next();
}

function getSessionDir(sessionId) {
  const sessionDir = path.join(SESSIONS_DIR, sessionId);
  ensureDir(sessionDir);
  return sessionDir;
}

function getOutputPath(sessionId) {
  return path.join(getSessionDir(sessionId), 'output.json');
}

function readOutput(sessionId) {
  const outputPath = getOutputPath(sessionId);
  if (!fs.existsSync(outputPath)) return null;

  try {
    return JSON.parse(fs.readFileSync(outputPath, 'utf-8'));
  } catch {
    return null;
  }
}

function writeOutput(sessionId, data) {
  const outputPath = getOutputPath(sessionId);
  fs.writeFileSync(outputPath, JSON.stringify(data, null, 2), 'utf-8');
}

module.exports = {
  ensureSession,
  readOutput,
  writeOutput,
};

// Vitest setup — runs BEFORE test files import config, so env vars take effect.
import bcrypt from 'bcryptjs';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

process.env.WEB_PASSWORD = bcrypt.hashSync('test-admin-pass', 8);
process.env.WEB_USER = 'admin';
process.env.SESSION_SECRET = 'test-secret';
process.env.SESSION_TTL_MIN = '60';
process.env.DEVICE_ID = 'bedroom-ac-01';
process.env.TOPIC_PREFIX = 'remote-ac/v1/devices';
const tmp = path.join(os.tmpdir(), `rac-test-${Date.now()}.db`);
process.env.DB_PATH = tmp;
// Ensure cleanup
process.on('exit', () => {
  try {
    fs.unlinkSync(tmp);
  } catch {
    /* ignore */
  }
});

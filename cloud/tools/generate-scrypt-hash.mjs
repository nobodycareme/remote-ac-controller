#!/usr/bin/env node

import crypto from 'node:crypto';

const SALT_BYTES = 16;
const HASH_BYTES = 64;
const FAKE_CI_PREFIX = 'FAKE_CI_ONLY_';

function derive(password, salt) {
  return new Promise((resolve, reject) => {
    crypto.scrypt(password, salt, HASH_BYTES, (error, derivedKey) => {
      if (error) reject(error);
      else resolve(derivedKey);
    });
  });
}

async function createStoredHash(password) {
  if (!password) throw new Error('Password must not be empty.');
  const salt = crypto.randomBytes(SALT_BYTES).toString('hex');
  const hash = await derive(password, salt);
  return `${salt}:${hash.toString('hex')}`;
}

async function verifyStoredHash(password, stored) {
  const parts = stored.split(':');
  if (parts.length !== 2 || !/^[0-9a-f]{32}$/i.test(parts[0]) || !/^[0-9a-f]{128}$/i.test(parts[1])) return false;
  const expected = Buffer.from(parts[1], 'hex');
  const actual = await derive(password, parts[0]);
  return crypto.timingSafeEqual(expected, actual);
}

async function readMasked(prompt) {
  if (!process.stdin.isTTY || !process.stdout.isTTY || typeof process.stdin.setRawMode !== 'function') {
    throw new Error('Interactive masking is unavailable; pipe two password lines through stdin instead.');
  }
  process.stdout.write(prompt);
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.setEncoding('utf8');
  return new Promise((resolve, reject) => {
    let value = '';
    const finish = (error) => {
      process.stdin.off('data', onData);
      process.stdin.setRawMode(false);
      process.stdin.pause();
      process.stdout.write('\n');
      if (error) reject(error);
      else resolve(value);
    };
    const onData = (character) => {
      if (character === '\u0003') return finish(new Error('Cancelled.'));
      if (character === '\r' || character === '\n') return finish();
      if (character === '\u0008' || character === '\u007f') value = value.slice(0, -1);
      else if (character >= ' ') value += character;
    };
    process.stdin.on('data', onData);
  });
}

async function readPasswords() {
  if (process.stdin.isTTY) return [await readMasked('Owner password: '), await readMasked('Confirm password: ')];
  const input = await new Promise((resolve) => {
    let value = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { value += chunk; });
    process.stdin.on('end', () => resolve(value));
  });
  const lines = input.split(/\r?\n/);
  return [lines[0] ?? '', lines[1] ?? ''];
}

async function selfTest() {
  const fakePassword = `${FAKE_CI_PREFIX}owner-password-123!`;
  const first = await createStoredHash(fakePassword);
  const second = await createStoredHash(fakePassword);
  if (first === second) throw new Error('Random salts were not applied.');
  if (!(await verifyStoredHash(fakePassword, first))) throw new Error('Generated hash did not verify.');
  if (await verifyStoredHash(`${fakePassword}-wrong`, first)) throw new Error('Wrong password verified.');
  if (!/^[0-9a-f]{32}:[0-9a-f]{128}$/i.test(first)) throw new Error('Stored hash format is invalid.');
  try {
    await createStoredHash('');
    throw new Error('Empty password was accepted.');
  } catch (error) {
    if (error.message === 'Empty password was accepted.') throw error;
  }
  process.stdout.write('SCRYPT_SELF_TEST_PASS=True\n');
}

async function main() {
  if (process.argv.includes('--self-test')) return selfTest();
  const ciIndex = process.argv.indexOf('--ci-test-password');
  if (ciIndex !== -1) {
    const fakePassword = process.argv[ciIndex + 1] ?? '';
    if (!fakePassword.startsWith(FAKE_CI_PREFIX)) throw new Error(`CI test passwords must start with ${FAKE_CI_PREFIX}.`);
    process.stdout.write(`${await createStoredHash(fakePassword)}\n`);
    return;
  }
  const [password, confirmation] = await readPasswords();
  if (!password) throw new Error('Password must not be empty.');
  if (password !== confirmation) throw new Error('Password confirmation does not match.');
  process.stdout.write(`${await createStoredHash(password)}\n`);
}

main().catch((error) => {
  process.stderr.write(`Error: ${error.message}\n`);
  process.exitCode = 1;
});

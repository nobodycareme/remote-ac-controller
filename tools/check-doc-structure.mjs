#!/usr/bin/env node
// 校验双语文档目录结构：中文文件名本地化、英文文件名无 _EN 后缀、
// 必备文档齐全、根级 GitHub 约定文件存在。
// 用法: node tools/check-doc-structure.mjs [--json]
import { readdirSync, existsSync, readFileSync, statSync } from 'node:fs';
import { join, dirname, resolve, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const zhDir = join(repoRoot, 'docs', '中文');
const enDir = join(repoRoot, 'docs', 'English');

const REQUIRED_ZH = [
  '系统架构.md', '部署指南.md', '硬件说明.md', '接线说明.md', '红外学习.md',
  'MQTT协议.md', '安全模型.md', '定时任务.md', '温度自动控制.md',
  '运维指南.md', '低配置服务器部署.md', '故障排查.md', '备份与恢复.md',
];
const REQUIRED_EN = [
  'architecture.md', 'deployment.md', 'hardware.md', 'wiring.md', 'ir-learning.md',
  'mqtt-protocol.md', 'security-model.md', 'scheduling.md', 'temperature-automation.md',
  'operations-guide.md', 'resource-constrained-deployment.md', 'troubleshooting.md',
  'backup-and-recovery.md',
];
const REQUIRED_ROOT = [
  'README.md', 'LICENSE', 'NOTICE',
  'SECURITY.md', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md',
];

const SKIP_DIRS = new Set([
  '.git', 'node_modules', 'dist', 'build', '.pio', '.vite', 'coverage', '.venv',
]);
const VENDORED_PREFIXES = [
  'firmware/lib/Adafruit Unified Sensor/', 'firmware/lib/ArduinoJson/',
  'firmware/lib/DHT sensor library/', 'firmware/lib/PubSubClient/',
  'firmware/lib/srun-c/',
];

function walkAll(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      walkAll(join(dir, e.name), out);
    } else if (e.isFile()) {
      out.push(relative(repoRoot, join(dir, e.name)).split(sep).join('/'));
    }
  }
  return out;
}

const allFiles = walkAll(repoRoot);
const isVendored = (p) => VENDORED_PREFIXES.some((v) => p.startsWith(v));

const ls = (d) => (existsSync(d) ? readdirSync(d).filter((f) => f.endsWith('.md')).sort() : []);
const zhFiles = ls(zhDir);
const enFiles = ls(enDir);

const hasHan = (s) => /[\u4e00-\u9fff]/.test(s);

const results = {};

results.chineseDirectoryExists = existsSync(zhDir);
results.englishDirectoryExists = existsSync(enDir);

results.missingChineseDocs = REQUIRED_ZH.filter((f) => !zhFiles.includes(f));
results.missingEnglishDocs = REQUIRED_EN.filter((f) => !enFiles.includes(f));

// 中文目录文件名必须含汉字（技术缩写开头的如 MQTT协议.md 也含汉字）
results.chineseFilenamesNotLocalized = zhFiles.filter((f) => !hasHan(f));

// 英文目录文件名不得含 _EN 后缀，也不得含汉字
results.englishFilenamesWithEnSuffix = enFiles.filter((f) => /_EN\.md$/i.test(f));
results.englishFilenamesWithHan = enFiles.filter((f) => hasHan(f));

// 全仓（排除 vendored）不得存在 *_EN.md / README_EN.*
results.repoWideEnSuffixFiles = allFiles.filter(
  (p) => !isVendored(p) && /(^|\/)[^/]*_EN\.[A-Za-z0-9]+$/.test(p),
);
results.vendoredEnSuffixFiles = allFiles.filter(
  (p) => isVendored(p) && /(^|\/)[^/]*_EN\.[A-Za-z0-9]+$/.test(p),
);

results.missingRootFiles = REQUIRED_ROOT.filter((f) => !existsSync(join(repoRoot, f)));

// 根级约定文件应为双语入口（同时含汉字与 ASCII 单词）
results.rootBilingualEntry = {};
for (const f of ['SECURITY.md', 'CONTRIBUTING.md', 'CODE_OF_CONDUCT.md']) {
  const p = join(repoRoot, f);
  if (!existsSync(p)) { results.rootBilingualEntry[f] = 'MISSING'; continue; }
  const t = readFileSync(p, 'utf8');
  results.rootBilingualEntry[f] =
    hasHan(t) && /[A-Za-z]{4,}/.test(t) && t.includes('docs/中文/') && t.includes('docs/English/')
      ? 'OK' : 'NOT_BILINGUAL_OR_MISSING_LINKS';
}

// LICENSE 必须是未改动的 Apache-2.0 英文原文
const licenseText = readFileSync(join(repoRoot, 'LICENSE'), 'utf8');
results.licenseApache20Unmodified =
  licenseText.includes('Apache License') &&
  licenseText.includes('Version 2.0, January 2004') &&
  licenseText.includes('http://www.apache.org/licenses/') &&
  licenseText.includes('END OF TERMS AND CONDITIONS') &&
  !hasHan(licenseText);

// hardware/ 目录不得为悬空空目录
results.hardwareReadmeExists = existsSync(join(repoRoot, 'hardware', 'README.md'));

results.chineseDocCount = zhFiles.length;
results.englishDocCount = enFiles.length;

const failures = [];
if (!results.chineseDirectoryExists) failures.push('docs/中文 missing');
if (!results.englishDirectoryExists) failures.push('docs/English missing');
if (results.missingChineseDocs.length) failures.push(`missing zh docs: ${results.missingChineseDocs}`);
if (results.missingEnglishDocs.length) failures.push(`missing en docs: ${results.missingEnglishDocs}`);
if (results.chineseFilenamesNotLocalized.length) failures.push(`zh filenames not localized: ${results.chineseFilenamesNotLocalized}`);
if (results.englishFilenamesWithEnSuffix.length) failures.push(`en filenames with _EN: ${results.englishFilenamesWithEnSuffix}`);
if (results.englishFilenamesWithHan.length) failures.push(`en filenames with Han: ${results.englishFilenamesWithHan}`);
if (results.repoWideEnSuffixFiles.length) failures.push(`repo-wide _EN files: ${results.repoWideEnSuffixFiles}`);
if (results.missingRootFiles.length) failures.push(`missing root files: ${results.missingRootFiles}`);
for (const [k, v] of Object.entries(results.rootBilingualEntry)) {
  if (v !== 'OK') failures.push(`root entry ${k}: ${v}`);
}
if (!results.licenseApache20Unmodified) failures.push('LICENSE is not pristine Apache-2.0 English text');
if (!results.hardwareReadmeExists) failures.push('hardware/README.md missing');

results.failures = failures;
results.pass = failures.length === 0;

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify(results, null, 2) + '\n');
} else {
  for (const [k, v] of Object.entries(results)) {
    if (k === 'failures') continue;
    console.log(`${k.padEnd(32)}: ${JSON.stringify(v)}`);
  }
  console.log(failures.length ? `FAIL:\n  - ${failures.join('\n  - ')}` : 'PASS: documentation structure OK');
}

process.exit(results.pass ? 0 : 1);

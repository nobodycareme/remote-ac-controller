#!/usr/bin/env node
// 校验仓库内所有 Markdown 文件的相对链接目标是否存在。
// 用法: node tools/check-doc-links.mjs [--json]
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs';
import { join, dirname, resolve, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SKIP_DIRS = new Set([
  '.git', 'node_modules', 'dist', 'build', '.pio', '.build', '.vite',
  'coverage', 'vendor', '.venv', '__pycache__',
]);

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(join(dir, entry.name), out);
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.md')) {
      out.push(join(dir, entry.name));
    }
  }
  return out;
}

// 只检查 git 跟踪的 Markdown：CI 的干净检出里不存在 .build/ 等生成目录，
// 本地工作树却可能有；用 git 清单让本地预演与 CI 结论完全一致。
function trackedMarkdown() {
  try {
    const out = execFileSync('git', ['-C', repoRoot, 'ls-files', '-z', '--', '*.md', '*.MD'], {
      encoding: 'utf8',
      maxBuffer: 32 * 1024 * 1024,
    });
    const files = out.split('\0').filter(Boolean).map((p) => join(repoRoot, p));
    return files.length ? files : null;
  } catch {
    return null;
  }
}

function collectFiles() {
  const tracked = trackedMarkdown();
  if (tracked) return { files: tracked, source: 'git ls-files (tracked only)' };
  return { files: walk(repoRoot), source: 'filesystem walk (git unavailable)' };
}

// 行内链接 [text](target) 与引用式定义 [id]: target
const INLINE = /\[[^\]\n]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const REFDEF = /^\s{0,3}\[[^\]]+\]:\s*(\S+)/gm;

function stripCode(md) {
  // 去掉围栏代码块与行内代码，避免误报
  return md
    .replace(/```[\s\S]*?```/g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/~~~[\s\S]*?~~~/g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/`[^`\n]*`/g, (m) => ' '.repeat(m.length));
}

function isExternal(target) {
  return /^(https?:|mailto:|tel:|ftp:|data:|#|\/\/)/i.test(target);
}

// 第三方 vendored 目录：其 README 由上游维护，不改名、不修链接，仅作提示。
// 上游 README 常引用未随发行包分发的文件（如 Unity 的 docs/、srun-c 的
// platform/md.c），这类断链不是本仓库的缺陷，因此只报告不失败。
const VENDORED_PREFIXES = [
  'firmware/agent-platformio/lib/',
  'firmware/arduino-ide/libraries/',
];
const isVendored = (rel) => VENDORED_PREFIXES.some((p) => rel.startsWith(p));

const collected = collectFiles();
const files = collected.files.slice().sort();
const broken = [];
const brokenVendored = [];
let totalLinks = 0;
let relativeLinks = 0;

for (const file of files) {
  const raw = readFileSync(file, 'utf8');
  const text = stripCode(raw);
  const targets = [];
  for (const m of text.matchAll(INLINE)) targets.push(m[1]);
  for (const m of text.matchAll(REFDEF)) targets.push(m[1]);

  for (const t of targets) {
    totalLinks++;
    if (isExternal(t)) continue;
    // 去掉锚点与查询串
    const clean = decodeURIComponent(t.split('#')[0].split('?')[0]).trim();
    if (!clean) continue;
    relativeLinks++;
    const base = clean.startsWith('/')
      ? join(repoRoot, clean.slice(1))
      : resolve(dirname(file), clean);
    if (!existsSync(base)) {
      const rel = relative(repoRoot, file).split(sep).join('/');
      const entry = {
        file: rel,
        target: t,
        resolved: relative(repoRoot, base).split(sep).join('/'),
      };
      (isVendored(rel) ? brokenVendored : broken).push(entry);
    }
  }
}

const report = {
  repoRoot,
  fileSource: collected.source,
  markdownFiles: files.length,
  totalLinks,
  relativeLinks,
  brokenCount: broken.length,
  broken,
  brokenVendoredCount: brokenVendored.length,
  brokenVendored,
};

if (process.argv.includes('--json')) {
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
} else {
  console.log(`File source                 : ${report.fileSource}`);
  console.log(`Markdown files scanned      : ${report.markdownFiles}`);
  console.log(`Links found (total)         : ${report.totalLinks}`);
  console.log(`Relative links checked      : ${report.relativeLinks}`);
  console.log(`Broken (project-owned)      : ${report.brokenCount}`);
  console.log(`Broken (vendored, ignored)  : ${report.brokenVendoredCount}`);
  for (const b of broken) {
    console.log(`  BROKEN ${b.file} -> ${b.target}  (resolved: ${b.resolved})`);
  }
  for (const b of brokenVendored) {
    console.log(`  vendored ${b.file} -> ${b.target}`);
  }
}

process.exit(broken.length === 0 ? 0 : 1);

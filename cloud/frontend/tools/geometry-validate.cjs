/**
 * 多尺寸真实渲染几何验证（规格第二十三节）。
 *
 * 原理：本地起 mock API + 静态服务器托管 dist 生产构建产物，
 * 用 Playwright Chromium 在 16 个真实视口下逐视图测量 DOM 几何：
 *   1. 全部视图无横向溢出（scrollWidth ≤ innerWidth + 1px）
 *   2. 同 Grid 行内两卡顶部/底部差 ≤ 1px（overview-grid / insight-grid，≥900px 时）
 *   3. 快捷卡等宽等高（差 ≤ 1px）
 *   4. 控制页状态 Tile 列数符合契约（<360:1 / 360–899:2 / 900–1199:3 / ≥1200:4）且等宽 ≤1px
 *
 * 输出 layout_geometry_validation.json 至证据目录。
 * 用法：node tools/geometry-validate.cjs <evidence_dir>
 */
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');

const DIST = path.join(__dirname, '..', 'dist');
const OUT_DIR = process.argv[2] || __dirname;
const PORT = 4173;
const TOL = 1; // px

// ---------- Mock API ----------
const now = Math.floor(Date.now() / 1000);
const telemetry = {
  seq: 12345, server_received_at: now - 20, temperature_c: 27.4, humidity_pct: 58.2,
  sensor_ok: 1, wifi_rssi_dbm: -52, free_heap_bytes: 31200, uptime_s: 86400 * 3 + 3600,
  wifi_reconnect_count: 1, mqtt_reconnect_count: 2, firmware_version: 'c502a879', simulated: 0,
};
const weather = {
  city: '西安', temperature_2m: 33.6, relative_humidity_2m: 41, apparent_temperature: 36.1,
  weather_code: 1, wind_speed_10m: 8.4, is_day: 1, time: new Date().toISOString(),
  stale: false, source: 'open-meteo', observed_at: (now - 300) * 1000,
};
const states = [];
for (const [mode, temps] of [['cool', [22, 24, 25, 26, 27, 28]], ['dry', [24, 26]], ['heat', [22, 24, 26, 28]]]) {
  for (const t of temps) {
    states.push({
      stateId: `hisense_${mode}_${t}c_v1`, displayName: `${mode === 'cool' ? '制冷' : mode === 'dry' ? '除湿' : '制热'} ${t}°C`,
      mode, temperature: t, fan: 'auto', swingVertical: true, swingHorizontal: false,
      powerOn: true, frameLength: 22, frameSha256: 'x'.repeat(64), enabled: true,
    });
  }
}
states.push({
  stateId: 'hisense_power_off_v1', displayName: '关机', mode: 'off', temperature: 0, fan: 'auto',
  swingVertical: false, swingHorizontal: false, powerOn: false, frameLength: 22,
  frameSha256: 'y'.repeat(64), enabled: true,
});
const recentCommands = Array.from({ length: 5 }, (_, i) => ({
  command_id: `cmd-${i}`, action: i === 0 ? 'hisense_cool_26c_v1' : 'hisense_power_off_v1',
  requested_power: 1, requested_temperature_c: 26, status: i % 2 ? 'ACK_TIMEOUT' : 'ACKNOWLEDGED',
  created_at: now - i * 3600, acknowledged_at: i % 2 ? null : now - i * 3600 + 4, failure_reason: null,
}));
const historyPoints = Array.from({ length: 48 }, (_, i) => ({
  t: (now - (48 - i) * 1800) * 1000,
  temperature_c: 26 + Math.sin(i / 5) * 2.5,
  humidity_pct: 55 + Math.cos(i / 7) * 8,
}));
const API = {
  '/api/auth/session': { authenticated: false, csrf: 'mock-csrf', ir_control: 'disabled' },
  '/api/dashboard': {
    availability: 'online', last_seen_at: now - 20, data_freshness: 'fresh',
    firmware_version: 'c502a879', mqtt_backend_connected: true, latest_telemetry: telemetry,
    recent_commands: recentCommands, weather, weather_error: null,
    ir_control: 'disabled', ir_armed: false, ir_available_codes: [],
  },
  '/api/ac/states': { states, ir_armed: false },
  '/api/telemetry/history': { range: '24h', unit: 'raw', points: historyPoints },
  '/api/events': { events: Array.from({ length: 8 }, (_, i) => ({ id: i + 1, event_type: 'device_online', device_id: 'ac-1', message: '设备上线', created_at: now - i * 7200 })) },
  '/api/weather/current': { ok: true, weather },
  '/api/ac/schedules': {
    schedules: [
      { id: 1, name: '晚间制冷', state_id: 'hisense_cool_26c_v1', time_hhmm: '21:30', days_mask: 127, one_shot: 0, enabled: 1, last_fired_minute: null, last_fired_at: now - 86400, created_by: 'owner', created_at: now - 86400 * 7, updated_at: now - 86400 },
      { id: 2, name: '清晨关机', state_id: 'hisense_power_off_v1', time_hhmm: '06:30', days_mask: 62, one_shot: 0, enabled: 1, last_fired_minute: null, last_fired_at: null, created_by: 'owner', created_at: now - 86400 * 6, updated_at: now - 86400 * 2 },
      { id: 3, name: '周末午休', state_id: 'hisense_cool_27c_v1', time_hhmm: '13:00', days_mask: 65, one_shot: 0, enabled: 0, last_fired_minute: null, last_fired_at: null, created_by: 'owner', created_at: now - 86400 * 3, updated_at: now - 86400 },
    ],
  },
  '/api/ac/temperature-rule': {
    rule: { id: 1, enabled: 1, on_threshold_c: 29, off_threshold_c: 25, on_state_id: 'hisense_cool_26c_v1', off_state_id: 'hisense_power_off_v1', min_interval_s: 1800, sensor_stale_s: 300, manual_suppress_s: 3600, last_action: 'on', last_action_at: now - 7200, last_eval_reason: 'temp_below_off_threshold', last_eval_at: now - 60 },
  },
  '/api/ac/automation/executions': {
    executions: Array.from({ length: 5 }, (_, i) => ({ id: i + 1, source: i % 2 ? 'schedule' : 'temperature_rule', rule_id: 1, state_id: 'hisense_cool_26c_v1', command_id: `cmd-${i}`, status: 'ACKNOWLEDGED', detail: null, created_at: now - i * 43200 })),
  },
};
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.webmanifest': 'application/manifest+json', '.json': 'application/json' };

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url, `http://localhost:${PORT}`);
      const p = url.pathname;
      if (p.startsWith('/api/')) {
        const key = Object.keys(API).find((k) => p === k || p.startsWith(k + '?'));
        if (key) {
          res.writeHead(200, { 'content-type': 'application/json' });
          res.end(JSON.stringify(API[key]));
        } else {
          res.writeHead(404, { 'content-type': 'application/json' });
          res.end(JSON.stringify({ errorCode: 'NOT_FOUND', message: 'mock miss: ' + p }));
        }
        return;
      }
      let file = path.join(DIST, p === '/' ? 'index.html' : p);
      if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(DIST, 'index.html');
      res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream' });
      res.end(fs.readFileSync(file));
    });
    server.listen(PORT, '127.0.0.1', () => resolve(server));
  });
}

// ---------- 视口矩阵（16） ----------
const VIEWPORTS = [
  { name: 'desktop-1728', width: 1728, height: 1117, group: 'desktop' },
  { name: 'desktop-1536', width: 1536, height: 960, group: 'desktop' },
  { name: 'desktop-1440', width: 1440, height: 900, group: 'desktop' },
  { name: 'desktop-1366', width: 1366, height: 768, group: 'desktop' },
  { name: 'desktop-1280', width: 1280, height: 800, group: 'desktop' },
  { name: 'ipad-pro129-landscape-1366', width: 1366, height: 1024, group: 'ipad' },
  { name: 'ipad-air-landscape-1180', width: 1180, height: 820, group: 'ipad' },
  { name: 'ipad-pro129-portrait-1024', width: 1024, height: 1366, group: 'ipad' },
  { name: 'ipad-landscape-1024', width: 1024, height: 768, group: 'ipad' },
  { name: 'ipad-air-portrait-820', width: 820, height: 1180, group: 'ipad' },
  { name: 'ipad-portrait-768', width: 768, height: 1024, group: 'ipad' },
  { name: 'iphone-pro-max-430', width: 430, height: 932, group: 'phone' },
  { name: 'iphone-11-414', width: 414, height: 896, group: 'phone' },
  { name: 'iphone-14-390', width: 390, height: 844, group: 'phone' },
  { name: 'iphone-se-375', width: 375, height: 667, group: 'phone' },
  { name: 'android-360', width: 360, height: 800, group: 'phone' },
];
function expectedStateCols(w) { return w < 360 ? 1 : w < 900 ? 2 : w < 1200 ? 3 : 4; }
function expectedQuickCols(w) { return w < 360 ? 1 : w < 900 ? 2 : 4; }

// ---------- 页面几何测量（浏览器内执行） ----------
const MEASURE = `(() => {
  const tol = ${TOL};
  const r = { checks: [] };
  const push = (name, pass, detail) => r.checks.push({ name, pass, detail });
  const doc = document.scrollingElement || document.documentElement;
  push('no_horizontal_overflow', doc.scrollWidth <= window.innerWidth + tol,
    'scrollWidth=' + doc.scrollWidth + ' innerWidth=' + window.innerWidth);
  const rects = (sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null || getComputedStyle(e).position === 'fixed').map(e => e.getBoundingClientRect());
  const sameRow = (a, b) => Math.abs(a.top - b.top) <= tol;
  const grid = (sel, label) => {
    const g = document.querySelector(sel);
    if (!g) return;
    const kids = [...g.children].map(e => e.getBoundingClientRect()).filter(b => b.width > 0);
    if (kids.length < 2) return;
    for (let i = 0; i < kids.length - 1; i++) for (let j = i + 1; j < kids.length; j++) {
      if (sameRow(kids[i], kids[j])) {
        push(label + '_row_top_align', Math.abs(kids[i].top - kids[j].top) <= tol, 'dTop=' + Math.abs(kids[i].top - kids[j].top).toFixed(2));
        push(label + '_row_bottom_align', Math.abs(kids[i].bottom - kids[j].bottom) <= tol, 'dBottom=' + Math.abs(kids[i].bottom - kids[j].bottom).toFixed(2));
      }
    }
  };
  grid('.overview-grid', 'overview');
  grid('.insight-grid', 'insight');
  const quick = rects('.quick-grid .quick-btn');
  if (quick.length >= 2) {
    const w = quick.map(b => b.width), h = quick.map(b => b.height);
    push('quick_equal_width', Math.max(...w) - Math.min(...w) <= tol, 'dW=' + (Math.max(...w) - Math.min(...w)).toFixed(2));
    push('quick_equal_height', Math.max(...h) - Math.min(...h) <= tol, 'dH=' + (Math.max(...h) - Math.min(...h)).toFixed(2));
    const lefts = [...new Set(quick.map(b => Math.round(b.left)))];
    r.quickCols = lefts.length;
  }
  const firstStateGrid = document.querySelector('.state-grid');
  if (firstStateGrid) {
    const tiles = [...firstStateGrid.querySelectorAll('.state-btn')].map(e => e.getBoundingClientRect()).filter(b => b.width > 0);
    if (tiles.length >= 2) {
      const w = tiles.map(b => b.width);
      push('state_tile_equal_width', Math.max(...w) - Math.min(...w) <= tol, 'dW=' + (Math.max(...w) - Math.min(...w)).toFixed(2));
    }
    r.stateCols = getComputedStyle(firstStateGrid).gridTemplateColumns.split(' ').length;
  }
  return r;
})()`;

async function navTo(page, view, width) {
  // 宽屏走顶部导航；窄屏走底部导航（data/settings 经"更多"）
  if (width >= 900) {
    const map = { home: '首页', control: '控制', schedule: '定时', automation: '自动化', data: '数据', settings: '设置' };
    await page.click(`.desktop-nav button:has-text("${map[view]}")`);
  } else {
    const map = { home: '首页', control: '控制', schedule: '定时', automation: '自动化' };
    if (map[view]) {
      await page.click(`.bottom-nav button:has-text("${map[view]}")`);
    } else {
      await page.click('.bottom-nav button:has-text("更多")');
      await page.waitForTimeout(120);
      await page.click(`.more-item:has-text("${view === 'data' ? '数据' : '设置'}")`);
    }
  }
  await page.waitForTimeout(350);
}

(async () => {
  const { chromium } = require('playwright');
  const server = await startServer();
  // 使用系统 Chrome（channel），避免依赖 ms-playwright 浏览器下载
  const browser = await chromium.launch({ channel: 'chrome' });
  const results = [];
  let totalChecks = 0, failedChecks = 0;

  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    const entry = { viewport: vp.name, width: vp.width, height: vp.height, group: vp.group, views: {}, pass: true };
    try {
      await page.goto(`http://127.0.0.1:${PORT}/`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      for (const view of ['home', 'control', 'schedule', 'automation', 'data', 'settings']) {
        if (view !== 'home') await navTo(page, view, vp.width);
        const m = await page.evaluate(MEASURE);
        // 列数契约断言
        if (view === 'home' && typeof m.quickCols === 'number') {
          m.checks.push({ name: 'quick_expected_cols', pass: m.quickCols === expectedQuickCols(vp.width), detail: `actual=${m.quickCols} expected=${expectedQuickCols(vp.width)}` });
        }
        if (view === 'control' && typeof m.stateCols === 'number') {
          m.checks.push({ name: 'state_expected_cols', pass: m.stateCols === expectedStateCols(vp.width), detail: `actual=${m.stateCols} expected=${expectedStateCols(vp.width)}` });
        }
        const fails = m.checks.filter((c) => !c.pass);
        totalChecks += m.checks.length; failedChecks += fails.length;
        if (fails.length) entry.pass = false;
        entry.views[view] = { pass: fails.length === 0, checks: m.checks };
        if (process.env.SHOTS === '1' && (view === 'home' || view === 'control')) {
          const shotDir = path.join(OUT_DIR, 'screenshots');
          if (!fs.existsSync(shotDir)) fs.mkdirSync(shotDir, { recursive: true });
          await page.screenshot({ path: path.join(shotDir, `${vp.name}_${view}.png`), fullPage: false });
        }
      }
    } catch (e) {
      entry.pass = false;
      entry.error = String(e && e.message || e).slice(0, 300);
      failedChecks += 1; totalChecks += 1;
    }
    results.push(entry);
    console.log(`${entry.pass ? 'PASS' : 'FAIL'}  ${vp.name} (${vp.width}x${vp.height})${entry.error ? ' ERROR: ' + entry.error : ''}`);
    if (!entry.pass && !entry.error) {
      for (const [v, d] of Object.entries(entry.views)) for (const c of d.checks) if (!c.pass) console.log(`   × [${v}] ${c.name}: ${c.detail}`);
    }
    await ctx.close();
  }
  await browser.close();
  server.close();

  const summary = {
    generated_at: new Date().toISOString(),
    tolerance_px: TOL,
    dist_build: fs.readdirSync(path.join(DIST, 'assets')).join(', '),
    viewports_total: VIEWPORTS.length,
    viewports_passed: results.filter((r) => r.pass).length,
    checks_total: totalChecks,
    checks_failed: failedChecks,
    overall_pass: results.every((r) => r.pass),
    results,
  };
  const out = path.join(OUT_DIR, 'layout_geometry_validation.json');
  fs.writeFileSync(out, JSON.stringify(summary, null, 2));
  console.log(`\nOVERALL: ${summary.overall_pass ? 'PASS' : 'FAIL'}  (${summary.viewports_passed}/${VIEWPORTS.length} viewports, ${failedChecks}/${totalChecks} checks failed)`);
  console.log('written: ' + out);
  process.exit(summary.overall_pass ? 0 : 1);
})();

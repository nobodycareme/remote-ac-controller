'use strict';
/**
 * 生产截图：使用真实 backend https://ac.example.com 渲染，验证部署后实际渲染效果。
 * 不修改生产文件，仅打开页面并截图，输出到证据目录。
 */
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const OUT = process.argv[2] || '.';
const VIEWPORTS = [
  { name: 'prod-desktop-1440', width: 1440, height: 900 },
  { name: 'prod-ipad-landscape', width: 1366, height: 1024 },
  { name: 'prod-ipad-portrait', width: 820, height: 1180 },
  { name: 'prod-iphone-14', width: 390, height: 844 },
];
(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const shotsDir = path.join(OUT, 'screenshots');
  fs.mkdirSync(shotsDir, { recursive: true });
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, deviceScaleFactor: 2 });
    const page = await ctx.newPage();
    await page.goto('https://ac.example.com/', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(shotsDir, `${vp.name}_home.png`), fullPage: false });
    // 切到控制页验证真实数据下的渲染
    const navBtn = vp.width >= 900
      ? `.desktop-nav button:has-text("控制")`
      : `.bottom-nav button:has-text("控制")`;
    await page.click(navBtn).catch(() => {});
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(shotsDir, `${vp.name}_control.png`), fullPage: false });
    console.log(`shot: ${vp.name}`);
    await ctx.close();
  }
  await browser.close();
})();
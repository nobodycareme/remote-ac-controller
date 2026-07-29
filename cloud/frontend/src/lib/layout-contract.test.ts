/**
 * 布局契约测试（结构层）。
 * 说明：本文件验证源码层面的栅格契约与反模式约束；
 * 真实渲染几何由多尺寸 DOM 几何验证（layout_geometry_validation.json）另行覆盖，
 * 两者共同构成视觉验收，本文件单独通过不代表视觉验收通过。
 */
import { describe, it, expect } from 'vitest';
// 注意：不能对 .css 使用 Vite ?raw 导入 —— vitest 2.x 会把 .css 请求（含 ?raw）
// 拦截为空字符串，导致断言全部落空。统一用 node:fs 读取源码文本，
// 类型由 @types/node 提供（tsconfig types 已含 "node"）。
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const app = readFileSync(join(root, 'App.vue'), 'utf-8');
const css = readFileSync(join(root, 'style.css'), 'utf-8');
const hero = readFileSync(join(root, 'components', 'ClimateHero.vue'), 'utf-8');
const weather = readFileSync(join(root, 'components', 'WeatherCard.vue'), 'utf-8');
const trend = readFileSync(join(root, 'components', 'TrendChart.vue'), 'utf-8');

/** 提取 App.vue 首页 <main>…</main> 片段 */
function homeSection(): string {
  const start = app.indexOf("currentView === 'home'");
  const end = app.indexOf('<!-- ============ 控制页');
  expect(start).toBeGreaterThan(-1);
  expect(end).toBeGreaterThan(start);
  return app.slice(start, end);
}

describe('OverviewGrid 契约', () => {
  it('OverviewGrid 同时包含 ClimateHero 与 WeatherCard（同级子项）', () => {
    const home = homeSection();
    const ov = home.slice(home.indexOf('overview-grid'), home.indexOf('</section>'));
    expect(ov).toContain('<ClimateHero');
    expect(ov).toContain('<WeatherCard');
  });

  it('ClimateHero 不再位于主 Grid 之外（overview-grid 出现在 ClimateHero 之前）', () => {
    const home = homeSection();
    expect(home.indexOf('overview-grid')).toBeLessThan(home.indexOf('<ClimateHero'));
  });

  it('WeatherCard 不再与快捷控制共用同一行（quick-section 在 overview-grid 之后且不含 WeatherCard）', () => {
    const home = homeSection();
    const qs = home.slice(home.indexOf('quick-section'), home.indexOf('insight-grid'));
    expect(qs).not.toContain('WeatherCard');
    expect(home.indexOf('overview-grid')).toBeLessThan(home.indexOf('quick-section'));
  });

  it('旧 .home-grid / .span-2 结构已移除', () => {
    expect(app).not.toContain('home-grid');
    expect(app).not.toContain('span-2');
    expect(css).not.toContain('.home-grid');
  });

  it('overview-grid 使用 stretch 等高（无 align-items:start）且子项 height:100%', () => {
    const block = css.slice(css.indexOf('.overview-grid'), css.indexOf('.quick-section'));
    expect(block).toContain('align-items: stretch');
    expect(block).toContain('height: 100%');
    expect(block).not.toContain('align-items: start');
  });
});

describe('QuickControlSection 契约', () => {
  it('快捷控制独占完整 Section（section.quick-section 包含标题与 quick-grid）', () => {
    const home = homeSection();
    const qs = home.slice(home.indexOf('quick-section'), home.indexOf('insight-grid'));
    expect(qs).toContain('section-title');
    expect(qs).toContain('quick-grid');
  });

  it('快捷卡使用统一 Grid：repeat + minmax(0, 1fr)，非固定宽度/space-between', () => {
    expect(css).toMatch(/\.quick-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    expect(css).toMatch(/\.quick-grid\s*\{\s*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/);
    const quickBtn = css.slice(css.indexOf('.quick-btn'), css.indexOf('.quick-btn.q-cool'));
    expect(quickBtn).not.toContain('space-between');
  });

  it('快捷卡触控与等高：min-height ≥ 112px 且 height:100%', () => {
    const quickBtn = css.slice(css.indexOf('.quick-btn {'), css.indexOf('.quick-btn .q-icon'));
    expect(quickBtn).toContain('min-height: 112px');
    expect(quickBtn).toContain('height: 100%');
  });
});

describe('InsightGrid 契约', () => {
  it('InsightGrid 同时包含 ActivityCard 与 TrendCard', () => {
    const home = homeSection();
    const ig = home.slice(home.indexOf('insight-grid'));
    expect(ig).toContain('activity-card');
    expect(ig).toContain('trend-card');
  });

  it('ActivityCard 使用 grid-template-rows: auto 1fr auto 结构（列表区伸缩、按钮贴底）', () => {
    expect(css).toMatch(/\.activity-card\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto/);
  });

  it('TrendCard 为 flex column，图表包装层 flex:1 + min-height', () => {
    expect(css).toMatch(/\.trend-card\s*\{[^}]*flex-direction:\s*column/);
    expect(css).toMatch(/\.trend-card\s+\.chart-flex\s*\{[^}]*flex:\s*1/);
    expect(css).toMatch(/\.trend-card\s+\.chart-flex\s*\{[^}]*min-height/);
  });
});

describe('间距责任唯一契约', () => {
  it('.card 自身不携带 margin-bottom（间距由父级 gap 负责）', () => {
    const cardBlock = css.slice(css.indexOf('.card {'), css.indexOf('.card h3'));
    expect(cardBlock).not.toMatch(/margin-bottom:\s*[1-9]/);
    expect(cardBlock).toContain('margin: 0');
  });

  it('移动端仍有明确 gap（.view 为 flex column + gap）', () => {
    const viewBlock = css.slice(css.indexOf('.view {'), css.indexOf('@keyframes view-in'));
    expect(viewBlock).toContain('flex-direction: column');
    expect(viewBlock).toMatch(/gap:\s*var\(--grid-gap\)/);
  });
});

describe('TrendChart 尺寸响应契约', () => {
  it('支持 fill 填充容器模式', () => {
    expect(trend).toContain('fill?: boolean');
    expect(trend).toContain("'chart-fill': fill");
  });

  it('使用 ResizeObserver 监听容器尺寸（而非 window resize）', () => {
    expect(trend).toContain('ResizeObserver');
    expect(trend).not.toContain("window.addEventListener('resize'");
  });

  it('卸载时解除监听、释放实例、防止重复初始化', () => {
    expect(trend).toContain('ro?.disconnect()');
    expect(trend).toContain('chart?.dispose()');
    expect(trend).toContain('chart = null');
    expect(trend).toContain('!chart');
  });
});

describe('反模式约束（禁止假修复）', () => {
  it('主要布局无负 margin', () => {
    // brand-sub 的 -2px 视觉微调不属于布局对齐修正，排除标题副行后检查
    const layoutCss = css.replace(/\.brand-sub[^}]*\}/, '');
    expect(layoutCss).not.toMatch(/margin[^:;]*:\s*-\d/);
  });

  it('主要布局卡片无 absolute 定位（仅允许固定层与装饰性小元素）', () => {
    for (const sel of ['.hero-card', '.card {', '.quick-btn', '.overview-grid', '.insight-grid']) {
      const idx = css.indexOf(sel);
      expect(idx).toBeGreaterThan(-1);
      const block = css.slice(idx, css.indexOf('}', idx));
      expect(block).not.toContain('position: absolute');
    }
  });

  it('无 transform/top/left 位置修正参与主布局（transform 仅用于居中与按压反馈）', () => {
    expect(css).not.toMatch(/\.(overview|insight|quick)-[a-z-]*\s*\{[^}]*transform/);
  });
});

describe('响应式导航契约', () => {
  it('底部导航只在窄屏显示：≥900px 断点内 display:none', () => {
    const m900 = css.slice(css.indexOf('@media (min-width: 900px)'), css.indexOf('@media (min-width: 1200px)'));
    expect(m900).toMatch(/\.bottom-nav\s*\{\s*display:\s*none/);
  });

  it('顶部导航只在宽屏显示：默认 display:none，≥900px 显示 flex', () => {
    expect(css).toMatch(/\.desktop-nav\s*\{\s*display:\s*none;\s*\}/);
    const m900 = css.slice(css.indexOf('@media (min-width: 900px)'), css.indexOf('@media (min-width: 1200px)'));
    expect(m900).toMatch(/\.desktop-nav\s*\{\s*display:\s*flex/);
  });

  it('底部导航与正文底部预留考虑安全区 env(safe-area-inset-bottom)', () => {
    expect(css).toMatch(/\.bottom-nav\s*\{[^}]*safe-area-inset-bottom/);
    expect(css).toMatch(/\.app-shell\s*\{[^}]*safe-area-inset-bottom/);
  });
});

describe('响应式栅格契约（12 列）', () => {
  it('≥900px：概览 7+5，洞察 6+6', () => {
    const m900 = css.slice(css.indexOf('@media (min-width: 900px)'), css.indexOf('@media (min-width: 1200px)'));
    expect(m900).toContain('repeat(12, minmax(0, 1fr))');
    expect(m900).toMatch(/\.ov-hero\s*\{\s*grid-column:\s*span 7/);
    expect(m900).toMatch(/\.ov-weather\s*\{\s*grid-column:\s*span 5/);
    expect(m900).toMatch(/\.activity-card\s*\{\s*grid-column:\s*span 6/);
  });

  it('≥1200px：概览 8+4，洞察 5+7', () => {
    const m1200 = css.slice(css.indexOf('@media (min-width: 1200px)'));
    expect(m1200).toMatch(/\.ov-hero\s*\{\s*grid-column:\s*span 8/);
    expect(m1200).toMatch(/\.ov-weather\s*\{\s*grid-column:\s*span 4/);
    expect(m1200).toMatch(/\.activity-card\s*\{\s*grid-column:\s*span 5/);
    expect(m1200).toMatch(/\.trend-card\s*\{\s*grid-column:\s*span 7/);
  });

  it('极窄屏（<360px）快捷卡降为单列', () => {
    expect(css).toMatch(/@media \(max-width: 359\.98px\)\s*\{\s*\.quick-grid\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  });

  it('唯一页面容器：.app-shell 使用 min(...) 宽度并 margin-inline auto', () => {
    expect(css).toMatch(/\.app-shell\s*\{[^}]*width:\s*min\(calc\(100% - var\(--shell-pad\) \* 2\), 1440px\)/);
    expect(css).toMatch(/\.app-shell\s*\{[^}]*margin-inline:\s*auto/);
  });

  it('全局 box-sizing: border-box 与 Grid 子项 min-width:0', () => {
    expect(css).toMatch(/\*::before,\s*\n?\*::after\s*\{[^}]*box-sizing:\s*border-box/);
    const ovBlock = css.slice(css.indexOf('.overview-grid > *'), css.indexOf('.quick-section'));
    expect(ovBlock).toContain('min-width: 0');
  });
});

describe('只读提示与窄屏文字契约', () => {
  it('readonly 登录链接不被拆字：inline-link 使用 nowrap + flex-shrink:0', () => {
    expect(css).toMatch(/\.inline-link\s*\{[^}]*white-space:\s*nowrap/);
    expect(css).toMatch(/\.inline-link\s*\{[^}]*flex-shrink:\s*0/);
  });

  it('readonly-note 文字区可伸缩换行（rn-text flex basis auto + min-width:0）', () => {
    expect(css).toMatch(/\.readonly-note\s+\.rn-text\s*\{[^}]*flex:\s*1 1 auto/);
    expect(css).toMatch(/\.readonly-note\s+\.rn-text\s*\{[^}]*min-width:\s*0/);
    expect(app).toContain('class="rn-text"');
  });
});

describe('Owner / Guest 双身份结构', () => {
  it('Guest 使用 readonly-note + 登录入口；Owner 分支存在控制与危险操作', () => {
    expect(app).toContain('v-if="!isTrustedOwner"');
    expect(app).toContain('danger-zone');
    expect(app).toContain('v-if="isTrustedOwner"');
  });

  it('ClimateHero 不依赖身份信息，Guest 下不会塌陷（无 isOwner/isTrustedOwner 分支）', () => {
    expect(hero).not.toContain('isOwner');
    expect(hero).not.toContain('isTrustedOwner');
  });
});

describe('主题 Token 完整性', () => {
  const tokens = [
    '--bg', '--surface-1', '--surface-2', '--surface-3',
    '--text', '--text-dim', '--text-faint',
    '--accent', '--accent-cooling', '--accent-dry', '--accent-heating',
    '--ok', '--warn', '--danger', '--border', '--border-strong',
    '--hero-grad', '--nav-bg',
  ];
  const darkBlock = css.slice(css.indexOf(':root {'), css.indexOf(":root[data-theme='light']"));
  const lightBlock = css.slice(css.indexOf(":root[data-theme='light']"), css.indexOf('/* ===== Reset'));

  it('深色主题 Token 完整', () => {
    for (const t of tokens) expect(darkBlock, `dark missing ${t}`).toContain(t + ':');
  });

  it('浅色主题 Token 完整（同名覆盖）', () => {
    for (const t of tokens) expect(lightBlock, `light missing ${t}`).toContain(t + ':');
  });

  it('数字使用 tabular-nums；支持 prefers-reduced-motion', () => {
    expect(css).toContain('font-variant-numeric: tabular-nums');
    expect(css).toContain('prefers-reduced-motion: reduce');
  });
});

describe('天气卡与气候卡同卡片体系', () => {
  it('WeatherCard 使用通用 .card 外层且为 overview 子项（ov-weather）', () => {
    expect(weather).toContain('class="card weather-card-root ov-weather"');
  });

  it('ClimateHero 为 overview 子项（ov-hero）且含主数据/指标/底部三区', () => {
    expect(hero).toContain('ov-hero');
    expect(hero).toContain('hero-body');
    expect(hero).toContain('hero-metrics');
    expect(hero).toContain('hero-foot');
  });

  it('ClimateHero 只描述"最近发送"，不声称空调当前状态', () => {
    expect(hero).toContain('最近发送');
    expect(hero).not.toContain('当前处于');
  });
});

describe('控制页状态 Tile 显式列数契约（规格第十二节）', () => {
  it('基态（手机 / iPad 竖屏）：显式 2 列，禁用 auto-fill', () => {
    expect(css).toMatch(/\.state-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    expect(css).not.toMatch(/\.state-grid\s*\{[^}]*auto-fill/);
  });

  it('极窄屏（<360px）：状态 Tile 降为单列', () => {
    const narrow = css.slice(css.indexOf('@media (max-width: 359.98px)'), css.indexOf('@media (min-width: 600px)'));
    expect(narrow).toMatch(/\.state-grid\s*\{\s*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  });

  it('≥900px（iPad 横屏 / 中桌面）：3 列', () => {
    const m900 = css.slice(css.indexOf('@media (min-width: 900px)'), css.indexOf('@media (min-width: 1200px)'));
    expect(m900).toMatch(/\.state-grid\s*\{\s*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  });

  it('≥1200px（大桌面）：4 列', () => {
    const m1200 = css.slice(css.indexOf('@media (min-width: 1200px)'));
    expect(m1200).toMatch(/\.state-grid\s*\{\s*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/);
  });

  it('状态按钮等高：min-height + height:100% + stretch', () => {
    expect(css).toMatch(/\.state-btn\s*\{[^}]*min-height:\s*96px/);
    expect(css).toMatch(/\.state-btn\s*\{[^}]*height:\s*100%/);
    expect(css).toMatch(/\.state-grid\s*\{[^}]*align-items:\s*stretch/);
  });
});

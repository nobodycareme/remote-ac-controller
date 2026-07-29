<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, onErrorCaptured } from 'vue';
import {
  fetchSession,
  login,
  logout,
  revokeTrustedDevice,
  revokeAllTrustedDevices,
  fetchDashboard,
  fetchTelemetryHistory,
  fetchEvents,
  sendIrAction,
  fetchWeatherCurrent,
  connectWS,
  fetchAcStates,
  patchAcState,
  fetchSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  fetchTemperatureRule,
  putTemperatureRule,
  fetchAutomationExecutions,
  type Dashboard,
  type ApiError,
  type SessionInfo,
  type AcStateInfo,
  type AcSchedule,
  type TemperatureRule,
  type AutomationExecution,
} from './api';
import TrendChart from './components/TrendChart.vue';
import AppIcon from './components/AppIcon.vue';
import ClimateHero from './components/ClimateHero.vue';
import WeatherCard from './components/WeatherCard.vue';
import ThermostatBar from './components/ThermostatBar.vue';
import ActivityTimeline from './components/ActivityTimeline.vue';
import EmptyState from './components/EmptyState.vue';
import {
  DAY_LABELS,
  MODE_LABELS,
  formatTimestamp,
  relativeTime,
  daysMaskText,
  buildDaysMask,
  validateScheduleForm,
  validateRuleThresholds,
  stateChipText,
  groupStatesByMode,
  computeCanFireRealIr,
  parseUserAgent,
  trustStatusText,
} from './lib/format';

declare const __APP_BUILD_ID__: string;
declare const __APP_GIT_COMMIT__: string;
declare const __APP_BUILD_TS__: string;

const BUILD_ID = typeof __APP_BUILD_ID__ !== 'undefined' ? __APP_BUILD_ID__ : 'dev';
const GIT_COMMIT = typeof __APP_GIT_COMMIT__ !== 'undefined' ? __APP_GIT_COMMIT__ : 'unknown';
const BUILD_TS = typeof __APP_BUILD_TS__ !== 'undefined' ? __APP_BUILD_TS__ : '0';
const PAGE_TITLE = '云端空调管家';
const POWER_OFF_STATE_ID = 'hisense_power_off_v1';

const fatalError = ref<{ id: string; message: string } | null>(null);
onErrorCaptured((err: any) => {
  fatalError.value = { id: BUILD_ID, message: String(err?.message || '页面渲染出错').slice(0, 160) };
  return false;
});

// ===== 视图导航（轻量状态切换，无路由库） =====
type ViewName = 'home' | 'control' | 'schedule' | 'automation' | 'data' | 'settings' | 'more';
const currentView = ref<ViewName>('home');
function go(v: ViewName) {
  currentView.value = v;
  try { window.scrollTo({ top: 0 }); } catch { /* ignore */ }
}
const NAV_ITEMS: { view: ViewName; label: string; icon: string }[] = [
  { view: 'home', label: '首页', icon: 'home' },
  { view: 'control', label: '控制', icon: 'remote' },
  { view: 'schedule', label: '定时', icon: 'schedule' },
  { view: 'automation', label: '自动化', icon: 'automation' },
];
const DESKTOP_EXTRA: { view: ViewName; label: string; icon: string }[] = [
  { view: 'data', label: '数据', icon: 'chart' },
  { view: 'settings', label: '设置', icon: 'settings' },
];

// ===== 核心数据 =====
const sessionInfo = ref<SessionInfo | null>(null);
const dashboard = ref<Dashboard | null>(null);
const history = ref<{ t: number; temperature_c: number; humidity_pct: number }[]>([]);
const historyRange = ref('1h');
const events = ref<{ id: number; event_type: string; device_id: string; message: string; created_at: number }[]>([]);
const weatherCurrent = ref<any>(null);
const weatherError = ref<string | null>(null);
const ws = ref<WebSocket | null>(null);
const theme = ref<'dark' | 'light'>('dark');
const loginPassword = ref('');
const loginBusy = ref(false);
const ownerBusy = ref(false);
const loginMessage = ref('');
const showLoginModal = ref(false);
const showFireConfirm = ref(false);
const showRevokeCurrentConfirm = ref(false);
const showRevokeAllConfirm = ref(false);

// Toast（aria-live 通知）
const toastMsg = ref('');
let toastTimer: any = null;
function toast(msg: string) {
  toastMsg.value = msg;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastMsg.value = ''; }, 6000);
}

// ===== 全状态控制 / 定时 / 温控 =====
const acStates = ref<AcStateInfo[]>([]);
const pendingState = ref<AcStateInfo | null>(null);
const showStateManager = ref(false);
const controlModeFilter = ref<'all' | 'off' | 'cool' | 'dry' | 'heat'>('all');
const schedules = ref<AcSchedule[]>([]);
const tempRule = ref<TemperatureRule | null>(null);
const executions = ref<AutomationExecution[]>([]);
const showScheduleForm = ref(false);
const editingScheduleId = ref<number | null>(null);
const scheduleForm = ref({ name: '', state_id: '', time_hhmm: '07:30', days: [true, true, true, true, true, true, true], one_shot: false });
const scheduleBusy = ref(false);
const scheduleMessage = ref('');
const showRuleEditor = ref(false);
const ruleForm = ref({ enabled: false, on_threshold_c: 28, off_threshold_c: 26, on_state_id: '', off_state_id: '' });
const ruleBusy = ref(false);
const ruleMessage = ref('');

const MODE_ICON_NAMES: Record<string, string> = { cool: 'snow', dry: 'drop', heat: 'sun', off: 'power' };

const isOwner = computed(() => sessionInfo.value?.role === 'owner');
const stateGroups = computed(() => {
  const filtered = controlModeFilter.value === 'all'
    ? acStates.value
    : acStates.value.filter((s) => s.mode === controlModeFilter.value);
  return groupStatesByMode(filtered).map((g) => ({ ...g, icon: MODE_ICON_NAMES[g.mode] ?? 'info' }));
});
const enabledStates = computed(() => acStates.value.filter((s) => s.enabled));
const availableModeFilters = computed(() => {
  const modes = new Set(acStates.value.map((s) => s.mode));
  const out: { key: 'all' | 'off' | 'cool' | 'dry' | 'heat'; label: string; icon: string }[] = [{ key: 'all', label: '全部', icon: 'control' }];
  for (const m of ['cool', 'dry', 'heat', 'off'] as const) {
    if (modes.has(m)) out.push({ key: m, label: MODE_LABELS[m] ?? m, icon: MODE_ICON_NAMES[m] });
  }
  return out;
});

// 快捷控制（首页 ≤4）：关机 + 常用制冷 + 强冷 + 除湿，缺位则顺位补齐
const quickControls = computed(() => {
  const enabled = enabledStates.value;
  const picks: AcStateInfo[] = [];
  const off = enabled.find((s) => s.mode === 'off');
  const coolCommon = enabled.find((s) => s.mode === 'cool' && s.temperature === 26 && s.fan === 'auto') ?? enabled.find((s) => s.mode === 'cool' && s.fan === 'auto') ?? enabled.find((s) => s.mode === 'cool');
  const coolTurbo = enabled.find((s) => s.mode === 'cool' && s.fan === 'turbo');
  const dry = enabled.find((s) => s.mode === 'dry');
  for (const c of [coolCommon, coolTurbo, dry, off]) if (c && !picks.includes(c)) picks.push(c);
  for (const s of enabled) {
    if (picks.length >= 4) break;
    if (!picks.includes(s)) picks.push(s);
  }
  return picks.slice(0, 4);
});

function stateName(id: string): string {
  return acStates.value.find((s) => s.stateId === id)?.displayName ?? id;
}

function quickSub(s: AcStateInfo): string {
  if (s.mode === 'off') return '发送关机指令';
  return stateChipText(s) || (MODE_LABELS[s.mode] ?? s.mode);
}

function quickName(s: AcStateInfo): string {
  if (s.mode === 'off') return '关机';
  return `${MODE_LABELS[s.mode] ?? s.mode} ${s.temperature}℃`;
}

async function loadAcStates() {
  try {
    const r = await fetchAcStates();
    acStates.value = r.states;
  } catch { /* ignore */ }
}

async function loadSchedules() {
  try {
    schedules.value = (await fetchSchedules()).schedules;
  } catch { /* ignore */ }
}

async function loadTempRule() {
  try {
    tempRule.value = (await fetchTemperatureRule()).rule;
  } catch { /* ignore */ }
}

async function loadExecutions() {
  try {
    executions.value = (await fetchAutomationExecutions(30)).executions;
  } catch { /* ignore */ }
}

function requestFire(s: AcStateInfo) {
  if (!isTrustedOwner.value) {
    openLoginModal();
    return;
  }
  if (!s.enabled || !canFireRealIr.value) return;
  pendingState.value = s;
  showFireConfirm.value = true;
}

async function toggleStateEnabled(s: AcStateInfo) {
  if (!isOwner.value) return;
  try {
    const r = await patchAcState(s.stateId, !s.enabled);
    const idx = acStates.value.findIndex((x) => x.stateId === s.stateId);
    if (idx >= 0) acStates.value[idx] = r.state;
  } catch (e: any) {
    toast(`状态开关保存失败：${e?.message || ''}`);
  }
}

// ===== 定时任务表单（新建 / 编辑复用同一抽屉） =====
function daysFromMask(mask: number): boolean[] {
  return Array.from({ length: 7 }, (_, i) => !!(mask & (1 << i)));
}

function openScheduleForm(edit?: AcSchedule) {
  scheduleMessage.value = '';
  if (edit) {
    editingScheduleId.value = edit.id;
    scheduleForm.value = {
      name: edit.name || '',
      state_id: edit.state_id,
      time_hhmm: edit.time_hhmm,
      days: daysFromMask(edit.days_mask),
      one_shot: !!edit.one_shot,
    };
  } else {
    editingScheduleId.value = null;
    scheduleForm.value = {
      name: '',
      state_id: enabledStates.value.find((s) => s.powerOn)?.stateId ?? '',
      time_hhmm: '07:30',
      days: [true, true, true, true, true, true, true],
      one_shot: false,
    };
  }
  showScheduleForm.value = true;
}

async function submitSchedule() {
  const f = scheduleForm.value;
  const err = validateScheduleForm(f);
  if (err) {
    scheduleMessage.value = err;
    return;
  }
  const mask = buildDaysMask(f.days);
  scheduleBusy.value = true;
  scheduleMessage.value = '';
  try {
    if (editingScheduleId.value !== null) {
      await updateSchedule(editingScheduleId.value, {
        name: f.name || `${f.time_hhmm} ${stateName(f.state_id)}`,
        state_id: f.state_id,
        time_hhmm: f.time_hhmm,
        days_mask: mask,
        one_shot: f.one_shot,
      });
    } else {
      await createSchedule({
        name: f.name || `${f.time_hhmm} ${stateName(f.state_id)}`,
        state_id: f.state_id,
        time_hhmm: f.time_hhmm,
        days_mask: mask,
        one_shot: f.one_shot,
      });
    }
    showScheduleForm.value = false;
    editingScheduleId.value = null;
    await loadSchedules();
  } catch (e: any) {
    scheduleMessage.value = `保存失败：${e?.message || ''}`;
  } finally {
    scheduleBusy.value = false;
  }
}

async function toggleSchedule(s: AcSchedule) {
  if (!isOwner.value) return;
  try {
    await updateSchedule(s.id, { enabled: !s.enabled });
    await loadSchedules();
  } catch (e: any) {
    toast(`更新失败：${e?.message || ''}`);
  }
}

async function removeSchedule(s: AcSchedule) {
  if (!isOwner.value) return;
  try {
    await deleteSchedule(s.id);
    await loadSchedules();
  } catch (e: any) {
    toast(`删除失败：${e?.message || ''}`);
  }
}

// ===== 温控规则 =====
function openRuleEditor() {
  const r = tempRule.value;
  ruleForm.value = {
    enabled: !!r?.enabled,
    on_threshold_c: r?.on_threshold_c ?? 28,
    off_threshold_c: r?.off_threshold_c ?? 26,
    on_state_id: r?.on_state_id ?? '',
    off_state_id: r?.off_state_id ?? POWER_OFF_STATE_ID,
  };
  ruleMessage.value = '';
  showRuleEditor.value = true;
}

async function submitRule() {
  const f = ruleForm.value;
  const err = validateRuleThresholds(f.on_threshold_c, f.off_threshold_c);
  if (err) {
    ruleMessage.value = err;
    return;
  }
  ruleBusy.value = true;
  ruleMessage.value = '';
  try {
    const r = await putTemperatureRule({
      enabled: f.enabled,
      on_threshold_c: f.on_threshold_c,
      off_threshold_c: f.off_threshold_c,
      on_state_id: f.on_state_id || undefined,
      off_state_id: f.off_state_id || undefined,
    });
    tempRule.value = r.rule;
    showRuleEditor.value = false;
  } catch (e: any) {
    ruleMessage.value = `保存失败：${e?.message || ''}`;
  } finally {
    ruleBusy.value = false;
  }
}

// ===== 派生状态 =====
const availabilityClass = computed(() => {
  const a = dashboard.value?.availability;
  if (a === 'online') return 'pill online';
  if (a === 'offline') return 'pill offline';
  return 'pill warn';
});
const availabilityText = computed(() => {
  const a = dashboard.value?.availability;
  if (a === 'online') return '在线';
  if (a === 'offline') return '离线';
  return '未知';
});

const isTrustedOwner = computed(() => sessionInfo.value?.role === 'owner' && sessionInfo.value?.trusted === true);
const canFireRealIr = computed(() =>
  computeCanFireRealIr({
    irArmed: !!dashboard.value?.ir_armed,
    online: !!(dashboard.value as any)?.online,
    mqttConnected: !!dashboard.value?.mqtt_backend_connected,
    trustedOwner: isTrustedOwner.value,
    busy: ownerBusy.value,
  })
);

const settings = computed(() => (dashboard.value as any)?.settings ?? null);
const samplePeriodS = computed(() => (settings.value?.device_sample_interval_ms ?? 0) / 1000);
const publishPeriodS = computed(() => (settings.value?.device_publish_interval_ms ?? 0) / 1000);
const staleThresholdS = computed(() => (settings.value?.stale_threshold_ms ?? 0) / 1000);
const offlineThresholdS = computed(() => (settings.value?.offline_threshold_ms ?? 0) / 1000);
const tempNow = computed(() => dashboard.value?.latest_telemetry?.temperature_c ?? null);
const humNow = computed(() => dashboard.value?.latest_telemetry?.humidity_pct ?? null);
const rssiNow = computed(() => dashboard.value?.latest_telemetry?.wifi_rssi_dbm ?? null);
const fwVer = computed(() => dashboard.value?.firmware_version ?? '--');
const mqttBack = computed(() => dashboard.value?.mqtt_backend_connected ?? false);
// 受信任设备：原始 UA 仅用于折叠诊断区；主卡片显示中文解析结果。
// trusted_label 为空时回退到本机 navigator.userAgent（当前设备场景等价）。
const trustedRawLabel = computed(() => sessionInfo.value?.trusted_label || '');
const trustedDevice = computed(() => parseUserAgent(trustedRawLabel.value || navigator.userAgent));
const trustedExpiresAt = computed(() => sessionInfo.value?.trusted_expires_at ?? null);
const trustedPersistent = computed(() => sessionInfo.value?.trusted_persistent === true);
// 显示规则（规格第十节）：revoked→已撤销 / persistent→长期有效 / expiresAt→有效至 / 否则→状态未知。
const trustedStatusText = computed(() =>
  trustStatusText({ persistent: trustedPersistent.value, expiresAt: trustedExpiresAt.value }),
);
const trustedStatusHint = computed(() => (trustedPersistent.value ? '可随时移除' : '到期后需重新登录'));
const ownerControlState = computed(() => '已开放');
const lastSeenTs = computed(() => dashboard.value?.last_seen_at ?? null);

// 首页 Hero「最近发送」：最近一条指令映射到状态目录（只描述发送行为，不声称空调实际状态）
const lastSentText = computed(() => {
  const cmd = dashboard.value?.recent_commands?.[0];
  if (!cmd) return null;
  const st = acStates.value.find((s) => s.stateId === cmd.action);
  if (!st) return null;
  return st.displayName;
});

// 首页 Hero 底部提示：温控自动化 / 定时任务概况（人类可读）
const heroHint = computed(() => {
  const bits: string[] = [];
  if (tempRule.value?.enabled) bits.push(`温控自动化运行中（≥${tempRule.value.on_threshold_c}℃ 自动开机）`);
  const activeSchedules = schedules.value.filter((s) => s.enabled).length;
  if (activeSchedules > 0) bits.push(`${activeSchedules} 个定时任务已启用`);
  if (!bits.length) bits.push('暂无启用的自动化');
  return bits.join(' · ');
});

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value);
  try { localStorage.setItem('rac-theme', theme.value); } catch { /* ignore */ }
  window.dispatchEvent(new Event('resize'));
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  applyTheme();
}

// ===== 数据加载 =====
async function loadSession() {
  try {
    sessionInfo.value = await fetchSession();
  } catch {
    sessionInfo.value = null;
  }
}

async function loadDashboard() {
  try {
    dashboard.value = await fetchDashboard();
  } catch { /* ignore */ }
}

async function loadWeather() {
  try {
    weatherCurrent.value = await fetchWeatherCurrent();
    weatherError.value = null;
  } catch (e: any) {
    weatherError.value = e?.message || '天气暂不可用';
  }
}

async function loadHistory() {
  try {
    const r = await fetchTelemetryHistory(historyRange.value);
    history.value = r.points;
  } catch { /* ignore */ }
}

async function loadEvents() {
  try {
    const r = await fetchEvents();
    events.value = r.events;
  } catch { /* ignore */ }
}

async function refreshAll() {
  await loadSession();
  await loadDashboard();
  await loadWeather();
  await loadHistory();
  await loadEvents();
  await loadAcStates();
  await loadSchedules();
  await loadTempRule();
  await loadExecutions();
}

function onWs(type: string, payload: any) {
  if (type === 'telemetry' && payload) {
    if (dashboard.value) {
      dashboard.value.latest_telemetry = payload as any;
      dashboard.value.availability = 'online';
      dashboard.value.last_seen_at = payload.server_received_at;
      dashboard.value.data_freshness = 'fresh';
    }
    loadHistory();
  } else if (type === 'availability' && payload) {
    if (dashboard.value) dashboard.value.availability = payload.status;
  } else if (type === 'weather_update' && payload) {
    weatherCurrent.value = payload;
    weatherError.value = null;
  } else if (type === 'ack') {
    loadDashboard();
    loadEvents();
  }
}

// ===== 登录 / 信任 / 发射 =====
async function openLoginModal() {
  loginMessage.value = '';
  loginPassword.value = '';
  showLoginModal.value = true;
}

async function submitLogin() {
  loginBusy.value = true;
  loginMessage.value = '';
  try {
    sessionInfo.value = await login(loginPassword.value);
    showLoginModal.value = false;
    loginPassword.value = '';
    await loadDashboard();
    toast('已为当前设备建立受信任会话。');
  } catch (e: any) {
    const ae = e as ApiError;
    loginMessage.value = `绑定失败：${ae?.errorCode ? '[' + ae.errorCode + '] ' : ''}${ae?.message || e?.message || ''}`;
  } finally {
    loginBusy.value = false;
  }
}

async function confirmFireIr() {
  const target = pendingState.value;
  if (!target || !canFireRealIr.value) {
    toast('当前不可发送红外指令。');
    showFireConfirm.value = false;
    return;
  }
  showFireConfirm.value = false;
  ownerBusy.value = true;
  try {
    const r = await sendIrAction(target.stateId);
    toast(`已发送「${target.displayName}」红外指令（${String(r.command_id).slice(0, 8)}），请留意空调动作。`);
  } catch (e: any) {
    const ae = e as ApiError;
    toast(`指令未发送：${ae?.errorCode ? '[' + ae.errorCode + '] ' : ''}${ae?.message || e?.message || ''}`);
  } finally {
    ownerBusy.value = false;
    pendingState.value = null;
    await loadDashboard();
    await loadEvents();
  }
}

async function confirmRevokeCurrent() {
  showRevokeCurrentConfirm.value = false;
  ownerBusy.value = true;
  try {
    await revokeTrustedDevice();
    await refreshAll();
    toast('当前设备信任已移除。');
  } catch (e: any) {
    toast(`撤销失败：${e?.message || ''}`);
  } finally {
    ownerBusy.value = false;
  }
}

async function confirmRevokeAll() {
  showRevokeAllConfirm.value = false;
  ownerBusy.value = true;
  try {
    const r = await revokeAllTrustedDevices();
    await refreshAll();
    toast(`已撤销 ${r.revoked} 个受信任会话。`);
  } catch (e: any) {
    toast(`撤销失败：${e?.message || ''}`);
  } finally {
    ownerBusy.value = false;
  }
}

async function doLogout() {
  ownerBusy.value = true;
  try {
    await logout();
    await refreshAll();
    toast('已退出登录。');
  } catch (e: any) {
    toast(`退出失败：${e?.message || ''}`);
  } finally {
    ownerBusy.value = false;
  }
}

let pollTimer: any = null;
let weatherTimer: any = null;
onMounted(async () => {
  document.title = PAGE_TITLE;
  try {
    const saved = localStorage.getItem('rac-theme') as 'dark' | 'light' | null;
    if (saved) theme.value = saved;
  } catch { /* ignore */ }
  applyTheme();
  await refreshAll();
  ws.value = connectWS(onWs);
  pollTimer = setInterval(() => {
    loadDashboard();
    loadSession();
    loadEvents();
    loadExecutions();
  }, 10000);
  weatherTimer = setInterval(loadWeather, 60000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (weatherTimer) clearInterval(weatherTimer);
  if (toastTimer) clearTimeout(toastTimer);
  ws.value?.close();
});
</script>

<template>
  <div>
    <div v-if="fatalError" class="error-fallback">
      <div class="error-card">
        <h2>页面渲染出错</h2>
        <p class="error-msg">{{ fatalError.message }}</p>
        <p class="error-meta">
          Error id: {{ fatalError.id }}<br />
          Build: {{ BUILD_ID }} | Commit: {{ GIT_COMMIT.slice(0, 12) }}
        </p>
      </div>
    </div>

    <div v-else class="app-shell">
      <!-- ===== 顶栏 ===== -->
      <header class="topbar">
        <div class="brand">
          <span class="brand-logo"><AppIcon name="snow" :size="22" /></span>
          <div>
            <div class="brand-name">云端空调管家</div>
            <div class="brand-sub">卧室 · 海信空调</div>
          </div>
        </div>
        <nav class="desktop-nav" aria-label="主导航">
          <button
            v-for="n in [...NAV_ITEMS, ...DESKTOP_EXTRA]"
            :key="n.view"
            :class="{ active: currentView === n.view }"
            :aria-current="currentView === n.view ? 'page' : undefined"
            @click="go(n.view)"
          >
            <AppIcon :name="n.icon" :size="16" />{{ n.label }}
          </button>
        </nav>
        <div class="topbar-actions">
          <span v-if="isTrustedOwner" class="session-chip"><AppIcon name="shield" :size="13" />受信任</span>
          <button v-else class="mini-link" style="margin-left: 0" @click="openLoginModal">登录</button>
          <button class="icon-btn" :aria-label="theme === 'dark' ? '切换为浅色主题' : '切换为深色主题'" @click="toggleTheme">
            <AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="18" />
          </button>
        </div>
      </header>

      <!-- ============ 首页 ============ -->
      <main v-if="currentView === 'home'" class="view" aria-label="首页">
        <!-- 环境概览：气候卡与天气卡同级、同 Grid、等高 -->
        <section class="overview-grid" aria-label="环境概览">
          <ClimateHero
            :temperature="tempNow"
            :humidity="humNow"
            :availability="dashboard?.availability"
            :last-seen-at="lastSeenTs"
            :rssi="rssiNow"
            :last-sent="lastSentText"
          >
            <template #foot>{{ heroHint }}</template>
          </ClimateHero>
          <WeatherCard :weather="weatherCurrent" :error="weatherError" />
        </section>

        <!-- 快捷控制：独占整行 Section -->
        <section class="quick-section" aria-label="快捷控制">
          <div class="section-title"><AppIcon name="remote" :size="18" />快捷控制</div>
          <div v-if="!isTrustedOwner" class="readonly-note">
            <span class="rn-icon"><AppIcon name="lock" :size="16" /></span>
            <span class="rn-text">当前为只读模式，空调控制仅对受信任的 Owner 设备开放。</span>
            <a class="inline-link" @click="openLoginModal">去登录</a>
          </div>
          <div class="quick-grid" v-if="quickControls.length">
            <button
              v-for="s in quickControls"
              :key="s.stateId"
              class="quick-btn"
              :class="'q-' + s.mode"
              :disabled="isTrustedOwner && (!canFireRealIr || ownerBusy)"
              :aria-label="'发送' + s.displayName + '红外指令'"
              @click="requestFire(s)"
            >
              <span class="q-icon"><AppIcon :name="MODE_ICON_NAMES[s.mode] ?? 'info'" :size="18" /></span>
              <span class="q-name">{{ quickName(s) }}</span>
              <span class="q-sub">{{ quickSub(s) }}</span>
            </button>
          </div>
          <div v-else class="sub">状态目录加载中…</div>
        </section>

        <!-- 洞察：活动卡与趋势卡同 Grid、等高 -->
        <section class="insight-grid" aria-label="活动与趋势">
          <div class="card activity-card">
            <h3><span class="card-title-icon"><AppIcon name="timeline" :size="16" /></span>最近活动</h3>
            <div class="activity-scroll">
              <ActivityTimeline :executions="executions" :state-name="stateName" :limit="4" />
            </div>
            <button class="ghost activity-foot" style="width: 100%" @click="go('data')">查看全部活动与趋势</button>
          </div>

          <div class="card trend-card">
            <h3><span class="card-title-icon"><AppIcon name="chart" :size="16" /></span>温湿度趋势（近 1 小时）</h3>
            <div class="chart-flex">
              <TrendChart :points="history" fill />
            </div>
          </div>
        </section>
      </main>

      <!-- ============ 控制页 ============ -->
      <main v-else-if="currentView === 'control'" class="view" aria-label="空调控制">
        <div class="section-title">
          <AppIcon name="remote" :size="18" />空调控制
          <span v-if="isTrustedOwner" class="panel-chip ok">{{ ownerControlState }}</span>
          <span v-else class="panel-chip">只读</span>
          <button v-if="isOwner" class="mini-link" @click="showStateManager = !showStateManager">{{ showStateManager ? '完成' : '管理' }}</button>
        </div>

        <div v-if="!isTrustedOwner" class="readonly-note">
          <span class="rn-icon"><AppIcon name="lock" :size="16" /></span>
          <span class="rn-text">只读模式：可查看全部状态，发送指令需要 Owner 在受信任设备上操作。</span>
          <a class="inline-link" @click="openLoginModal">去登录</a>
        </div>
        <div v-else-if="!canFireRealIr" class="readonly-note">
          <span class="rn-icon"><AppIcon name="warning" :size="16" /></span>
          <span class="rn-text">
            当前不可发送：<template v-if="!dashboard?.online">设备离线。</template>
            <template v-else-if="!mqttBack">云端与设备的通道未连接。</template>
            <template v-else>请稍候。</template>
          </span>
        </div>

        <div class="segmented" role="tablist" aria-label="按模式筛选">
          <button
            v-for="f in availableModeFilters"
            :key="f.key"
            role="tab"
            :aria-selected="controlModeFilter === f.key"
            :class="{ active: controlModeFilter === f.key }"
            @click="controlModeFilter = f.key"
          >
            <AppIcon :name="f.icon" :size="15" />{{ f.label }}
          </button>
        </div>

        <div v-for="g in stateGroups" :key="g.mode" class="mode-group">
          <div class="mode-title" :class="'m-' + g.mode"><AppIcon :name="g.icon" :size="15" />{{ g.label }}</div>
          <div class="state-grid">
            <button
              v-for="s in g.states"
              :key="s.stateId"
              class="state-btn"
              :class="{ 'state-off': s.mode === 'off', 'state-disabled': !s.enabled, ['tile-' + s.mode]: true }"
              :disabled="!s.enabled || (isTrustedOwner && (!canFireRealIr || ownerBusy))"
              :aria-label="'发送' + s.displayName + '红外指令'"
              @click="requestFire(s)"
            >
              <span class="state-mode-icon"><AppIcon :name="MODE_ICON_NAMES[s.mode] ?? 'info'" :size="16" /></span>
              <span class="state-temp" v-if="s.temperature > 0">{{ s.temperature }}<small>℃</small></span>
              <span class="state-temp" v-else>关机</span>
              <span class="state-sub">{{ stateChipText(s) || (s.mode === 'off' ? '发送关机指令' : '') }}</span>
              <span v-if="showStateManager && isOwner" class="state-switch" role="switch" :aria-checked="s.enabled" @click.stop="toggleStateEnabled(s)">
                {{ s.enabled ? '已启用' : '已停用' }}
              </span>
            </button>
          </div>
        </div>
      </main>

      <!-- ============ 定时页 ============ -->
      <main v-else-if="currentView === 'schedule'" class="view" aria-label="定时任务">
        <div class="section-title">
          <AppIcon name="schedule" :size="18" />定时任务
          <button v-if="isOwner" class="mini-link" @click="openScheduleForm()"><AppIcon name="plus" :size="13" /> 新增</button>
        </div>

        <div class="card">
          <EmptyState
            v-if="schedules.length === 0"
            icon="schedule"
            title="还没有定时任务"
            :desc="isOwner ? '例如：工作日早上 7:30 自动制冷，晚上 23:00 自动关机。' : '设备主人尚未设置定时任务。'"
            :action-text="isOwner ? '创建第一个定时任务' : undefined"
            @action="openScheduleForm()"
          />
          <template v-else>
            <div v-for="s in schedules" :key="s.id" class="schedule-row" :class="{ 'row-disabled': !s.enabled }">
              <div class="schedule-main" @click="isOwner ? openScheduleForm(s) : undefined">
                <div class="schedule-line1">
                  <span class="schedule-time">{{ s.time_hhmm }}</span>
                  <span class="schedule-name">{{ stateName(s.state_id) }}</span>
                </div>
                <span class="schedule-days">
                  {{ daysMaskText(s.days_mask) }}{{ s.one_shot ? ' · 只执行一次' : '' }}
                  <template v-if="s.last_fired_at"> · 上次执行 {{ relativeTime(s.last_fired_at) }}</template>
                </span>
              </div>
              <div class="schedule-actions" v-if="isOwner">
                <button class="mini-toggle" :class="{ on: !!s.enabled }" :aria-label="(s.enabled ? '停用' : '启用') + '定时任务 ' + s.time_hhmm" @click="toggleSchedule(s)">{{ s.enabled ? '开' : '关' }}</button>
                <button class="mini-del" :aria-label="'删除定时任务 ' + s.time_hhmm" @click="removeSchedule(s)"><AppIcon name="trash" :size="14" /></button>
              </div>
              <div class="schedule-actions" v-else>
                <span class="sub">{{ s.enabled ? '已启用' : '已停用' }}</span>
              </div>
            </div>
          </template>
        </div>
        <p class="faint" style="line-height: 1.6">定时到点后由云端向设备发送红外指令；若设备离线则该次不执行并记录原因。</p>
      </main>

      <!-- ============ 自动化页 ============ -->
      <main v-else-if="currentView === 'automation'" class="view" aria-label="温度自动化">
        <div class="section-title">
          <AppIcon name="automation" :size="18" />温度自动化
          <span class="panel-chip" :class="tempRule?.enabled ? 'ok' : ''">{{ tempRule?.enabled ? '运行中' : '已停用' }}</span>
          <button v-if="isOwner" class="mini-link" @click="openRuleEditor">设置</button>
        </div>

        <div class="card" v-if="tempRule">
          <div class="rule-summary">
            <div class="rule-line">
              室温 ≥ <strong>{{ tempRule.on_threshold_c }}℃</strong> 自动开机（{{ stateName(tempRule.on_state_id) }}）；
              ≤ <strong>{{ tempRule.off_threshold_c }}℃</strong> 自动关机。
            </div>
          </div>
          <ThermostatBar
            :on-threshold="tempRule.on_threshold_c"
            :off-threshold="tempRule.off_threshold_c"
            :current-temp="tempNow"
          />
          <div class="sub" style="margin-top: 12px; line-height: 1.7">
            安全机制：两次自动动作至少间隔 {{ Math.round(tempRule.min_interval_s / 60) }} 分钟；手动操作后 {{ Math.round(tempRule.manual_suppress_s / 60) }} 分钟内自动化暂停；室温取最近采样中位数并需连续确认。
            <template v-if="tempRule.last_action">
              <br />上次自动动作：{{ tempRule.last_action === 'on' ? '开机' : '关机' }}（{{ formatTimestamp(tempRule.last_action_at) }}）。
            </template>
          </div>
        </div>
        <div class="card" v-else><div class="sub">规则加载中…</div></div>

        <div class="card">
          <h3><span class="card-title-icon"><AppIcon name="timeline" :size="16" /></span>自动化执行记录</h3>
          <ActivityTimeline :executions="executions" :state-name="stateName" :limit="10" show-absolute />
        </div>
      </main>

      <!-- ============ 数据页 ============ -->
      <main v-else-if="currentView === 'data'" class="view" aria-label="数据">
        <div class="section-title"><AppIcon name="chart" :size="18" />数据</div>
        <div class="card">
          <h3><span class="card-title-icon"><AppIcon name="chart" :size="16" /></span>温湿度趋势</h3>
          <div class="range-tabs" role="tablist" aria-label="时间范围">
            <button v-for="r in ['1h', '6h', '24h', '7d']" :key="r" role="tab" :aria-selected="historyRange === r" :class="{ active: historyRange === r }" @click=";(historyRange = r), loadHistory()">{{ r }}</button>
          </div>
          <div class="chart-area">
            <TrendChart :points="history" fill />
          </div>
        </div>
        <div class="card">
          <h3><span class="card-title-icon"><AppIcon name="timeline" :size="16" /></span>全部自动化活动</h3>
          <ActivityTimeline :executions="executions" :state-name="stateName" :limit="30" show-absolute />
        </div>
      </main>

      <!-- ============ 更多页（移动端入口） ============ -->
      <main v-else-if="currentView === 'more'" class="view" aria-label="更多">
        <div class="section-title"><AppIcon name="info" :size="18" />更多</div>
        <div class="more-list">
          <button class="more-item" @click="go('data')">
            <span class="mi-icon"><AppIcon name="chart" :size="20" /></span>数据与趋势
            <span class="mi-chev"><AppIcon name="chevron" :size="16" /></span>
          </button>
          <button class="more-item" @click="go('settings')">
            <span class="mi-icon"><AppIcon name="settings" :size="20" /></span>设置与诊断
            <span class="mi-chev"><AppIcon name="chevron" :size="16" /></span>
          </button>
          <button class="more-item" @click="toggleTheme">
            <span class="mi-icon"><AppIcon :name="theme === 'dark' ? 'sun' : 'moon'" :size="20" /></span>
            切换为{{ theme === 'dark' ? '浅色' : '深色' }}主题
          </button>
        </div>
      </main>

      <!-- ============ 设置 / 诊断页 ============ -->
      <main v-else class="view" aria-label="设置">
        <div class="section-title"><AppIcon name="settings" :size="18" />设置与诊断</div>
        <div class="settings-grid">
          <div class="card">
            <h3><span class="card-title-icon"><AppIcon name="device" :size="16" /></span>设备</h3>
            <div class="kv-grid">
              <div><span>设备状态</span><strong :class="dashboard?.availability === 'online' ? 'gate-ok' : 'gate-bad'">{{ availabilityText }}</strong></div>
              <div><span>最后上报</span><strong>{{ relativeTime(lastSeenTs) }}</strong></div>
              <div><span>固件版本</span><strong>{{ fwVer }}</strong></div>
              <div><span>Wi-Fi 信号</span><strong>{{ rssiNow !== null ? rssiNow + ' dBm' : '--' }}</strong></div>
              <div><span>云端通道</span><strong :class="mqttBack ? 'gate-ok' : 'gate-bad'">{{ mqttBack ? '已连接' : '未连接' }}</strong></div>
              <div><span>红外控制</span><strong class="gate-ok">已开启</strong></div>
            </div>
            <div class="sub" style="margin-top: 10px" v-if="settings">
              采样 {{ samplePeriodS }}s · 上传 {{ publishPeriodS }}s · 陈旧阈值 {{ staleThresholdS }}s · 离线阈值 {{ offlineThresholdS }}s
            </div>
          </div>

          <div class="card" v-if="isTrustedOwner">
            <h3><span class="card-title-icon"><AppIcon name="shield" :size="16" /></span>受信任设备</h3>
            <!-- 主卡只显示中文解析结果，完整 UA 仅在下方折叠诊断区（规格第七/九节） -->
            <div class="kv-grid trust-grid">
              <div>
                <span>这台设备</span>
                <strong class="trust-device-name">{{ trustedDevice.device }}</strong>
                <em class="kv-sub">{{ trustedDevice.browser }}</em>
              </div>
              <div>
                <span>信任状态</span>
                <strong class="gate-ok">{{ trustedStatusText }}</strong>
                <em class="kv-sub">{{ trustedStatusHint }}</em>
              </div>
              <div>
                <span>控制权限</span>
                <strong :class="dashboard?.ir_armed ? 'gate-ok' : 'gate-bad'">{{ ownerControlState }}</strong>
                <em class="kv-sub">可以控制空调</em>
              </div>
              <div>
                <span>可用控制</span>
                <strong>{{ enabledStates.length }} 种空调状态</strong>
                <em class="kv-sub">制冷 · 制热 · 除湿 · 电源</em>
              </div>
            </div>
            <details class="diag ua-diag" v-if="trustedRawLabel">
              <summary>诊断信息（原始浏览器标识）</summary>
              <code class="ua-raw">{{ trustedRawLabel }}</code>
            </details>
          </div>

          <div class="card" v-else>
            <h3><span class="card-title-icon"><AppIcon name="lock" :size="16" /></span>访问权限</h3>
            <p class="sub" style="line-height: 1.6">当前为只读访客模式。登录后本设备可被标记为受信任，用于发送空调控制指令。</p>
            <button style="width: 100%" @click="openLoginModal">登录</button>
          </div>

          <div class="card grid-full" v-if="isOwner">
            <details class="diag">
              <summary>诊断信息（原始事件与回执）</summary>
              <div class="sub" style="margin: 8px 0">构建 {{ BUILD_ID }} · 提交 {{ GIT_COMMIT.slice(0, 12) }}</div>
              <div v-if="events.length === 0" class="sub">暂无事件</div>
              <div v-for="e in events.slice(0, 12)" :key="e.id" class="event">
                <span class="t">{{ new Date(e.created_at).toLocaleTimeString() }}</span> | {{ e.event_type }} | {{ e.message }}
              </div>
            </details>
          </div>

          <div class="card danger-zone grid-full" v-if="isTrustedOwner">
            <h3><span class="card-title-icon"><AppIcon name="warning" :size="16" /></span>危险操作</h3>
            <p class="sub" style="margin: 0 0 12px; line-height: 1.6">以下操作会立即影响设备的控制权限，请谨慎使用。</p>
            <div class="btn-row">
              <button class="ghost" :disabled="ownerBusy" @click="showRevokeCurrentConfirm = true">移除本机信任</button>
              <button class="ghost" :disabled="ownerBusy" @click="showRevokeAllConfirm = true">移除全部信任</button>
              <button class="danger" :disabled="ownerBusy" @click="doLogout">退出登录</button>
            </div>
          </div>
          <div class="build-note grid-full">云端空调管家 · 构建 {{ BUILD_ID }} · 提交 {{ GIT_COMMIT.slice(0, 12) }} · {{ BUILD_TS }}</div>
        </div>
      </main>

      <!-- ===== 移动端底部导航 ===== -->
      <nav class="bottom-nav" aria-label="底部导航">
        <button
          v-for="n in NAV_ITEMS"
          :key="n.view"
          :class="{ active: currentView === n.view }"
          :aria-current="currentView === n.view ? 'page' : undefined"
          @click="go(n.view)"
        >
          <AppIcon :name="n.icon" :size="21" />{{ n.label }}
        </button>
        <button :class="{ active: currentView === 'more' || currentView === 'data' || currentView === 'settings' }" @click="go('more')">
          <AppIcon name="info" :size="21" />更多
        </button>
      </nav>

      <!-- ===== Toast（aria-live 状态通知） ===== -->
      <div class="toast-region" aria-live="polite" role="status">
        <div v-if="toastMsg" class="toast">{{ toastMsg }}</div>
      </div>

      <!-- ===== 登录 ===== -->
      <div v-if="showLoginModal" class="modal-mask drawer-mask" @click.self="showLoginModal = false">
        <div class="modal login-modal" role="dialog" aria-modal="true" aria-label="登录">
          <h2>登录</h2>
          <form @submit.prevent="submitLogin">
            <label for="owner-pass">Owner 密码</label>
            <input id="owner-pass" v-model="loginPassword" type="password" autocomplete="current-password" />
            <div class="sub login-help">验证后这台设备会保持受信任状态，可用于发送空调控制指令。</div>
            <div v-if="loginMessage" class="err" aria-live="polite">{{ loginMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="loginBusy" @click="showLoginModal = false">取消</button>
              <button type="submit" :disabled="loginBusy || !loginPassword">登录并信任本机</button>
            </div>
          </form>
        </div>
      </div>

      <!-- ===== 发射确认 ===== -->
      <div v-if="showFireConfirm" class="modal-mask drawer-mask" @click.self="showFireConfirm = false; pendingState = null">
        <div class="modal ir-confirm-modal" role="dialog" aria-modal="true" aria-label="确认发送红外指令">
          <h2>确认发送</h2>
          <p class="confirm-lead">即将发送：<strong>{{ pendingState?.displayName }}</strong></p>
          <div class="confirm-copy">
            <ol>
              <li>系统会向设备发送一次真实红外指令，不会自动重试。</li>
              <li>红外为单向发送，网页无法确认空调是否实际响应，请留意空调动作。</li>
            </ol>
          </div>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showFireConfirm = false; pendingState = null">取消</button>
            <button class="ir" :disabled="ownerBusy" @click="confirmFireIr">确认发送</button>
          </div>
        </div>
      </div>

      <!-- ===== 定时任务编辑（抽屉） ===== -->
      <div v-if="showScheduleForm" class="modal-mask drawer-mask" @click.self="showScheduleForm = false">
        <div class="modal ir-confirm-modal" role="dialog" aria-modal="true" :aria-label="editingScheduleId !== null ? '编辑定时任务' : '新增定时任务'">
          <h2>{{ editingScheduleId !== null ? '编辑定时任务' : '新增定时任务' }}</h2>
          <form @submit.prevent="submitSchedule">
            <label for="sch-time">执行时间（24 小时制）</label>
            <input id="sch-time" v-model="scheduleForm.time_hhmm" type="time" required />
            <label for="sch-state">执行动作</label>
            <select id="sch-state" v-model="scheduleForm.state_id" class="modal-select" required>
              <option v-for="s in enabledStates" :key="s.stateId" :value="s.stateId">{{ s.displayName }}</option>
            </select>
            <label>重复星期</label>
            <div class="day-picker" role="group" aria-label="选择重复的星期">
              <button
                v-for="(d, i) in DAY_LABELS"
                :key="i"
                type="button"
                class="day-btn"
                :class="{ on: scheduleForm.days[i] }"
                :aria-pressed="scheduleForm.days[i]"
                @click="scheduleForm.days[i] = !scheduleForm.days[i]"
              >{{ d }}</button>
            </div>
            <label class="check-line">
              <input v-model="scheduleForm.one_shot" type="checkbox" /> 只执行一次（触发后自动停用）
            </label>
            <label for="sch-name">备注（可选）</label>
            <input id="sch-name" v-model="scheduleForm.name" type="text" placeholder="如：早晨预冷" />
            <div v-if="scheduleMessage" class="err" aria-live="polite">{{ scheduleMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="scheduleBusy" @click="showScheduleForm = false">取消</button>
              <button class="ok" type="submit" :disabled="scheduleBusy">保存</button>
            </div>
          </form>
        </div>
      </div>

      <!-- ===== 温控设置（抽屉） ===== -->
      <div v-if="showRuleEditor" class="modal-mask drawer-mask" @click.self="showRuleEditor = false">
        <div class="modal ir-confirm-modal" role="dialog" aria-modal="true" aria-label="温度自动化设置">
          <h2>温度自动化设置</h2>
          <form @submit.prevent="submitRule">
            <label class="check-line">
              <input v-model="ruleForm.enabled" type="checkbox" /> 启用温度自动化
            </label>
            <label for="rule-on">开机阈值（室温 ≥ 此值自动开机）：{{ ruleForm.on_threshold_c }}℃</label>
            <input id="rule-on" v-model.number="ruleForm.on_threshold_c" type="range" min="24" max="34" step="0.5" aria-valuetext="开机阈值" />
            <label for="rule-off">关机阈值（室温 ≤ 此值自动关机）：{{ ruleForm.off_threshold_c }}℃</label>
            <input id="rule-off" v-model.number="ruleForm.off_threshold_c" type="range" min="20" max="30" step="0.5" aria-valuetext="关机阈值" />
            <ThermostatBar :on-threshold="ruleForm.on_threshold_c" :off-threshold="ruleForm.off_threshold_c" :current-temp="tempNow" />
            <label for="rule-state">自动开机执行的动作</label>
            <select id="rule-state" v-model="ruleForm.on_state_id" class="modal-select">
              <option v-for="s in enabledStates.filter((x) => x.powerOn)" :key="s.stateId" :value="s.stateId">{{ s.displayName }}</option>
            </select>
            <div class="sub" style="margin-top: 8px; line-height: 1.6">
              安全机制：两次自动动作至少间隔 10 分钟；你手动操作后 30 分钟内自动化暂停；室温取最近 3 次采样中位数并需连续两轮确认。
            </div>
            <div v-if="ruleMessage" class="err" aria-live="polite">{{ ruleMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="ruleBusy" @click="showRuleEditor = false">取消</button>
              <button class="ok" type="submit" :disabled="ruleBusy">保存</button>
            </div>
          </form>
        </div>
      </div>

      <!-- ===== 撤销信任确认 ===== -->
      <div v-if="showRevokeCurrentConfirm" class="modal-mask" @click.self="showRevokeCurrentConfirm = false">
        <div class="modal ir-confirm-modal" role="dialog" aria-modal="true" aria-label="撤销本机信任">
          <h2>撤销本机信任</h2>
          <p class="confirm-lead">这台设备会回到只读状态，不能再发送空调控制指令。</p>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeCurrentConfirm = false">取消</button>
            <button class="danger" :disabled="ownerBusy" @click="confirmRevokeCurrent">确认撤销</button>
          </div>
        </div>
      </div>

      <div v-if="showRevokeAllConfirm" class="modal-mask" @click.self="showRevokeAllConfirm = false">
        <div class="modal ir-confirm-modal" role="dialog" aria-modal="true" aria-label="撤销全部信任">
          <h2>撤销全部信任</h2>
          <p class="confirm-lead">所有受信任设备都会失效，需要重新登录才能控制空调。</p>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeAllConfirm = false">取消</button>
            <button class="danger" :disabled="ownerBusy" @click="confirmRevokeAll">确认撤销</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

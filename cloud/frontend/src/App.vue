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
const ownerMessage = ref('');
const showLoginModal = ref(false);
const showFireConfirm = ref(false);
const showRevokeCurrentConfirm = ref(false);
const showRevokeAllConfirm = ref(false);

// ===== v0.5.0 全状态控制 / 定时 / 温控 =====
const acStates = ref<AcStateInfo[]>([]);
const pendingState = ref<AcStateInfo | null>(null); // 待确认发射的状态
const showStateManager = ref(false);
const schedules = ref<AcSchedule[]>([]);
const tempRule = ref<TemperatureRule | null>(null);
const executions = ref<AutomationExecution[]>([]);
const showScheduleForm = ref(false);
const scheduleForm = ref({ name: '', state_id: '', time_hhmm: '07:30', days: [true, true, true, true, true, true, true], one_shot: false });
const scheduleBusy = ref(false);
const scheduleMessage = ref('');
const showRuleEditor = ref(false);
const ruleForm = ref({ enabled: false, on_threshold_c: 28, off_threshold_c: 26, on_state_id: '', off_state_id: '' });
const ruleBusy = ref(false);
const ruleMessage = ref('');

const DAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];
const MODE_LABELS: Record<string, string> = { cool: '制冷', dry: '除湿', heat: '制热', off: '电源' };
const MODE_ICONS: Record<string, string> = { cool: '❄️', dry: '💧', heat: '☀️', off: '⏻' };
const FAN_LABELS: Record<string, string> = { auto: '自动风', turbo: '超强风', quiet: '静音风' };

const isOwner = computed(() => sessionInfo.value?.role === 'owner');
const stateGroups = computed(() => {
  const order = ['off', 'cool', 'dry', 'heat'];
  const groups: { mode: string; label: string; icon: string; states: AcStateInfo[] }[] = [];
  for (const m of order) {
    const list = acStates.value.filter((s) => s.mode === m);
    if (list.length) groups.push({ mode: m, label: MODE_LABELS[m] ?? m, icon: MODE_ICONS[m] ?? '', states: list });
  }
  return groups;
});
const enabledStates = computed(() => acStates.value.filter((s) => s.enabled));

function stateName(id: string): string {
  return acStates.value.find((s) => s.stateId === id)?.displayName ?? id;
}

function stateChip(s: AcStateInfo): string {
  const parts: string[] = [];
  if (s.fan) parts.push(FAN_LABELS[s.fan] ?? s.fan);
  if (s.swingVertical && s.swingHorizontal) parts.push('双向扫风');
  else if (s.swingVertical) parts.push('上下扫风');
  else if (s.swingHorizontal) parts.push('左右扫风');
  return parts.join(' · ');
}

function daysMaskText(mask: number): string {
  if (mask === 127) return '每天';
  if (mask === 31) return '工作日';
  if (mask === 96) return '周末';
  const out: string[] = [];
  for (let i = 0; i < 7; i++) if (mask & (1 << i)) out.push('周' + DAY_LABELS[i]);
  return out.join(' ');
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
    executions.value = (await fetchAutomationExecutions(20)).executions;
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
    ownerMessage.value = `状态开关失败：${e?.message || ''}`;
  }
}

function openScheduleForm() {
  scheduleMessage.value = '';
  scheduleForm.value = {
    name: '',
    state_id: enabledStates.value.find((s) => s.powerOn)?.stateId ?? '',
    time_hhmm: '07:30',
    days: [true, true, true, true, true, true, true],
    one_shot: false,
  };
  showScheduleForm.value = true;
}

async function submitSchedule() {
  const f = scheduleForm.value;
  let mask = 0;
  f.days.forEach((d, i) => { if (d) mask |= 1 << i; });
  if (!f.state_id || !mask || !/^([01]\d|2[0-3]):[0-5]\d$/.test(f.time_hhmm)) {
    scheduleMessage.value = '请完整填写时间（HH:MM）、状态与星期。';
    return;
  }
  scheduleBusy.value = true;
  scheduleMessage.value = '';
  try {
    await createSchedule({
      name: f.name || `${f.time_hhmm} ${stateName(f.state_id)}`,
      state_id: f.state_id,
      time_hhmm: f.time_hhmm,
      days_mask: mask,
      one_shot: f.one_shot,
    });
    showScheduleForm.value = false;
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
    scheduleMessage.value = `更新失败：${e?.message || ''}`;
  }
}

async function removeSchedule(s: AcSchedule) {
  if (!isOwner.value) return;
  try {
    await deleteSchedule(s.id);
    await loadSchedules();
  } catch (e: any) {
    scheduleMessage.value = `删除失败：${e?.message || ''}`;
  }
}

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
  if (!(f.on_threshold_c > f.off_threshold_c)) {
    ruleMessage.value = '开启阈值必须高于关闭阈值（滞回区间）。';
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
  !!dashboard.value?.ir_armed &&
  !!dashboard.value?.online &&
  !!dashboard.value?.mqtt_backend_connected &&
  isTrustedOwner.value &&
  !ownerBusy.value
);

const settings = computed(() => (dashboard.value as any)?.settings ?? null);
const samplePeriodS = computed(() => (settings.value?.device_sample_interval_ms ?? 0) / 1000);
const publishPeriodS = computed(() => (settings.value?.device_publish_interval_ms ?? 0) / 1000);
const staleThresholdS = computed(() => (settings.value?.stale_threshold_ms ?? 0) / 1000);
const offlineThresholdS = computed(() => (settings.value?.offline_threshold_ms ?? 0) / 1000);
const tempNow = computed(() => dashboard.value?.latest_telemetry?.temperature_c ?? null);
const humNow = computed(() => dashboard.value?.latest_telemetry?.humidity_pct ?? null);
const fwVer = computed(() => dashboard.value?.firmware_version ?? '--');
const mqttBack = computed(() => dashboard.value?.mqtt_backend_connected ?? false);
const trustedLabel = computed(() => sessionInfo.value?.trusted_label || '当前设备');
const trustedExpiresAt = computed(() => sessionInfo.value?.trusted_expires_at ?? null);
const ownerControlState = computed(() => dashboard.value?.ir_armed ? '可发射' : '只读');
const lastSeen = computed(() => {
  const t = dashboard.value?.last_seen_at;
  if (!t) return '--';
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
});

function formatTimestamp(ts: number | string | null | undefined): string {
  if (ts === null || ts === undefined || ts === '') return '--';
  const n = typeof ts === 'string' ? Number(ts) : ts;
  if (!Number.isFinite(n) || n <= 0) return '--';
  const d = new Date(n);
  if (Number.isNaN(d.getTime())) return '--';
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function weatherText(code: number): string {
  const m: Record<number, string> = {
    0: '晴', 1: '大致晴朗', 2: '局部多云', 3: '阴', 45: '雾', 48: '雾凇',
    51: '小雨', 53: '小雨', 55: '中雨', 61: '小雨', 63: '中雨', 65: '大雨',
    71: '小雪', 73: '中雪', 75: '大雪', 80: '阵雨', 95: '雷阵雨',
  };
  return m[code] ?? '未知';
}

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value);
  try { localStorage.setItem('rac-theme', theme.value); } catch { /* ignore */ }
  window.dispatchEvent(new Event('resize'));
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  applyTheme();
}

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
  } catch {
    /* ignore */
  }
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
  } catch {
    /* ignore */
  }
}

async function loadEvents() {
  try {
    const r = await fetchEvents();
    events.value = r.events;
  } catch {
    /* ignore */
  }
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
    loginMessage.value = '已为当前手机建立受信任会话。';
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
    ownerMessage.value = '当前不可发射。';
    showFireConfirm.value = false;
    return;
  }
  showFireConfirm.value = false;
  ownerBusy.value = true;
  ownerMessage.value = '';
  try {
    const r = await sendIrAction(target.stateId);
    ownerMessage.value = `已下发「${target.displayName}」命令 ${String(r.command_id).slice(0, 8)}，等待设备回执。`;
  } catch (e: any) {
    const ae = e as ApiError;
    ownerMessage.value = `未发射：${ae?.errorCode ? '[' + ae.errorCode + '] ' : ''}${ae?.message || e?.message || ''}`;
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
  ownerMessage.value = '';
  try {
    await revokeTrustedDevice();
    await refreshAll();
    ownerMessage.value = '当前设备信任已移除。';
  } catch (e: any) {
    ownerMessage.value = `撤销失败：${e?.message || ''}`;
  } finally {
    ownerBusy.value = false;
  }
}

async function confirmRevokeAll() {
  showRevokeAllConfirm.value = false;
  ownerBusy.value = true;
  ownerMessage.value = '';
  try {
    const r = await revokeAllTrustedDevices();
    await refreshAll();
    ownerMessage.value = `已撤销 ${r.revoked} 个受信任会话。`;
  } catch (e: any) {
    ownerMessage.value = `撤销失败：${e?.message || ''}`;
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
  ws.value?.close();
});
</script>

<template>
  <div>
    <div v-if="fatalError" class="error-fallback">
      <div class="error-card">
        <h2>Page render error</h2>
        <p class="error-msg">{{ fatalError.message }}</p>
        <p class="error-meta">
          Error id: {{ fatalError.id }}<br />
          Build: {{ BUILD_ID }} | Commit: {{ GIT_COMMIT.slice(0, 12) }}
        </p>
      </div>
    </div>

    <div v-else>
      <div class="topbar">
        <div class="title">云端空调管家</div>
        <div class="topbar-actions">
          <span v-if="isTrustedOwner" class="session-chip">受信任设备</span>
          <button v-if="!isTrustedOwner" class="icon-btn" @click="openLoginModal">绑定当前手机</button>
          <button class="icon-btn" @click="toggleTheme">{{ theme === 'dark' ? 'Light' : 'Dark' }}</button>
        </div>
      </div>

      <div class="card">
        <div class="row">
          <span :class="availabilityClass">{{ availabilityText }}</span>
          <span class="sub">最后活动：{{ lastSeen }}</span>
          <span class="sub">后端 MQTT：{{ mqttBack ? 'ON' : 'OFF' }}</span>
        </div>
        <div class="row" style="margin-top: 8px">
          <span class="sub">固件：{{ fwVer }}</span>
          <span class="sub">构建：{{ BUILD_ID }}</span>
        </div>
      </div>

      <div class="dashboard-grid">
        <div class="card">
          <h3>室内状态</h3>
          <div class="grid2">
            <div>
              <div class="sub">温度</div>
              <div class="big">{{ tempNow !== null ? tempNow.toFixed(1) : '--' }}<span style="font-size: 18px">℃</span></div>
            </div>
            <div>
              <div class="sub">湿度</div>
              <div class="big">{{ humNow !== null ? humNow.toFixed(0) : '--' }}<span style="font-size: 18px">%</span></div>
            </div>
          </div>
          <div class="sub" style="margin-top: 8px">RSSI {{ dashboard?.latest_telemetry?.wifi_rssi_dbm ?? '--' }} dBm</div>
        </div>

        <div class="card" v-if="weatherCurrent?.current">
          <h3>室外天气</h3>
          <div class="row">
            <div>
              <div class="big">{{ weatherCurrent.current.temperatureC.toFixed(1) }}<span style="font-size: 18px">℃</span></div>
              <div class="sub">{{ weatherText(weatherCurrent.current.weatherCode) }}</div>
            </div>
            <div style="text-align: right">
              <div class="sub">湿度 {{ weatherCurrent.current.relativeHumidity }}%</div>
              <div class="sub">风速 {{ weatherCurrent.current.windSpeed }} km/h</div>
              <div class="sub">观测 {{ formatTimestamp(weatherCurrent.observedAt) }}</div>
            </div>
          </div>
        </div>

        <div class="card" v-else-if="weatherError">
          <h3>室外天气</h3>
          <div class="sub">{{ weatherError }}</div>
        </div>

        <div class="card card-full">
          <h3>
            空调控制面板
            <span v-if="isTrustedOwner" class="panel-chip ok">受信任 · {{ ownerControlState }}</span>
            <span v-else class="panel-chip">只读模式</span>
            <button v-if="isOwner" class="mini-link" @click="showStateManager = !showStateManager">{{ showStateManager ? '完成' : '管理' }}</button>
          </h3>

          <div v-if="!isTrustedOwner" class="badge-ir">当前为只读模式，真实红外只对受信任手机开放。<a class="inline-link" @click="openLoginModal">绑定当前手机</a></div>

          <div v-for="g in stateGroups" :key="g.mode" class="mode-group">
            <div class="mode-title">{{ g.icon }} {{ g.label }}</div>
            <div class="state-grid">
              <button
                v-for="s in g.states"
                :key="s.stateId"
                class="state-btn"
                :class="{ 'state-off': s.mode === 'off', 'state-disabled': !s.enabled }"
                :disabled="!s.enabled || (isTrustedOwner && (!canFireRealIr || ownerBusy))"
                @click="requestFire(s)"
              >
                <span class="state-temp" v-if="s.temperature > 0">{{ s.temperature }}<small>℃</small></span>
                <span class="state-temp" v-else>关机</span>
                <span class="state-sub">{{ stateChip(s) || (s.mode === 'off' ? '一键关闭' : '') }}</span>
                <span v-if="showStateManager && isOwner" class="state-switch" @click.stop="toggleStateEnabled(s)">
                  {{ s.enabled ? '已启用' : '已停用' }}
                </span>
              </button>
            </div>
          </div>

          <div v-if="isTrustedOwner" class="owner-grid" style="margin-top: 14px">
            <div><span>当前设备</span><strong>{{ trustedLabel }}</strong></div>
            <div><span>信任到期</span><strong>{{ formatTimestamp(trustedExpiresAt) }}</strong></div>
            <div><span>控制状态</span><strong :class="dashboard?.ir_armed ? 'gate-ok' : 'gate-bad'">{{ ownerControlState }}</strong></div>
            <div><span>可用状态</span><strong>{{ enabledStates.length }} / {{ acStates.length }}</strong></div>
          </div>
          <div class="btn-row owner-actions" v-if="isTrustedOwner">
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeCurrentConfirm = true">移除本机信任</button>
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeAllConfirm = true">移除全部信任</button>
          </div>
          <div v-if="ownerMessage" class="sub owner-message">{{ ownerMessage }}</div>
        </div>

        <div class="card card-full">
          <h3>
            定时任务
            <button v-if="isOwner" class="mini-link" @click="openScheduleForm">+ 新增</button>
          </h3>
          <div v-if="schedules.length === 0" class="sub">暂无定时任务{{ isOwner ? '，点击右上角新增。' : '。' }}</div>
          <div v-for="s in schedules" :key="s.id" class="schedule-row" :class="{ 'row-disabled': !s.enabled }">
            <div class="schedule-main">
              <span class="schedule-time">{{ s.time_hhmm }}</span>
              <span class="schedule-name">{{ stateName(s.state_id) }}</span>
              <span class="schedule-days">{{ daysMaskText(s.days_mask) }}{{ s.one_shot ? ' · 单次' : '' }}</span>
            </div>
            <div class="schedule-actions" v-if="isOwner">
              <button class="mini-toggle" :class="{ on: !!s.enabled }" @click="toggleSchedule(s)">{{ s.enabled ? '开' : '关' }}</button>
              <button class="mini-del" @click="removeSchedule(s)">删除</button>
            </div>
            <div class="schedule-actions" v-else>
              <span class="sub">{{ s.enabled ? '启用' : '停用' }}</span>
            </div>
          </div>
          <div v-if="scheduleMessage" class="err">{{ scheduleMessage }}</div>
        </div>

        <div class="card card-full">
          <h3>
            温度自动化
            <span class="panel-chip" :class="tempRule?.enabled ? 'ok' : ''">{{ tempRule?.enabled ? '运行中' : '已停用' }}</span>
            <button v-if="isOwner" class="mini-link" @click="openRuleEditor">设置</button>
          </h3>
          <div v-if="tempRule" class="rule-summary">
            <div class="rule-line">
              室温 ≥ <strong>{{ tempRule.on_threshold_c }}℃</strong> 自动开机（{{ stateName(tempRule.on_state_id) }}）；
              ≤ <strong>{{ tempRule.off_threshold_c }}℃</strong> 自动关机。
            </div>
            <div class="sub" style="margin-top: 6px">
              最短间隔 {{ Math.round(tempRule.min_interval_s / 60) }} 分钟 · 手动操作后暂停 {{ Math.round(tempRule.manual_suppress_s / 60) }} 分钟
              <template v-if="tempRule.last_action">· 上次动作 {{ tempRule.last_action === 'on' ? '开机' : '关机' }} {{ formatTimestamp(tempRule.last_action_at) }}</template>
            </div>
          </div>
          <div v-else class="sub">规则加载中…</div>
        </div>

        <div class="card card-full" v-if="executions.length > 0">
          <h3>自动化记录</h3>
          <div v-for="e in executions.slice(0, 8)" :key="e.id" class="event">
            <span class="t">{{ formatTimestamp(e.created_at) }}</span>
            | {{ e.source === 'schedule' ? '定时' : '温控' }}
            | {{ stateName(e.state_id) }}
            | <span :class="e.status === 'dispatched' ? 'gate-ok' : 'gate-bad'">{{ e.status }}</span>
            <template v-if="e.detail"> | {{ e.detail }}</template>
          </div>
        </div>

        <div class="card" v-if="settings">
          <h3>运行参数</h3>
          <div class="sub">采样 {{ samplePeriodS }}s | 上传 {{ publishPeriodS }}s</div>
          <div class="sub">陈旧阈值 {{ staleThresholdS }}s | 离线阈值 {{ offlineThresholdS }}s</div>
        </div>
      </div>

      <div class="card">
        <h3>温湿度趋势</h3>
        <div class="btn-row" style="margin-bottom: 10px">
          <button class="ghost" v-for="r in ['1h', '6h', '24h', '7d']" :key="r" :style="historyRange === r ? 'border-color: var(--accent); color: var(--accent)' : ''" @click=";(historyRange = r), loadHistory()">{{ r }}</button>
        </div>
        <TrendChart :points="history" />
      </div>

      <div class="card">
        <h3>事件 / 回执</h3>
        <div v-if="events.length === 0" class="sub">暂无事件</div>
        <div v-for="e in events.slice(0, 12)" :key="e.id" class="event">
          <span class="t">{{ new Date(e.created_at).toLocaleTimeString() }}</span> | {{ e.event_type }} | {{ e.message }}
        </div>
      </div>

      <div class="footer-build">Build {{ BUILD_ID }} | Commit {{ GIT_COMMIT.slice(0, 12) }} | {{ BUILD_TS }}</div>

      <div v-if="showLoginModal" class="modal-mask" @click.self="showLoginModal = false">
        <div class="modal login-modal">
          <h2>绑定当前手机</h2>
          <form @submit.prevent="submitLogin">
            <label>Owner 密码</label>
            <input v-model="loginPassword" type="password" autocomplete="current-password" />
            <div class="sub login-help">验证后这台设备会保持受信任状态。</div>
            <div v-if="loginMessage" class="err">{{ loginMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="loginBusy" @click="showLoginModal = false">取消</button>
              <button class="ir" type="submit" :disabled="loginBusy || !loginPassword">绑定并信任</button>
            </div>
          </form>
        </div>
      </div>

      <div v-if="showFireConfirm" class="modal-mask" @click.self="showFireConfirm = false; pendingState = null">
        <div class="modal ir-confirm-modal">
          <h2>确认发射</h2>
          <p class="confirm-lead">即将发射：<strong>{{ pendingState?.displayName }}</strong></p>
          <div class="confirm-copy">
            <ol>
              <li>确认红外头正对空调接收窗。</li>
              <li>本次会发射一次真实红外，系统不会自动重试。</li>
            </ol>
          </div>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showFireConfirm = false; pendingState = null">取消</button>
            <button class="ir" :disabled="ownerBusy" @click="confirmFireIr">确认发射</button>
          </div>
        </div>
      </div>

      <div v-if="showScheduleForm" class="modal-mask" @click.self="showScheduleForm = false">
        <div class="modal ir-confirm-modal">
          <h2>新增定时任务</h2>
          <form @submit.prevent="submitSchedule">
            <label>执行时间（每天 24 小时制）</label>
            <input v-model="scheduleForm.time_hhmm" type="time" required />
            <label>执行状态</label>
            <select v-model="scheduleForm.state_id" class="modal-select" required>
              <option v-for="s in enabledStates" :key="s.stateId" :value="s.stateId">{{ s.displayName }}</option>
            </select>
            <label>重复星期</label>
            <div class="day-picker">
              <button
                v-for="(d, i) in DAY_LABELS"
                :key="i"
                type="button"
                class="day-btn"
                :class="{ on: scheduleForm.days[i] }"
                @click="scheduleForm.days[i] = !scheduleForm.days[i]"
              >{{ d }}</button>
            </div>
            <label class="check-line">
              <input v-model="scheduleForm.one_shot" type="checkbox" style="width: auto" /> 只执行一次（触发后自动停用）
            </label>
            <label>备注（可选）</label>
            <input v-model="scheduleForm.name" type="text" placeholder="如：早晨预冷" />
            <div v-if="scheduleMessage" class="err">{{ scheduleMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="scheduleBusy" @click="showScheduleForm = false">取消</button>
              <button class="ok" type="submit" :disabled="scheduleBusy">保存</button>
            </div>
          </form>
        </div>
      </div>

      <div v-if="showRuleEditor" class="modal-mask" @click.self="showRuleEditor = false">
        <div class="modal ir-confirm-modal">
          <h2>温度自动化设置</h2>
          <form @submit.prevent="submitRule">
            <label class="check-line">
              <input v-model="ruleForm.enabled" type="checkbox" style="width: auto" /> 启用温度自动化
            </label>
            <label>开机阈值（室温 ≥ 此值自动开机）：{{ ruleForm.on_threshold_c }}℃</label>
            <input v-model.number="ruleForm.on_threshold_c" type="range" min="24" max="34" step="0.5" />
            <label>关机阈值（室温 ≤ 此值自动关机）：{{ ruleForm.off_threshold_c }}℃</label>
            <input v-model.number="ruleForm.off_threshold_c" type="range" min="20" max="30" step="0.5" />
            <label>自动开机状态</label>
            <select v-model="ruleForm.on_state_id" class="modal-select">
              <option v-for="s in enabledStates.filter((x) => x.powerOn)" :key="s.stateId" :value="s.stateId">{{ s.displayName }}</option>
            </select>
            <div class="sub" style="margin-top: 8px; line-height: 1.6">
              安全机制：两次自动动作至少间隔 10 分钟；你手动操作后 30 分钟内自动化暂停；温度取最近 3 次采样中位数并需连续两轮确认。
            </div>
            <div v-if="ruleMessage" class="err">{{ ruleMessage }}</div>
            <div class="btn-row confirm-actions" style="margin-top: 14px">
              <button class="ghost" type="button" :disabled="ruleBusy" @click="showRuleEditor = false">取消</button>
              <button class="ok" type="submit" :disabled="ruleBusy">保存</button>
            </div>
          </form>
        </div>
      </div>

      <div v-if="showRevokeCurrentConfirm" class="modal-mask" @click.self="showRevokeCurrentConfirm = false">
        <div class="modal ir-confirm-modal">
          <h2>撤销本机信任</h2>
          <p class="confirm-lead">这台手机会回到只读状态。</p>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeCurrentConfirm = false">取消</button>
            <button class="ir" :disabled="ownerBusy" @click="confirmRevokeCurrent">确认撤销</button>
          </div>
        </div>
      </div>

      <div v-if="showRevokeAllConfirm" class="modal-mask" @click.self="showRevokeAllConfirm = false">
        <div class="modal ir-confirm-modal">
          <h2>撤销全部信任</h2>
          <p class="confirm-lead">所有受信任设备都会失效。</p>
          <div class="btn-row confirm-actions">
            <button class="ghost" :disabled="ownerBusy" @click="showRevokeAllConfirm = false">取消</button>
            <button class="ir" :disabled="ownerBusy" @click="confirmRevokeAll">确认撤销</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

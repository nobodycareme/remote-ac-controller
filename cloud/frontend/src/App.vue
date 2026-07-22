<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, onErrorCaptured } from 'vue';
import {
  fetchSession,
  logout as apiLogout,
  fetchDashboard,
  fetchTelemetryHistory,
  fetchEvents,
  sendCommand,
  sendIrAction,
  fetchWeatherCurrent,
  connectWS,
  login,
  type SessionInfo,
  type Dashboard,
  type CommandRow,
  type ApiError,
} from './api';
import TrendChart from './components/TrendChart.vue';

// Build identity (injected by Vite define at build time). Non-sensitive — used
// only to confirm which release the browser actually loaded, and shown on the
// visible error page so failures are diagnosable without leaking secrets.
declare const __APP_BUILD_ID__: string;
declare const __APP_GIT_COMMIT__: string;
declare const __APP_BUILD_TS__: string;
const BUILD_ID = typeof __APP_BUILD_ID__ !== 'undefined' ? __APP_BUILD_ID__ : 'dev';
const GIT_COMMIT = typeof __APP_GIT_COMMIT__ !== 'undefined' ? __APP_GIT_COMMIT__ : 'unknown';
const BUILD_TS = typeof __APP_BUILD_TS__ !== 'undefined' ? __APP_BUILD_TS__ : '0';

// ── Visible error fallback (Task §八) ──
// If any descendant render throws, we capture it here and show a readable error
// card instead of an empty page. We never echo tokens, stacks with secrets, or
// raw request bodies — only a short message + the non-sensitive build id.
const fatalError = ref<{ id: string; message: string } | null>(null);
onErrorCaptured((err: any) => {
  const message = (err?.message || '渲染时发生未知错误').toString().slice(0, 160);
  fatalError.value = { id: BUILD_ID, message };
  return false; // stop propagation; we render our own fallback
});

// Safe timestamp formatter. The backend returns `observedAt` as a unix-ms
// NUMBER (not a string), so calling .slice() on it throws "not a function".
// Normalize to a string first, then format. Accepts number | string | null.
function formatTimestamp(ts: number | string | null | undefined): string {
  if (ts === null || ts === undefined || ts === '') return '—';
  const n = typeof ts === 'string' ? Number(ts) : ts;
  if (!Number.isFinite(n) || n <= 0) return '—';
  const d = new Date(n);
  if (isNaN(d.getTime())) return '—';
  const p = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}


const csrf = ref<string>('');
const dashboard = ref<Dashboard | null>(null);
const history = ref<{ t: number; temperature_c: number; humidity_pct: number }[]>([]);
const historyRange = ref<string>('1h');
const events = ref<{ id: number; event_type: string; device_id: string; message: string; created_at: number }[]>([]);
const ws = ref<WebSocket | null>(null);
const theme = ref<'dark' | 'light'>('dark');

// ── Session role (Task §二/§五) ──
// Guests (auto-created anonymous sessions) must NEVER see the armed real-IR button.
// The backend derives ir_armed from the session ROLE, but we also track it here so
// the login UI appears/disappears immediately after login/logout.
const sessionRole = ref<string>('guest');
const ownerUser = ref<string>('');
const showLogin = ref(false);
const loginUser = ref('');
const loginPass = ref('');
const loginBusy = ref(false);
const loginErr = ref('');

// ── Independent weather (Task §十一/§十二/§十三) ──
// Decoupled from device state: fed by /api/weather/current (backend WeatherService),
// updated via WS 'weather_update'. Shows last snapshot even when device is offline.
const weatherCurrent = ref<any>(null);
const weatherError = ref<string | null>(null);

const powerOn = ref(false);
const targetTemp = ref(26);
const busy = ref(false);
const ackMsg = ref('');
const lastAckAt = ref(0);

// ── Real-IR action (Section 九) ──────────────────────────────────────────
// Single button → one vendor PROGMEM code → device emits raw 22H frame once.
// Layered status: we can confirm the MODULE emitted IR (device ACK), but we can
// NOT confirm the physical AC responded, so AC status stays "pending" by design.
const IR_CODE_ID = 'hisense_cool_24_quiet_swing_v_on_swing_h_on_power_on_v1';
const irBusy = ref(false);
const irAckMsg = ref('');
const irModuleEmitted = ref(false); // device ACKed + module drove IR LED (NOT = AC success)
const irLastAt = ref(0);
const acPhysicalResponse = ref<'pending' | 'confirmed' | 'unknown'>('pending');

const weatherText = (code: number): string => {
  const m: Record<number, string> = {
    0: '晴', 1: '大致晴朗', 2: '局部多云', 3: '阴', 45: '雾', 48: '雾凇', 51: '毛毛雨', 53: '小雨', 55: '中雨',
    61: '小雨', 63: '中雨', 65: '大雨', 71: '小雪', 73: '中雪', 75: '大雪', 80: '阵雨', 95: '雷阵雨',
  };
  return m[code] ?? '未知';
};

const availabilityClass = computed(() => {
  const a = dashboard.value?.availability;
  if (a === 'online') return 'pill online';
  if (a === 'offline') return 'pill offline';
  return 'pill warn';
});

const availabilityText = computed(() => {
  const a = dashboard.value?.availability;
  return a === 'online' ? '在线' : a === 'offline' ? '离线' : '未知';
});

const isOnline = computed(() => dashboard.value?.availability === 'online');
const isOwner = computed(() => sessionRole.value === 'owner');

const settings = computed(() => dashboard.value?.settings ?? null);
const samplePeriodS = computed(() => (settings.value?.device_sample_interval_ms ?? 0) / 1000);
const publishPeriodS = computed(() => (settings.value?.device_publish_interval_ms ?? 0) / 1000);
const staleThresholdS = computed(() => (settings.value?.stale_threshold_ms ?? 0) / 1000);
const offlineThresholdS = computed(() => (settings.value?.offline_threshold_ms ?? 0) / 1000);

const tempNow = computed(() => dashboard.value?.latest_telemetry?.temperature_c ?? null);
const humNow = computed(() => dashboard.value?.latest_telemetry?.humidity_pct ?? null);
const fwVer = computed(() => dashboard.value?.firmware_version ?? '—');
const mqttBack = computed(() => dashboard.value?.mqtt_backend_connected ?? false);
const lastSeen = computed(() => {
  const t = dashboard.value?.last_seen_at;
  if (!t) return '—';
  const s = Math.floor((Date.now() - t) / 1000);
  if (s < 60) return `${s}秒前`;
  if (s < 3600) return `${Math.floor(s / 60)}分钟前`;
  return `${Math.floor(s / 3600)}小时前`;
});

function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value);
  try {
    localStorage.setItem('rac-theme', theme.value);
  } catch {
    /* ignore */
  }
  // re-render chart with new colors
  window.dispatchEvent(new Event('resize'));
}

function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark';
  applyTheme();
}

async function loadSession() {
  try {
    const s: SessionInfo = await fetchSession();
    if (s.csrf) csrf.value = s.csrf;
    sessionRole.value = s.role ?? 'guest';
    ownerUser.value = s.user ?? '';
  } catch {
    sessionRole.value = 'guest';
  }
}

async function loadDashboard() {
  try {
    dashboard.value = await fetchDashboard();
    syncControlFromIntent();
  } catch {
    /* session may have expired */
  }
}

// Independent weather fetch — never depends on device/dashboard payload.
async function loadWeather() {
  try {
    const w = await fetchWeatherCurrent();
    weatherCurrent.value = w;
    weatherError.value = null;
  } catch (e: any) {
    weatherError.value = e?.message || '天气暂时不可用';
  }
}

function syncControlFromIntent() {
  const intent = dashboard.value?.recent_commands?.find(
    (c: CommandRow) => c.status === 'accepted_mock' || c.status === 'blocked_by_ir_policy'
  );
  if (intent) {
    powerOn.value = intent.requested_power === 1;
    if (intent.requested_temperature_c) targetTemp.value = intent.requested_temperature_c;
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
    // Independent push from the backend WeatherService (device state irrelevant).
    weatherCurrent.value = payload;
    weatherError.value = null;
  } else if (type === 'ack' && payload) {
    ackMsg.value = `命令 ${String(payload.command_id).slice(0, 8)} → ${payload.status}${payload.reason ? ' (' + payload.reason + ')' : ''}`;
    lastAckAt.value = Date.now();
    // Layered IR status: device ACKed an IR action → module drove the IR LED.
    // This confirms EMISSION only — NOT that the physical AC responded.
    if (payload.status === 'ir_executed') {
      irModuleEmitted.value = true;
      irAckMsg.value = `红外模块已发射（命令 ${String(payload.command_id).slice(0, 8)}）· 空调是否响应未知`;
      irLastAt.value = Date.now();
      acPhysicalResponse.value = 'pending';
    } else if (payload.status === 'ir_module_busy' || payload.status === 'ir_execute_failed') {
      irAckMsg.value = `红外发射失败：${payload.status}${payload.reason ? ' (' + payload.reason + ')' : ''}`;
    }
    loadDashboard();
    loadEvents();
  }
}

async function initGuest() {
  await loadSession();
  await loadDashboard();
  await loadWeather();
  await loadHistory();
  await loadEvents();
  ws.value = connectWS(onWs);
}

async function doLogout() {
  try { await apiLogout(); } catch { /* ignore */ }
  sessionRole.value = 'guest';
  ownerUser.value = '';
  showLogin.value = false;
  // Re-init guest session
  ws.value?.close();
  await initGuest();
}

async function doLogin() {
  loginBusy.value = true;
  loginErr.value = '';
  try {
    const s = await fetchSession(); // ensure a guest cookie exists first
    const r: SessionInfo = await login(loginUser.value, loginPass.value);
    csrf.value = r.csrf || s.csrf || '';
    sessionRole.value = r.role ?? 'owner';
    ownerUser.value = r.user ?? '';
    showLogin.value = false;
    loginUser.value = '';
    loginPass.value = '';
    await loadDashboard();
    await loadWeather();
  } catch (e: any) {
    const ae = e as ApiError;
    loginErr.value = ae?.message || e?.message || '登录失败';
  } finally {
    loginBusy.value = false;
  }
}

async function sendSetState() {
  busy.value = true;
  ackMsg.value = '';
  try {
    const r = await sendCommand('set_state', { power: powerOn.value, target_temperature_c: targetTemp.value });
    ackMsg.value = `已下发（${String(r.command_id).slice(0, 8)}）…等待设备回执`;
  } catch (e: any) {
    ackMsg.value = '下发失败：' + (e?.message || '');
  } finally {
    busy.value = false;
    loadEvents();
  }
}

async function sendPower(on: boolean) {
  powerOn.value = on;
  busy.value = true;
  try {
    await sendCommand('set_power', { power: on });
  } catch (e: any) {
    ackMsg.value = '下发失败：' + (e?.message || '');
  } finally {
    busy.value = false;
  }
}

async function sendTemp() {
  busy.value = true;
  try {
    await sendCommand('set_temperature', { target_temperature_c: targetTemp.value });
  } catch (e: any) {
    ackMsg.value = '下发失败：' + (e?.message || '');
  } finally {
    busy.value = false;
  }
}

// Single real-IR action (Section 九). Only rendered when dashboard.ir_armed is true,
// which the backend sets ONLY for an OWNER session with WEB_REAL_IR_ENABLED=true.
// (This is the root-cause fix for the spurious guest 403 — guests never see the
// button, so they can no longer click it and hit OWNER_REQUIRED.)
async function sendIrActionOnce() {
  if (!dashboard.value?.ir_armed) {
    irAckMsg.value = '真实红外未启用（需所有者登录且 WEB_REAL_IR_ENABLED=true）';
    return;
  }
  irBusy.value = true;
  irAckMsg.value = '';
  irModuleEmitted.value = false;
  acPhysicalResponse.value = 'pending';
  try {
    const r = await sendIrAction(IR_CODE_ID);
    irAckMsg.value = `已下发（${r.command_id.slice(0, 8)}）…等待设备回执`;
  } catch (e: any) {
    const ae = e as ApiError;
    // Show the precise structured envelope: [errorCode] message — not a bare "403 ".
    irAckMsg.value = `下发失败：${ae?.errorCode ? '[' + ae.errorCode + '] ' : ''}${ae?.message || e?.message || ''}`;
  } finally {
    irBusy.value = false;
    loadEvents();
  }
}

let pollTimer: any = null;
let weatherTimer: any = null;
onMounted(async () => {
  try {
    const saved = localStorage.getItem('rac-theme') as 'dark' | 'light' | null;
    if (saved) theme.value = saved;
  } catch {
    /* ignore */
  }
  applyTheme();
  await initGuest();
  pollTimer = setInterval(() => {
    loadDashboard();
    loadEvents();
  }, 10000);
  // Independent weather poll (backend refreshes every 10 min; this is the fallback).
  weatherTimer = setInterval(() => {
    loadWeather();
  }, 60000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (weatherTimer) clearInterval(weatherTimer);
  ws.value?.close();
});
</script>

<template>
  <div>
    <!-- Visible error fallback (Task §八): a captured render error shows a
         readable card instead of an empty page. No tokens / secrets / raw stacks. -->
    <div v-if="fatalError" class="error-fallback">
      <div class="error-card">
        <h2>⚠️ 页面渲染出错</h2>
        <p class="error-msg">{{ fatalError.message }}</p>
        <p class="error-meta">
          错误编号：{{ fatalError.id }}<br />
          构建标识：{{ BUILD_ID }} · 提交：{{ GIT_COMMIT.slice(0, 12) }}<br />
          请刷新页面重试；若反复出现，请联系管理员并提供以上编号。
        </p>
      </div>
    </div>

    <!-- Main (public guest mode — no login required for read-only view) -->
    <div>
      <div class="topbar">
        <div class="title">☁️ 云端空调管家</div>
        <div style="display: flex; gap: 8px">
          <button class="icon-btn" @click="toggleTheme">{{ theme === 'dark' ? '🌙' : '☀️' }}</button>
          <button v-if="isOwner" class="icon-btn" @click="doLogout">退出</button>
          <button v-else class="icon-btn" @click="showLogin = true">所有者登录</button>
        </div>
      </div>

      <!-- Owner login card -->
      <div class="card" v-if="showLogin">
        <h3>🔐 所有者登录（真实红外操作需要）</h3>
        <div class="sub" style="margin-bottom: 8px">登录后本页才会显示「单次真实红外发射」按钮。普通控制无需登录。</div>
        <div style="display: flex; flex-direction: column; gap: 8px; max-width: 320px">
          <input v-model="loginUser" placeholder="用户名" :disabled="loginBusy" style="padding: 8px; border-radius: 8px; border: 1px solid var(--border)" />
          <input v-model="loginPass" type="password" placeholder="密码" :disabled="loginBusy" @keyup.enter="doLogin" style="padding: 8px; border-radius: 8px; border: 1px solid var(--border)" />
          <div v-if="loginErr" class="badge-offline-msg">{{ loginErr }}</div>
          <div class="btn-row">
            <button :disabled="loginBusy" @click="doLogin">{{ loginBusy ? '登录中…' : '登录' }}</button>
            <button class="ghost" @click="showLogin = false">取消</button>
          </div>
        </div>
      </div>

      <!-- Status -->
      <div class="card">
        <div class="row">
          <span :class="availabilityClass">{{ availabilityText }}</span>
          <span class="sub">
            设备 {{ dashboard?.ir_control === 'disabled' ? '（红外控制已禁用）' : '' }}
            <span v-if="dashboard?.latest_telemetry?.simulated" class="badge badge-sim-sm">模拟</span>
          </span>
        </div>
        <div class="row" style="margin-top: 8px">
          <span class="sub">最后心跳：{{ lastSeen }}</span>
          <span class="sub">固件 {{ fwVer }}</span>
        </div>
        <div class="row" style="margin-top: 4px">
          <span class="sub">后端MQTT：{{ mqttBack ? '已连接' : '未连接' }}</span>
        </div>
      </div>

      <div class="dashboard-grid">

      <!-- Indoor -->
      <div class="card">
        <h3>🛏️ 室内（卧室）
          <span v-if="dashboard?.latest_telemetry?.simulated" class="badge badge-sim">模拟</span>
          <span v-else-if="dashboard?.latest_telemetry" class="badge badge-real">真实设备</span>
        </h3>
        <div class="grid2">
          <div>
            <div class="sub">温度</div>
            <div class="big">{{ tempNow !== null ? tempNow.toFixed(1) : '—' }}<span style="font-size: 18px">℃</span></div>
          </div>
          <div>
            <div class="sub">湿度</div>
            <div class="big">{{ humNow !== null ? humNow.toFixed(0) : '—' }}<span style="font-size: 18px">%</span></div>
          </div>
        </div>
        <div class="sub" style="margin-top: 8px">
          RSSI {{ dashboard?.latest_telemetry?.wifi_rssi_dbm ?? '—' }} dBm ·
          空闲堆 {{ dashboard?.latest_telemetry?.free_heap_bytes ? (dashboard.latest_telemetry.free_heap_bytes / 1024).toFixed(0) + ' KB' : '—' }}
        </div>
        <div class="sub" style="margin-top: 4px; font-size: 10px; color: var(--text-dim)">
          最后更新：{{ lastSeen }} ·
          数据来源：{{ dashboard?.latest_telemetry?.simulated ? '模拟设备' : dashboard?.latest_telemetry ? '真实设备' : '无数据' }}
        </div>
      </div>

      <!-- Xi'an weather (INDEPENDENT of device state) -->
      <div class="card" v-if="weatherCurrent?.current">
        <h3>🌤️ 西安室外天气
          <span v-if="weatherCurrent.stale" class="badge badge-cache">数据略旧</span>
          <span v-else class="badge badge-real">实时</span>
        </h3>
        <div class="row">
          <div>
            <div class="big">{{ weatherCurrent.current.temperatureC.toFixed(1) }}<span style="font-size: 18px">℃</span></div>
            <div class="sub">{{ weatherText(weatherCurrent.current.weatherCode) }} · 体感 {{ weatherCurrent.current.apparentTemperatureC.toFixed(1) }}℃</div>
          </div>
          <div style="text-align: right">
            <div class="sub">湿度 {{ weatherCurrent.current.relativeHumidity }}%</div>
            <div class="sub">风速 {{ weatherCurrent.current.windSpeed }} km/h</div>
            <div class="sub" style="font-size: 10px; color: var(--text-dim)">来源：Open-Meteo（独立服务）</div>
            <div class="sub" style="font-size: 10px; color: var(--text-dim)">观测时间：{{ formatTimestamp(weatherCurrent.observedAt) }}</div>
          </div>
        </div>
        <div class="sub" style="margin-top: 6px; font-size: 10px; color: var(--text-dim)" v-if="weatherCurrent.error">
          上次刷新出错，已保留最后成功数据：{{ weatherCurrent.error }}
        </div>
      </div>
      <div class="card" v-else-if="weatherError">
        <h3>🌤️ 西安室外天气</h3>
        <div class="sub">暂不可用：{{ weatherError }}（天气服务与设备状态无关，稍后自动重试）</div>
      </div>

      <!-- Control -->
      <div class="card">
        <h3>🎛️ 控制（网页 → 云端 → ESP8266）</h3>
        <div class="btn-row" style="margin-bottom: 12px">
          <button :class="powerOn ? 'ok' : 'ghost'" :disabled="busy || !isOnline" @click="sendPower(true)">开机</button>
          <button :class="!powerOn ? 'danger' : 'ghost'" :disabled="busy || !isOnline" @click="sendPower(false)">关机</button>
        </div>
        <div v-if="!isOnline" class="badge-offline-msg">设备离线，无法下发命令</div>
        <div class="sub">目标温度：{{ targetTemp }}℃</div>
        <input type="range" min="16" max="30" step="1" v-model.number="targetTemp" :disabled="!isOnline" />
        <div class="btn-row" style="margin-top: 12px">
          <button :disabled="busy || !isOnline" @click="sendTemp">仅设温</button>
          <button :disabled="busy || !isOnline" @click="sendSetState">下发完整状态</button>
        </div>
        <div class="badge-ir">命令已到达设备，但红外控制仍处于安全禁用状态（blocked_by_ir_policy）</div>
        <div v-if="ackMsg" class="sub" style="margin-top: 10px; color: var(--accent)">{{ ackMsg }}</div>
      </div>

      <!-- Real-IR action (Section 九): single button → module emits raw 22H frame once -->
      <div class="card" v-if="dashboard?.ir_armed">
        <h3>📡 真实红外发射（模块 → 空调）</h3>
        <div class="sub" style="margin-bottom: 8px">
          一次性发射：开机 · 制冷 24℃ · 静音 · 双向扫风
        </div>
        <button :class="irModuleEmitted ? 'ok' : 'ir'" :disabled="irBusy || !isOnline" @click="sendIrActionOnce">
          {{ irBusy ? '发射中…' : '开机：制冷24℃·静音·双向扫风' }}
        </button>
        <div v-if="!isOnline" class="badge-offline-msg">设备离线，无法下发红外命令</div>
        <!-- Layered status: emission confirmed ≠ AC responded -->
        <div class="ir-layers" style="margin-top: 10px">
          <div class="layer" :class="irModuleEmitted ? 'done' : ''">
            ① 模块已发射红外：{{ irModuleEmitted ? '是' : '否' }}
          </div>
          <div class="layer" :class="acPhysicalResponse === 'confirmed' ? 'done' : ''">
            ② 空调是否响应：{{ acPhysicalResponse === 'pending' ? '未知（需人工确认）' : acPhysicalResponse === 'confirmed' ? '已确认' : '未知' }}
          </div>
        </div>
        <div v-if="irAckMsg" class="sub" style="margin-top: 10px; color: var(--accent)">{{ irAckMsg }}</div>
      </div>
      <div class="card" v-else-if="dashboard">
        <h3>📡 真实红外发射</h3>
        <div class="badge-ir">真实红外发射未启用（安全默认：WEB_REAL_IR_ENABLED=false）。需<strong>所有者登录</strong>并显式开启后，本卡片才会激活单次发射按钮。访客点击不会触发 403 —— 因为按钮对访客根本不显示。</div>
        <button v-if="!isOwner" class="ghost" style="margin-top: 10px" @click="showLogin = true">所有者登录</button>
      </div>

      <!-- Run params (real device, read from code/runtime — not suggested values) -->
      <div class="card" v-if="settings">
        <h3>⚙️ 运行参数（真实设备）</h3>
        <div class="sub">采样周期：{{ samplePeriodS }}s · 上传周期：{{ publishPeriodS }}s</div>
        <div class="sub">陈旧阈值：{{ staleThresholdS }}s · 离线阈值：{{ offlineThresholdS }}s</div>
        <div class="sub" style="margin-top: 4px; font-size: 10px; color: var(--text-dim)">
          数据来源：ESP8266 + DHT11 · 数据类型：真实设备 · 模拟：否
        </div>
      </div>

      </div><!-- dashboard-grid -->

      <!-- Trend -->
      <div class="card">
        <h3>📈 温湿度趋势</h3>
        <div class="btn-row" style="margin-bottom: 10px">
          <button class="ghost" v-for="r in ['1h', '6h', '24h', '7d']" :key="r" :style="historyRange === r ? 'border-color: var(--accent); color: var(--accent)' : ''" @click=";(historyRange = r), loadHistory()">{{ r }}</button>
        </div>
        <TrendChart :points="history" />
      </div>

      <!-- Events -->
      <div class="card">
        <h3>📜 事件 / 命令回执</h3>
        <div v-if="events.length === 0" class="sub">暂无事件</div>
        <div v-for="e in events.slice(0, 12)" :key="e.id" class="event">
          <span class="t">{{ new Date(e.created_at).toLocaleTimeString() }}</span> · {{ e.event_type }} · {{ e.message }}
        </div>
      </div>

      <!-- Build/release identity (non-sensitive; confirms loaded release) -->
      <div class="footer-build">
        构建：{{ BUILD_ID }} · 提交：{{ GIT_COMMIT.slice(0, 12) }} · 时间：{{ BUILD_TS }}
      </div>
    </div>
  </div>
</template>

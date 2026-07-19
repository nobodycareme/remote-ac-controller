<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import {
  fetchSession,
  login as apiLogin,
  logout as apiLogout,
  fetchDashboard,
  fetchTelemetryHistory,
  fetchEvents,
  sendCommand,
  connectWS,
  type SessionInfo,
  type Dashboard,
  type CommandRow,
} from './api';
import TrendChart from './components/TrendChart.vue';

const session = ref<SessionInfo | null>(null);
const dashboard = ref<Dashboard | null>(null);
const history = ref<{ t: number; temperature_c: number; humidity_pct: number }[]>([]);
const historyRange = ref<string>('1h');
const events = ref<{ id: number; event_type: string; device_id: string; message: string; created_at: number }[]>([]);
const ws = ref<WebSocket | null>(null);
const theme = ref<'dark' | 'light'>('dark');

const loginUser = ref('');
const loginPass = ref('');
const loginErr = ref('');

const powerOn = ref(false);
const targetTemp = ref(26);
const busy = ref(false);
const ackMsg = ref('');
const lastAckAt = ref(0);

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

async function loadDashboard() {
  try {
    dashboard.value = await fetchDashboard();
    syncControlFromIntent();
  } catch {
    /* session may have expired */
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
  } else if (type === 'ack' && payload) {
    ackMsg.value = `命令 ${payload.command_id.slice(0, 8)} → ${payload.status}${payload.reason ? ' (' + payload.reason + ')' : ''}`;
    lastAckAt.value = Date.now();
    loadDashboard();
    loadEvents();
  }
}

async function doLogin() {
  loginErr.value = '';
  try {
    session.value = await apiLogin(loginUser.value, loginPass.value);
    await afterAuth();
  } catch (e: any) {
    loginErr.value = '登录失败：' + (e?.message || '凭据错误');
  }
}

async function doLogout() {
  try {
    await apiLogout();
  } catch {
    /* ignore */
  }
  session.value = null;
  csrfCleared();
  ws.value?.close();
}

function csrfCleared() {
  // csrf cleared inside api client
}

async function afterAuth() {
  await loadDashboard();
  await loadHistory();
  await loadEvents();
  ws.value = connectWS(onWs);
}

async function sendSetState() {
  busy.value = true;
  ackMsg.value = '';
  try {
    const r = await sendCommand('set_state', { power: powerOn.value, target_temperature_c: targetTemp.value });
    ackMsg.value = `已下发（${r.command_id.slice(0, 8)}）…等待设备回执`;
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

let pollTimer: any = null;
onMounted(async () => {
  try {
    const saved = localStorage.getItem('rac-theme') as 'dark' | 'light' | null;
    if (saved) theme.value = saved;
  } catch {
    /* ignore */
  }
  applyTheme();
  try {
    const s = await fetchSession();
    if (s.authenticated) {
      session.value = s;
      await afterAuth();
    }
  } catch {
    /* not authed */
  }
  pollTimer = setInterval(() => {
    if (session.value?.authenticated) {
      loadDashboard();
      loadEvents();
    }
  }, 10000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  ws.value?.close();
});
</script>

<template>
  <div>
    <!-- Login modal -->
    <div v-if="!session?.authenticated" class="modal-mask">
      <div class="modal">
        <h2>云端空调管家</h2>
        <label>用户名</label>
        <input v-model="loginUser" type="text" placeholder="admin" autocomplete="username" />
        <label>密码</label>
        <input v-model="loginPass" type="password" placeholder="••••••" autocomplete="current-password" @keyup.enter="doLogin" />
        <div class="err">{{ loginErr }}</div>
        <button style="width: 100%; margin-top: 12px" @click="doLogin">登录</button>
        <div class="muted" style="margin-top: 12px; text-align: center">手机远程控制空调 · 云端联调</div>
      </div>
    </div>

    <!-- Main -->
    <template v-else>
      <div class="topbar">
        <div class="title">☁️ 云端空调管家</div>
        <div style="display: flex; gap: 8px">
          <button class="icon-btn" @click="toggleTheme">{{ theme === 'dark' ? '🌙' : '☀️' }}</button>
          <button class="icon-btn" @click="doLogout">退出</button>
        </div>
      </div>

      <!-- Status -->
      <div class="card">
        <div class="row">
          <span :class="availabilityClass">{{ availabilityText }}</span>
          <span class="sub">设备 {{ dashboard?.ir_control === 'disabled' ? '（红外控制已禁用）' : '' }}</span>
        </div>
        <div class="row" style="margin-top: 8px">
          <span class="sub">最后心跳：{{ lastSeen }}</span>
          <span class="sub">固件 {{ fwVer }}</span>
        </div>
        <div class="row" style="margin-top: 4px">
          <span class="sub">后端MQTT：{{ mqttBack ? '已连接' : '未连接' }}</span>
        </div>
      </div>

      <!-- Indoor -->
      <div class="card">
        <h3>🛏️ 室内（卧室）</h3>
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
      </div>

      <!-- Xi'an weather -->
      <div class="card" v-if="dashboard?.weather">
        <h3>🌤️ 西安室外天气</h3>
        <div class="row">
          <div>
            <div class="big">{{ dashboard.weather.temperature_2m.toFixed(1) }}<span style="font-size: 18px">℃</span></div>
            <div class="sub">{{ weatherText(dashboard.weather.weather_code) }} · 体感 {{ dashboard.weather.apparent_temperature.toFixed(1) }}℃</div>
          </div>
          <div style="text-align: right">
            <div class="sub">湿度 {{ dashboard.weather.relative_humidity_2m }}%</div>
            <div class="sub">风速 {{ dashboard.weather.wind_speed_10m }} km/h</div>
            <div class="sub">{{ dashboard.weather.stale ? '（缓存）' : '实时' }} · {{ dashboard.weather.time }}</div>
          </div>
        </div>
      </div>
      <div class="card" v-else-if="dashboard?.weather_error">
        <h3>🌤️ 西安室外天气</h3>
        <div class="sub">暂不可用：{{ dashboard.weather_error }}</div>
      </div>

      <!-- Control -->
      <div class="card">
        <h3>🎛️ 控制（网页 → 云端 → ESP8266）</h3>
        <div class="btn-row" style="margin-bottom: 12px">
          <button :class="powerOn ? 'ok' : 'ghost'" @click="sendPower(true)">开机</button>
          <button :class="!powerOn ? 'danger' : 'ghost'" @click="sendPower(false)">关机</button>
        </div>
        <div class="sub">目标温度：{{ targetTemp }}℃</div>
        <input type="range" min="16" max="30" step="1" v-model.number="targetTemp" />
        <div class="btn-row" style="margin-top: 12px">
          <button :disabled="busy" @click="sendTemp">仅设温</button>
          <button :disabled="busy" @click="sendSetState">下发完整状态</button>
        </div>
        <div class="badge-ir">真实红外发射已按安全策略禁用；命令将真实下发并由设备回执（blocked_by_ir_policy）</div>
        <div v-if="ackMsg" class="sub" style="margin-top: 10px; color: var(--accent)">{{ ackMsg }}</div>
      </div>

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
    </template>
  </div>
</template>

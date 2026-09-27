<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { weekdays, minutes, parseWeeks, addDays, dateInZone, weekOf, occurrences, conflicts } from './core.mjs';
import Modal from './components/Modal.vue';
import ScheduleView from './components/ScheduleView.vue';
import CourseEditor from './components/CourseEditor.vue';
import SettingsEditor from './components/SettingsEditor.vue';
const data = ref(null), revision = ref(0), authenticated = ref(false), selectedWeek = ref(1);
const view = ref(globalThis.matchMedia?.('(max-width:700px)').matches ? 'list' : 'week');
const preview = ref(false), modal = ref(''), selected = ref(null), busy = ref(false), error = ref(''), password = ref('');
const status = ref('正在读取课表…'), loadError = ref(''), message = ref(''), clock = ref(new Date());
let realData, pendingAction, timer, toastTimer, active = true, loading = false;
const clone = value => JSON.parse(JSON.stringify(value));
let savedTheme; try { savedTheme = localStorage.getItem('course-theme'); } catch { /* storage is optional */ }
const theme = ref(savedTheme || (globalThis.matchMedia?.('(prefers-color-scheme:dark)').matches ? 'dark' : 'light'));
document.documentElement.dataset.theme = theme.value;
function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme.value; try { localStorage.setItem('course-theme', theme.value); } catch { /* storage is optional */ } }
const now = computed(() => data.value ? dateInZone(data.value.settings.timezone, clock.value) : { date: '', time: '' });
const actualWeek = computed(() => data.value ? weekOf(data.value.settings.startDate, now.value.date) : 1);
const currentWeek = computed(() => data.value ? Math.max(1, Math.min(data.value.settings.totalWeeks, actualWeek.value)) : 1);
const start = computed(() => data.value ? addDays(data.value.settings.startDate, (selectedWeek.value - 1) * 7) : '');
const items = computed(() => data.value ? occurrences(data.value, selectedWeek.value) : []);
const hours = computed(() => (items.value.reduce((sum, x) => sum + minutes(x.end) - minutes(x.start), 0) / 60).toFixed(1));
const termNote = computed(() => !data.value ? '' : actualWeek.value < 1 ? '学期尚未开始' : actualWeek.value > data.value.settings.totalWeeks ? '这个学期已经结束' : `今天是第 ${actualWeek.value} 周 · ${weekdays[(new Date(now.value.date + 'T00:00Z').getUTCDay() + 6) % 7]}`);
const next = computed(() => {
  if (!data.value) return null;
  for (let w = Math.max(1, actualWeek.value); w <= data.value.settings.totalWeeks; w++) {
    const item = occurrences(data.value, w).find(x => x.date > now.value.date || (x.date === now.value.date && x.end > now.value.time));
    if (item) return item;
  }
  return null;
});
const notes = computed(() => (selected.value?.notes || '').split(/(https?:\/\/[^\s<>]+)/g).map(text => ({ text, link: /^https?:\/\//.test(text) })));
function toast(text) { message.value = text; clearTimeout(toastTimer); toastTimer = setTimeout(() => message.value = '', 4200); }
function open(name) { error.value = ''; modal.value = name; }
function close() { if (!busy.value) { modal.value = ''; password.value = ''; pendingAction = null; } }
function requireEdit(action) { if (preview.value) return toast('正在查看示例，先返回我的课表再编辑'); if (authenticated.value) action(); else { pendingAction = action; password.value = ''; open('login'); } }
function edit(course = null) { requireEdit(() => { selected.value = course; open('course'); }); }
function detail(course) { selected.value = course; open('detail'); }
async function api(path, options = {}) {
  const response = await fetch(`/api/${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
  const result = await response.json();
  if (!response.ok) { if (response.status === 401) authenticated.value = false; throw new Error(result.error || '请求失败，请稍后重试'); }
  return result;
}
async function load(initial = false) {
  if (loading || preview.value || (!initial && modal.value)) return;
  loading = true;
  // Ignore a response if an editor opened or a save completed while it was in flight.
  const before = revision.value;
  try {
    const result = await api('schedule');
    if (!active || preview.value || modal.value || revision.value !== before) return;
    data.value = result.data; revision.value = result.revision; authenticated.value = result.authenticated;
    clock.value = new Date(); selectedWeek.value = initial ? currentWeek.value : Math.min(selectedWeek.value, data.value.settings.totalWeeks);
    loadError.value = ''; status.value = '已同步 · ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } catch (err) { status.value = data.value ? '连接中断 · 当前为已加载的课表' : '未连接'; loadError.value = err.message; }
  finally { loading = false; }
}
async function save(value) {
  const result = await api('schedule', { method: 'PUT', body: JSON.stringify({ data: value, revision: revision.value }) });
  data.value = result.data; revision.value = result.revision; selectedWeek.value = Math.min(selectedWeek.value, data.value.settings.totalWeeks);
  status.value = '已保存 · ' + new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }); toast('已保存，所有设备都会同步');
}
async function perform(action) { if (busy.value) return; busy.value = true; error.value = ''; try { await action(); } catch (err) { error.value = err.message; } finally { busy.value = false; } }
async function saveCourse(draft) {
  await perform(async () => {
    const course = clone(draft); course.id ||= globalThis.crypto.randomUUID(); course.name = course.name.trim();
    if (!course.name) throw new Error('请填写课程名称');
    for (const s of course.sessions) { parseWeeks(s.weeks, data.value.settings.totalWeeks); if (s.start >= s.end) throw new Error('结束时间须晚于开始时间；跨天课程请拆成两个时段'); }
    const value = clone(data.value); const index = value.courses.findIndex(x => x.id === course.id);
    if (index < 0) value.courses.push(course); else value.courses[index] = course;
    const overlap = conflicts(value.courses, value.settings.totalWeeks);
    if (overlap.length && !confirm('以下课程的上课时间有重叠：\n' + overlap.slice(0, 8).join('\n') + '\n\n仍然保存吗？')) return;
    await save(value); modal.value = '';
  });
}
async function deleteCourse(id) { if (!confirm('删除这门课程及其所有上课时段？')) return; await perform(async () => { const value = clone(data.value); value.courses = value.courses.filter(c => c.id !== id); await save(value); modal.value = ''; }); }
async function saveSettings(settings) { await perform(async () => {
  if (new Date(settings.startDate + 'T00:00Z').getUTCDay() !== 1) throw new Error('请选择第一周的周一，保证周次与星期一致');
  if (settings.dayStart >= settings.dayEnd) throw new Error('课表结束时间须晚于起始时间');
  for (const c of data.value.courses) for (const s of c.sessions) parseWeeks(s.weeks, settings.totalWeeks);
  await save({ ...clone(data.value), settings: clone(settings) }); modal.value = '';
}); }
async function login() { await perform(async () => { await api('login', { method: 'POST', body: JSON.stringify({ password: password.value }) }); authenticated.value = true; password.value = ''; modal.value = ''; const action = pendingAction; pendingAction = null; action?.(); }); }
async function logout() { try { await api('logout', { method: 'POST', body: '{}' }); authenticated.value = false; toast('已退出编辑'); } catch (err) { toast(err.message); } }
function exportData() { const url = URL.createObjectURL(new Blob([JSON.stringify(data.value, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = `课间-${now.value.date}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
async function importData(file) { await perform(async () => { if (file.size > 512000) throw new Error('备份文件不能超过 500 KB'); const value = JSON.parse(await file.text()); if (!value.settings || !Array.isArray(value.courses)) throw new Error('这不是有效的课表备份'); if (!confirm(`导入将替换当前的 ${data.value.courses.length} 门课程。建议先导出备份。继续吗？`)) return; await save(value); modal.value = ''; }); }
function togglePreview() {
  if (preview.value) { data.value = realData; preview.value = false; selectedWeek.value = currentWeek.value; load(); return; }
  realData = data.value; const sample = clone(data.value);
  sample.courses = [['线性代数', 'green', '理科楼 A302', '陈老师', 1, '08:00', '09:40'], ['大学英语', 'blue', '文科楼 B205', '李老师', 2, '10:00', '11:40'], ['概率论与数理统计', 'mauve', '理科楼 A406', '王老师', 3, '08:00', '09:40'], ['数据结构', 'peach', '计算机楼 201', '刘老师', 4, '14:00', '15:40'], ['体育 · 羽毛球', 'rose', '体育馆', '', 5, '16:00', '17:30']].map(([name, color, location, teacher, day, start, end], i) => ({ id: 'demo-' + i, name, color, location, teacher, notes: '仅为界面示例。请返回我的课表，录入你的真实课程。', sessions: [{ day, start, end, weeks: `1-${sample.settings.totalWeeks}` }] }));
  data.value = sample; preview.value = true;
}
function refresh() { if (!document.hidden) { clock.value = new Date(); load(); } }
onMounted(() => { load(true); timer = setInterval(refresh, 60000); document.addEventListener('visibilitychange', refresh); });
onUnmounted(() => { active = false; clearInterval(timer); clearTimeout(toastTimer); document.removeEventListener('visibilitychange', refresh); });
</script>
<template>
  <div class="page"><header class="masthead"><a class="wordmark" href="/"><span class="mark">课</span>课间<span class="wordmark-en"> / timetable</span></a><nav aria-label="页面操作"><button id="theme" class="icon-button" aria-label="切换深浅主题" @click="toggleTheme">◐</button><button id="settings-button" class="text-button" :disabled="!data" @click="requireEdit(() => open('settings'))">学期设置 ↗</button></nav></header>
  <main><section class="intro"><div><p class="eyebrow">{{ data ? data.settings.title + ' / ' : '' }}MY TIMETABLE</p><h1>有课的日子，<br class="mobile-break">也留一点空白。</h1><p class="intro-note">{{ data ? termNote + '，' : '' }}把时间交还给眼前的事。</p></div><button id="add-course" class="primary" :disabled="!data" @click="edit()">＋ 添加课程</button></section>
  <template v-if="data"><section class="next-up" aria-label="接下来的课程"><span class="next-label"><i class="live-dot"></i>{{ next ? next.date === now.date && next.start <= now.time ? '正在上课' : '下一节课' : '接下来' }}</span><template v-if="next"><button class="next-content" style="text-align:left" @click="detail(next.course)"><strong>{{ next.course.name }}</strong><span>{{ next.location || '地点待填写' }}</span></button><span class="next-when">{{ next.date === now.date ? '今天' : next.date.slice(5).replace('-', '/') }} {{ next.start }}–{{ next.end }}</span></template><div v-else class="next-content"><strong>{{ data.courses.length ? '暂时没有课程安排' : '课表还空着，慢慢填满它。' }}</strong></div></section>
  <section class="schedule-section" aria-label="课程安排"><div class="toolbar"><div class="week-nav"><button class="icon-button" aria-label="上一周" :disabled="selectedWeek <= 1" @click="selectedWeek--">←</button><button class="week-title" aria-label="选择周次" @click="open('week')">第 {{ String(selectedWeek).padStart(2, '0') }} 周<span class="chevron">⌄</span></button><button class="icon-button" aria-label="下一周" :disabled="selectedWeek >= data.settings.totalWeeks" @click="selectedWeek++">→</button><button v-if="selectedWeek !== currentWeek" class="today-button" @click="selectedWeek = currentWeek">回到本周</button></div><div class="view-switch" aria-label="视图"><button :aria-pressed="view === 'week'" @click="view = 'week'">周课表</button><button :aria-pressed="view === 'list'" @click="view = 'list'">日程</button></div></div>
  <div class="schedule-meta"><span>{{ start.replaceAll('-', '.') }} — {{ addDays(start, 6).slice(5).replace('-', '.') }}</span><span>{{ items.length }} 节课 · {{ hours }} 小时</span></div><div v-if="preview" class="preview-banner">示例预览 · 以下课程仅用于展示，不会保存到你的课表。</div>
  <ScheduleView :data="data" :items="items" :start="start" :now="now" :view="view" @detail="detail" @add="edit()" /></section>
  <section class="course-index"><div class="section-heading"><h2>我的课程 <span>{{ String(data.courses.length).padStart(2, '0') }}</span></h2><button id="preview-button" class="text-button" @click="togglePreview">{{ preview ? '返回我的课表 ↗' : '看看示例 ↗' }}</button></div><div v-if="data.courses.length" class="course-index-list"><button v-for="c in data.courses" :key="c.id" class="course-index-item" :style="{ '--course-color': `var(--${c.color})` }" @click="detail(c)"><span class="color-dot"></span><span><strong>{{ c.name }}</strong><small>{{ [!c.sessions.length ? '时间待定' : '', c.teacher, c.location].filter(Boolean).join(' · ') || '未填写课程信息' }}</small></span><span class="arrow">↗</span></button></div><p v-else class="subtle">课程名称、教室、老师和备注，都收在这里。</p></section></template>
  <div v-else-if="loadError" class="empty-state"><h3>暂时没能读到课表</h3><p>{{ loadError }}</p><button class="secondary" @click="load(true)">重新读取</button></div><div v-else class="loading">正在翻开这一周…</div></main>
  <footer><span>课间 <span class="footer-dot">·</span> 一周，一页，从容一点。</span><div><span role="status">{{ status }}</span><button v-if="authenticated" class="text-button" @click="logout">退出编辑</button></div></footer></div>
  <Modal v-if="modal" :key="modal" :label="({ course: '课程编辑', detail: '课程详情', settings: '学期设置', login: '进入编辑', week: '选择周次' })[modal]" @close="close">
    <CourseEditor v-if="modal === 'course'" :course="selected" :total-weeks="data.settings.totalWeeks" :busy="busy" :error="error" @save="saveCourse" @delete="deleteCourse" @close="close" />
    <SettingsEditor v-else-if="modal === 'settings'" :settings="data.settings" :busy="busy" :error="error" @save="saveSettings" @close="close" @export="exportData" @import="importData" />
    <template v-else-if="modal === 'detail'"><div class="dialog-heading"><p class="eyebrow">COURSE NOTES</p><button class="icon-button" aria-label="关闭" @click="close">×</button></div><h2>{{ selected.name }}</h2><p class="detail-subtitle">{{ [selected.location, selected.teacher].filter(Boolean).join(' · ') }}</p><div v-for="(s, i) in selected.sessions" :key="i" class="detail-session">{{ weekdays[s.day - 1] }} · {{ s.start }}–{{ s.end }}<small>第 {{ s.weeks }} 周 · {{ s.location || selected.location || '地点待填写' }}</small></div><p v-if="!selected.sessions.length" class="subtle">时间待定，请以授课教师或开课单位通知为准。</p><dl v-if="selected.notes"><dt>备注</dt><dd class="notes"><template v-for="(part, i) in notes" :key="i"><a v-if="part.link" :href="part.text" target="_blank" rel="noopener noreferrer">{{ part.text }}</a><template v-else>{{ part.text }}</template></template></dd></dl><div class="dialog-actions"><span></span><button v-if="!preview" class="primary" @click="edit(selected)">编辑课程</button></div></template>
    <form v-else-if="modal === 'login'" id="login-form" @submit.prevent="login"><div class="dialog-heading"><div><p class="eyebrow">JUST FOR YOU</p><h2>进入编辑</h2></div><button type="button" class="icon-button" aria-label="关闭" @click="close">×</button></div><p class="field-help">输入你的课表密码，在任何设备上管理同一份课程安排。</p><label>课表密码<input v-model="password" type="password" autocomplete="current-password" required></label><p class="form-error" role="alert">{{ error }}</p><div class="dialog-actions"><span></span><button type="submit" class="primary" :disabled="busy">{{ busy ? '验证中…' : '继续 →' }}</button></div></form>
    <template v-else-if="modal === 'week'"><div class="dialog-heading"><h2>选择周次</h2><button class="icon-button" aria-label="关闭" @click="close">×</button></div><div id="weeks-grid"><button v-for="w in data.settings.totalWeeks" :key="w" :class="{ selected: w === selectedWeek }" @click="selectedWeek = w; close()">第 {{ w }} 周</button></div></template>
  </Modal><div v-if="message" id="toast" role="status">{{ message }}</div>
</template>

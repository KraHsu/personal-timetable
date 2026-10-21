<script setup>
import { computed, ref, watch } from 'vue';
import { dateInZone } from '../core.mjs';
const props = defineProps(['config', 'timezone', 'busy', 'error', 'lastDelivery']);
const emit = defineEmits(['save', 'close']);
const draft = ref(null);
const kindLabels = { homework: '作业', exam: '考试', other: '事项' };
const items = computed(() => [...props.config.items].sort((a, b) => Number(a.completed) - Number(b.completed) || (a.remindAt || a.dueAt).localeCompare(b.remindAt || b.dueAt)));
watch(() => props.config, () => { draft.value = null; });
function edit(item) { draft.value = item ? { ...item } : { id: crypto.randomUUID(), title: '', kind: 'homework', dueAt: '', remindAt: '', notes: '', enabled: true, completed: false }; }
function saveItem() {
  const config = JSON.parse(JSON.stringify(props.config));
  const item = { ...draft.value, title: draft.value.title.trim() };
  const index = config.items.findIndex(x => x.id === item.id);
  if (index < 0) config.items.push(item); else config.items[index] = item;
  emit('save', config);
}
function changeCourse(event) { emit('save', { ...props.config, courseEnabled: event.target.checked }); event.target.checked = props.config.courseEnabled; }
function changeFirst(event) { emit('save', { ...props.config, firstCourseEnabled: event.target.checked }); event.target.checked = props.config.firstCourseEnabled ?? true; }
function changeFriday(event) { if (event.target.value) emit('save', { ...props.config, firstCourseTime: event.target.value }); }
function toggle(item) { emit('save', { ...props.config, items: props.config.items.map(x => x.id === item.id ? { ...x, completed: !x.completed } : x) }); }
function remove(item) { emit('save', { ...props.config, items: props.config.items.filter(x => x.id !== item.id) }); }
function late(item) { const now = dateInZone(props.timezone); return item.enabled && !item.completed && item.remindAt && item.remindAt < now.date + 'T' + now.time; }
</script>
<template>
  <div class="dialog-heading"><div><p class="eyebrow">A LITTLE REMINDER</p><h2>事项与提醒</h2></div><button class="icon-button" aria-label="关闭" :disabled="busy" @click="emit('close')">×</button></div>
  <p class="field-help">通过 Server酱³ 推送到手机。所有时间按课表时区 {{ timezone }} 填写，关闭网页也会提醒。</p>
  <label class="check-label"><input id="course-reminders" type="checkbox" :checked="config.courseEnabled" :disabled="busy || !!draft" @change="changeCourse">课程开始前 30 分钟提醒</label>
  <label class="check-label"><input id="first-course-reminders" type="checkbox" :checked="config.firstCourseEnabled ?? true" :disabled="busy || !!draft" @change="changeFirst">每门课首次开课的前一周周五提醒</label>
  <label v-if="config.firstCourseEnabled ?? true" class="friday-time">周五提醒时间<input id="first-course-time" type="time" :value="config.firstCourseTime || '18:00'" :disabled="busy || !!draft" required @change="changeFriday"></label>
  <p v-if="lastDelivery" class="field-help">最近推送：{{ lastDelivery.title }}</p>
  <p class="form-error" role="alert">{{ error }}</p>
  <form v-if="draft" id="reminder-form" class="reminder-draft" @submit.prevent="saveItem">
    <h3>{{ config.items.some(x => x.id === draft.id) ? '编辑事项' : '添加事项' }}</h3>
    <div class="form-row"><label>类型<select v-model="draft.kind" name="kind"><option value="homework">作业</option><option value="exam">考试</option><option value="other">其他事项</option></select></label><label>名称<input v-model="draft.title" name="title" maxlength="120" required placeholder="例如：提交线性代数作业"></label></div>
    <label>事项时间（选填）<input v-model="draft.dueAt" name="dueAt" type="datetime-local"></label>
    <label>提醒时间<input v-model="draft.remindAt" name="remindAt" type="datetime-local" :required="draft.enabled && !draft.completed"></label>
    <p class="field-help">提醒时间可独立设置，例如考试前一天晚上、作业截止前两小时。服务中断后会在 24 小时内补发事项提醒。</p>
    <label>备注<textarea v-model="draft.notes" name="notes" maxlength="2000" rows="3" placeholder="考试地点、作业要求或相关链接"></textarea></label>
    <div class="reminder-checks"><label class="check-label"><input v-model="draft.enabled" type="checkbox">启用提醒</label><label class="check-label"><input v-model="draft.completed" type="checkbox">已完成</label></div>
    <div class="dialog-actions"><button type="button" class="secondary" :disabled="busy" @click="draft = null">返回列表</button><button class="primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存事项' }}</button></div>
  </form>
  <template v-else>
    <div class="section-heading"><h3>我的事项 · {{ config.items.length }}</h3><button id="add-reminder" class="text-button" :disabled="busy" @click="edit()">＋ 添加事项</button></div>
    <p v-if="!items.length" class="subtle">记下下一份作业、下一场考试，或任何需要提醒的事。</p>
    <article v-for="item in items" :key="item.id" class="reminder-item" :class="{ completed: item.completed }">
      <div class="reminder-info"><span class="eyebrow">{{ kindLabels[item.kind] }} · {{ item.completed ? '已完成' : item.enabled ? '提醒已启用' : '提醒已停用' }}</span><h3>{{ item.title }}</h3><p v-if="item.dueAt">事项时间 {{ item.dueAt.replace('T', ' ') }}</p><p v-if="item.remindAt">提醒 {{ item.remindAt.replace('T', ' ') }}<span v-if="late(item)"> · 时间已到</span></p><p v-if="item.notes" class="reminder-notes">{{ item.notes }}</p></div>
      <div class="reminder-actions"><button class="text-button" :disabled="busy" @click="edit(item)">编辑</button><button class="text-button" :disabled="busy" @click="toggle(item)">{{ item.completed ? '恢复待办' : '完成' }}</button><button class="text-button danger" :disabled="busy" @click="remove(item)">删除</button></div>
    </article>
    <div class="dialog-actions"><span></span><button class="secondary" :disabled="busy" @click="emit('close')">关闭</button></div>
  </template>
</template>

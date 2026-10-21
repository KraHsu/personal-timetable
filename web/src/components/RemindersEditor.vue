<script setup>
import { ref, watch } from 'vue';
import { reminderTimes } from '../reminders.mjs';
import ItemList from './ItemList.vue';
const props = defineProps(['config', 'timezone', 'busy', 'error', 'lastDelivery', 'initialItem']);
const emit = defineEmits(['save', 'close']);
const draft = ref(null);
watch(() => props.config, () => { draft.value = null; });
function edit(item) { draft.value = item ? { ...item, remindTimes: reminderTimes(item) } : { id: crypto.randomUUID(), title: '', kind: 'homework', dueAt: '', remindTimes: [''], notes: '', enabled: true, completed: false }; }
if (props.initialItem) { const current = props.config.items.find(x => x.id === props.initialItem.id); if (current) edit(current); }
function saveItem() {
  const config = JSON.parse(JSON.stringify(props.config));
  const item = { ...draft.value, title: draft.value.title.trim(), remindTimes: [...new Set(draft.value.remindTimes.filter(Boolean))].sort() };
  const index = config.items.findIndex(x => x.id === item.id);
  if (index < 0) config.items.push(item); else config.items[index] = item;
  emit('save', config);
}
function changeCourse(event) { emit('save', { ...props.config, courseEnabled: event.target.checked }); event.target.checked = props.config.courseEnabled; }
function changeFirst(event) { emit('save', { ...props.config, firstCourseEnabled: event.target.checked }); event.target.checked = props.config.firstCourseEnabled ?? true; }
function changeFriday(event) { if (event.target.value) emit('save', { ...props.config, firstCourseTime: event.target.value }); }
function toggle(item) { emit('save', { ...props.config, items: props.config.items.map(x => x.id === item.id ? { ...x, completed: !x.completed } : x) }); }
function remove(item) { emit('save', { ...props.config, items: props.config.items.filter(x => x.id !== item.id) }); }

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
    <div class="reminder-times-heading"><span>提醒时间 · {{ draft.remindTimes.length }}/20</span><button type="button" class="text-button" :disabled="draft.remindTimes.length >= 20 || busy" @click="draft.remindTimes.push('')">＋ 添加提醒时间</button></div>
    <div v-for="(_, index) in draft.remindTimes" :key="index" class="reminder-time-row"><label>第 {{ index + 1 }} 次提醒<input v-model="draft.remindTimes[index]" :name="'remindTime-' + index" type="datetime-local" :required="draft.enabled && !draft.completed"></label><button type="button" class="text-button danger" :disabled="busy" :aria-label="'移除第 ' + (index + 1) + ' 次提醒'" @click="draft.remindTimes.splice(index, 1)">移除</button></div>
    <p v-if="!draft.remindTimes.length" class="field-help">暂无提醒时间；启用提醒的待办事项至少需要一个时间。</p>
    <p class="field-help">一个事项最多可设 20 个提醒时间，例如考试前一周、前一天晚上和开考前两小时；完成后所有后续提醒都会停止。服务中断后会在 24 小时内补发事项提醒。</p>
    <label>备注<textarea v-model="draft.notes" name="notes" maxlength="2000" rows="3" placeholder="考试地点、作业要求或相关链接"></textarea></label>
    <div class="reminder-checks"><label class="check-label"><input v-model="draft.enabled" type="checkbox">启用提醒</label><label class="check-label"><input v-model="draft.completed" type="checkbox">已完成</label></div>
    <div class="dialog-actions"><button type="button" class="secondary" :disabled="busy" @click="draft = null">返回列表</button><button class="primary" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存事项' }}</button></div>
  </form>
  <template v-else>
    <div class="section-heading"><h3>我的事项 · {{ config.items.length }}</h3><button id="add-reminder" class="text-button" :disabled="busy" @click="edit()">＋ 添加事项</button></div>
    <ItemList :items="config.items" :busy="busy" @edit="edit" @toggle="toggle" @delete="remove" />
    <div class="dialog-actions"><span></span><button class="secondary" :disabled="busy" @click="emit('close')">关闭</button></div>
  </template>
</template>

<script setup>
import { reactive } from 'vue';
import { weekdays } from '../core.mjs';
const props = defineProps(['course', 'totalWeeks', 'busy', 'error']);
const emit = defineEmits(['save', 'delete', 'close']);
const session = () => ({ day: 1, start: '08:00', end: '09:35', weeks: `1-${props.totalWeeks}`, location: '' });
const draft = reactive(props.course ? JSON.parse(JSON.stringify(props.course)) : { id: '', name: '', location: '', teacher: '', notes: '', color: 'green', sessions: [session()] });
</script>
<template><form id="course-form" @submit.prevent="emit('save', draft)">
  <div class="dialog-heading"><div><p class="eyebrow">COURSE</p><h2>{{ course ? '编辑课程' : '添加课程' }}</h2></div><button type="button" class="icon-button" aria-label="关闭" @click="emit('close')">×</button></div>
  <label>课程名称<input v-model="draft.name" name="name" required maxlength="80" placeholder="例如：线性代数"></label>
  <div class="form-row"><label>上课地点<input v-model="draft.location" maxlength="120" placeholder="教学楼 / 教室 / 线上"></label><label>授课老师<input v-model="draft.teacher" maxlength="80" placeholder="选填"></label></div>
  <label>课程标记<select v-model="draft.color"><option value="green">草木绿</option><option value="blue">雾蓝</option><option value="mauve">浅紫</option><option value="peach">杏色</option><option value="rose">豆沙</option></select></label>
  <div class="section-heading"><h3>上课安排</h3><button type="button" class="text-button" :disabled="draft.sessions.length >= 30" @click="draft.sessions.push(session())">＋ 添加时段</button></div>
  <p class="field-help">同一门课可有多个时段，各自设置周次和地点；时间待定时可移除所有时段。</p>
  <div id="sessions"><div v-for="(s, i) in draft.sessions" :key="i" class="session"><div class="session-header"><span>上课时段</span><button type="button" class="remove-session" @click="draft.sessions.splice(i, 1)">移除</button></div>
    <div class="form-row three"><label>星期<select v-model.number="s.day"><option v-for="(day, n) in weekdays" :key="day" :value="n + 1">{{ day }}</option></select></label><label>开始时间<input v-model="s.start" type="time" required></label><label>结束时间<input v-model="s.end" type="time" required></label></div>
    <label>本时段地点<input v-model="s.location" maxlength="120" placeholder="留空沿用课程地点"></label><label>上课周次<input v-model="s.weeks" required maxlength="250" placeholder="1-8,10-16"></label>
    <div class="week-presets"><button v-for="(label, suffix) in { '': '每周', '单': '单周', '双': '双周' }" :key="suffix" type="button" @click="s.weeks = `1-${totalWeeks}${suffix}`">{{ label }}</button><span class="subtle" style="font-size:10px">可填写 1-8,10,12-16</span></div>
  </div></div>
  <label>备注<textarea v-model="draft.notes" rows="3" maxlength="2000" placeholder="教材、课程链接，或其他需要记住的事"></textarea></label><p class="form-error" role="alert">{{ error }}</p>
  <div class="dialog-actions"><button v-if="course" type="button" class="danger text-button" :disabled="busy" @click="emit('delete', course.id)">删除课程</button><div class="action-right"><button type="button" class="secondary" :disabled="busy" @click="emit('close')">取消</button><button type="submit" class="primary" :disabled="busy">{{ busy ? '保存中…' : '保存课程' }}</button></div></div>
</form></template>

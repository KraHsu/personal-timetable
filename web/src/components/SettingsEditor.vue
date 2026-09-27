<script setup>
import { reactive, ref } from 'vue';
const props = defineProps(['settings', 'error', 'busy']);
const emit = defineEmits(['save', 'close', 'export', 'import']);
const draft = reactive({ ...props.settings });
const file = ref();
function importFile(event) { const selected = event.target.files[0]; if (selected) emit('import', selected); event.target.value = ''; }
</script>
<template><form id="settings-form" @submit.prevent="emit('save', draft)"><div class="dialog-heading"><div><p class="eyebrow">SEMESTER</p><h2>学期设置</h2></div><button type="button" class="icon-button" aria-label="关闭" @click="emit('close')">×</button></div>
  <label>学期名称<input v-model="draft.title" maxlength="80" required placeholder="例如：2026 · 秋季学期"></label><div class="form-row"><label>第一周的周一<input v-model="draft.startDate" type="date" required></label><label>学期周数<input v-model.number="draft.totalWeeks" type="number" min="1" max="60" required></label></div>
  <label>课表时区<select v-model="draft.timezone"><option value="Asia/Shanghai">中国标准时间 · UTC+8</option><option value="America/Los_Angeles">美国洛杉矶</option><option value="Europe/London">英国伦敦</option><option value="Asia/Tokyo">日本东京</option><option value="UTC">UTC</option></select></label><p class="field-help">当前周和下一节课始终按课表时区计算。</p>
  <div class="form-row"><label>课表起始时间<input v-model="draft.dayStart" type="time" required></label><label>课表结束时间<input v-model="draft.dayEnd" type="time" required></label></div><p class="field-help">超出显示时间的课程会自动扩展课表，不会隐藏。</p><p class="form-error" role="alert">{{ error }}</p>
  <div class="dialog-actions"><button type="button" class="secondary" :disabled="busy" @click="emit('close')">取消</button><button type="submit" class="primary" :disabled="busy">{{ busy ? '保存中…' : '保存设置' }}</button></div>
  <div class="backup"><span>课表备份</span><button type="button" class="text-button" @click="emit('export')">导出 JSON ↗</button><button type="button" class="text-button" :disabled="busy" @click="file.click()">导入备份 ↗</button><input ref="file" type="file" accept="application/json,.json" hidden @change="importFile"></div>
</form></template>

<script setup>
import { computed, ref } from 'vue';
import { reminderTimes } from '../reminders.mjs';
const props = defineProps(['items', 'busy']);
const emit = defineEmits(['edit', 'toggle', 'delete']);
const filter = ref('all'), search = ref('');
const labels = { homework: '作业', exam: '考试', other: '事项' };
const counts = computed(() => ({ all: props.items.length, pending: props.items.filter(x => !x.completed).length, completed: props.items.filter(x => x.completed).length }));
const visible = computed(() => props.items.filter(x => (filter.value === 'all' || x.completed === (filter.value === 'completed')) && `${x.title} ${x.notes} ${labels[x.kind]}`.toLowerCase().includes(search.value.trim().toLowerCase())).sort((a,b) => Number(a.completed) - Number(b.completed) || (a.dueAt || reminderTimes(a)[0] || '9999').localeCompare(b.dueAt || reminderTimes(b)[0] || '9999')));
function dateLabel(value) { const [date, time] = value.split('T'); return date.replaceAll('-', '/') + '  ' + time; }
</script>
<template>
  <div class="item-list-tools">
    <div class="item-filters" aria-label="筛选事项"><button v-for="(label, key) in { all: '全部', pending: '待办', completed: '已完成' }" :key="key" :aria-pressed="filter === key" @click="filter = key">{{ label }}<span>{{ counts[key] }}</span></button></div>
    <div class="item-search"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg><input v-model="search" type="search" aria-label="搜索事项" placeholder="搜索名称、备注…"></div>
  </div>
  <div v-if="!visible.length" class="items-empty"><span class="items-empty-mark" aria-hidden="true">{{ items.length ? '⌕' : '✓' }}</span><h3>{{ items.length ? '没有找到这件事' : '暂时没有待记录的事' }}</h3><p>{{ items.length ? '没有符合条件的事项，试试其他关键词或筛选。' : '下一份作业、下一场考试，都可以记在这里。' }}</p></div>
  <div v-else class="item-cards">
    <article v-for="item in visible" :key="item.id" class="reminder-item" :class="[item.kind, { completed: item.completed }]" :data-item-id="item.id">
      <div class="reminder-info">
        <div class="item-card-top"><span class="item-kind"><i></i>{{ labels[item.kind] }}</span><span class="item-state">{{ item.completed ? '已完成 · 不再提醒' : item.enabled ? '提醒已启用' : '提醒已停用' }}</span></div>
        <h3>{{ item.title }}</h3>
        <p v-if="item.dueAt" class="item-due"><span>事项时间</span><time :datetime="item.dueAt">{{ dateLabel(item.dueAt) }}</time></p>
        <p v-if="item.notes" class="reminder-notes">{{ item.notes }}</p>
        <div v-if="reminderTimes(item).length" class="item-reminders"><div class="item-reminder-label"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span>{{ reminderTimes(item).length }} 次提醒</span></div><ul class="item-reminder-times"><li v-for="time in reminderTimes(item).slice(0, 2)" :key="time"><time :datetime="time">{{ dateLabel(time) }}</time></li></ul><details v-if="reminderTimes(item).length > 2" class="more-reminders"><summary>其余 {{ reminderTimes(item).length - 2 }} 次提醒</summary><ul class="item-reminder-times"><li v-for="time in reminderTimes(item).slice(2)" :key="time"><time :datetime="time">{{ dateLabel(time) }}</time></li></ul></details></div>
        <p v-else class="item-no-reminder">未设置提醒时间</p>
      </div>
      <div class="reminder-actions"><button class="text-button item-edit" :disabled="busy" @click="emit('edit', item)">编辑</button><button class="item-complete" :disabled="busy" @click="emit('toggle', item)">{{ item.completed ? '恢复待办' : '完成' }}</button><button class="text-button item-delete" :disabled="busy" @click="emit('delete', item)">删除</button></div>
    </article>
  </div>
</template>

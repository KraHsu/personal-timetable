<script setup>
import { computed, ref } from 'vue';
import { reminderTimes } from '../reminders.mjs';
const props = defineProps(['items', 'busy']);
const emit = defineEmits(['edit', 'toggle', 'delete']);
const filter = ref('all'), search = ref('');
const labels = { homework: '作业', exam: '考试', other: '事项' };
const counts = computed(() => ({ all: props.items.length, pending: props.items.filter(x => !x.completed).length, completed: props.items.filter(x => x.completed).length }));
const visible = computed(() => props.items.filter(x => (filter.value === 'all' || x.completed === (filter.value === 'completed')) && `${x.title} ${x.notes} ${labels[x.kind]}`.toLowerCase().includes(search.value.trim().toLowerCase())).sort((a,b) => Number(a.completed) - Number(b.completed) || (a.dueAt || reminderTimes(a)[0] || '9999').localeCompare(b.dueAt || reminderTimes(b)[0] || '9999')));
</script>
<template>
  <div class="item-list-tools"><div class="view-switch" aria-label="筛选事项"><button v-for="(label, key) in { all: '全部', pending: '待办', completed: '已完成' }" :key="key" :aria-pressed="filter === key" @click="filter = key">{{ label }} {{ counts[key] }}</button></div><input v-model="search" type="search" aria-label="搜索事项" placeholder="搜索事项"></div>
  <p v-if="!visible.length" class="subtle">{{ items.length ? '没有符合条件的事项。' : '还没有事项，添加下一份作业、考试或其他安排。' }}</p>
  <article v-for="item in visible" :key="item.id" class="reminder-item" :class="{ completed: item.completed }" :data-item-id="item.id">
    <div class="reminder-info"><span class="eyebrow">{{ labels[item.kind] }} · {{ item.completed ? '已完成 · 不再提醒' : item.enabled ? '提醒已启用' : '提醒已停用' }}</span><h3>{{ item.title }}</h3><p v-if="item.dueAt">事项时间 {{ item.dueAt.replace('T', ' ') }}</p><p v-if="reminderTimes(item).length">{{ reminderTimes(item).length }} 次提醒</p><ul v-if="reminderTimes(item).length" class="item-reminder-times"><li v-for="time in reminderTimes(item)" :key="time"><time>{{ time.replace('T', ' ') }}</time></li></ul><p v-if="item.notes" class="reminder-notes">{{ item.notes }}</p></div>
    <div class="reminder-actions"><button class="text-button" :disabled="busy" @click="emit('edit', item)">编辑</button><button class="text-button" :disabled="busy" @click="emit('toggle', item)">{{ item.completed ? '恢复待办' : '完成' }}</button><button class="text-button danger" :disabled="busy" @click="emit('delete', item)">删除</button></div>
  </article>
</template>

<script setup>
import { computed } from 'vue';
import { minutes, addDays, weekdays, lanes } from '../core.mjs';
const props = defineProps(['data', 'items', 'start', 'now', 'view']);
defineEmits(['detail', 'add']);
const low = computed(() => Math.floor(Math.min(minutes(props.data.settings.dayStart), ...props.items.map(x => minutes(x.start))) / 60) * 60);
const high = computed(() => Math.ceil(Math.max(minutes(props.data.settings.dayEnd), ...props.items.map(x => minutes(x.end))) / 60) * 60);
const height = computed(() => (high.value - low.value) / 60 * 64);
const hours = computed(() => Array.from({ length: (high.value - low.value) / 60 }, (_, i) => low.value + i * 60));
const days = computed(() => weekdays.map((label, i) => ({ label, date: addDays(props.start, i), items: lanes(props.items.filter(x => x.day === i + 1)) })));
const y = time => (minutes(time) - low.value) / 60 * 64;
const block = x => ({ '--course-color': `var(--${x.course.color})`, top: y(x.start) + 'px', height: Math.max(y(x.end) - y(x.start) - 3, 12) + 'px', left: `calc(${x.lane / x.laneCount * 100}% + 4px)`, width: `calc(${100 / x.laneCount}% - 8px)` });
</script>
<template>
  <div v-if="!data.courses.length" class="empty-state"><div class="empty-symbol">⌁</div><h3>这一页，留给新的学期。</h3><p>设置学期起始日期，再添上你的第一门课。</p><button class="secondary" @click="$emit('add')">＋ 添加第一门课</button></div>
  <div v-else-if="!items.length" class="empty-state"><div class="empty-symbol">—</div><h3>这周，暂时没有课。</h3><p>换一周看看，或留一点时间给自己。</p></div>
  <div v-else-if="view === 'week'" class="grid-scroll" tabindex="0" aria-label="一周课表，可左右滚动"><div class="week-grid">
    <div class="day-head"></div><div v-for="day in days" :key="day.date" class="day-head" :class="{ 'is-today': day.date === now.date }"><span>{{ day.label }}</span><span class="day-number">{{ day.date.slice(8) }}</span></div>
    <div class="time-axis" :style="{ height: height + 'px' }"><span v-for="t in hours" :key="t" class="hour-label" :style="{ top: (t - low) / 60 * 64 + 'px' }">{{ String(t / 60).padStart(2, '0') }}:00</span></div>
    <div v-for="day in days" :key="day.date" class="day-column" :class="{ 'is-today': day.date === now.date }" :style="{ height: height + 'px' }">
      <button v-for="(x, i) in day.items" :key="x.course.id + '-' + i" class="course-block" :class="{ compact: y(x.end) - y(x.start) < 45 }" :style="block(x)" :aria-label="`${x.course.name}，${day.label} ${x.start}至${x.end}，${x.location}`" @click="$emit('detail', x.course)"><span class="block-time">{{ x.start }}–{{ x.end }}</span><strong>{{ x.course.name }}</strong><span>{{ x.location }}</span></button>
      <div v-if="day.date === now.date && minutes(now.time) >= low && minutes(now.time) < high" class="now-line" :style="{ top: y(now.time) + 'px' }"></div>
    </div>
  </div></div>
  <template v-else><div v-for="day in days" :key="day.date" class="agenda-day"><div class="agenda-date" :class="{ today: day.date === now.date }">{{ day.label }}{{ day.date === now.date ? ' · 今' : '' }}<span>{{ day.date.slice(5).replace('-', ' / ') }}</span></div><div>
    <button v-for="(x, i) in day.items" :key="x.course.id + '-' + i" class="agenda-item" :style="{ '--course-color': `var(--${x.course.color})` }" @click="$emit('detail', x.course)"><time>{{ x.start }}<br>{{ x.end }}</time><span class="agenda-info"><strong>{{ x.course.name }}</strong><small>{{ [x.location, x.course.teacher].filter(Boolean).join(' · ') || '未填写地点' }}</small></span><span>↗</span></button><p v-if="!day.items.length" class="agenda-empty">没有课，留白也是安排。</p>
  </div></div></template>
</template>

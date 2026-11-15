<script setup>
import { computed, useId } from 'vue';
import { graphLayout, taskState, taskStateLabels } from '../reminders.mjs';
const props = defineProps(['items', 'visibleIds', 'busy']);
const emit = defineEmits(['edit']);
const marker = `arrow-${useId()}`;
const layout = computed(() => graphLayout(props.items, props.visibleIds));
function path(edge) {
  const x = edge.from.x + 220, y = edge.from.y + 44, endX = edge.to.x, endY = edge.to.y + 44;
  if (endX - x > 60) return `M ${x} ${y} L ${x + 20} ${y} L ${x + 20} 10 L ${endX - 20} 10 L ${endX - 20} ${endY} L ${endX} ${endY}`;
  return `M ${x} ${y} C ${x + 30} ${y}, ${endX - 30} ${endY}, ${endX} ${endY}`;
}
</script>
<template>
  <div class="task-graph-help"><p>箭头从前置任务指向后续任务。点击任务可编辑依赖；横向滚动查看完整关系。</p><p>筛选后仍显示相关前置任务，以虚线边框标记。</p></div>
  <div class="task-graph" tabindex="0" aria-label="任务依赖图，可滚动">
    <div class="task-graph-stage" :style="{ width: layout.width + 'px', height: layout.height + 'px' }">
      <svg :width="layout.width" :height="layout.height" aria-hidden="true">
        <defs><marker :id="marker" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
        <path v-for="edge in layout.edges" :key="JSON.stringify([edge.from.item.id, edge.to.item.id])" :d="path(edge)" fill="none" stroke="currentColor" stroke-width="1.5" :marker-end="`url(#${marker})`" />
      </svg>
      <button v-for="node in layout.nodes" :key="node.item.id" class="task-node" :class="[taskState(node.item, items), { context: node.context }]" :style="{ left: node.x + 'px', top: node.y + 'px' }" :disabled="busy" :data-task-id="node.item.id" :aria-label="`${node.item.title}，${taskStateLabels[taskState(node.item, items)]}，编辑任务`" @click="emit('edit', node.item)">
        <span>{{ taskStateLabels[taskState(node.item, items)] }}<small v-if="node.context"> · 前置任务</small></span><strong :title="node.item.title">{{ node.item.title }}</strong>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue';
import { connectTasks, graphLayout, reminderTimes, removeTask, saveGraphTask, taskNodeHeight, taskNodeWidth, taskState, taskStateLabels, wouldCycle } from '../reminders.mjs';
const props = defineProps(['items', 'lists', 'visibleIds', 'busy', 'revision', 'saveGraph', 'error', 'defaultListId']);
const emit = defineEmits(['reveal']);
const clone = value => JSON.parse(JSON.stringify(value));
const marker = `arrow-${useId()}`;
const viewport = ref(null), zoom = ref(1), expanded = ref(false);
const draft = ref(null), original = ref(''), baseItems = ref([]), baseRevision = ref(0), relation = ref(null);
const selectedEdge = ref(null), connecting = ref(false), sourceId = ref(''), localError = ref(''), notice = ref(''), dependencyId = ref('');
const dirty = computed(() => draft.value && JSON.stringify(draft.value) !== original.value);
const isNew = computed(() => draft.value && !baseItems.value.some(x => x.id === draft.value.id));
const layout = computed(() => graphLayout(props.items, props.visibleIds));
const selection = computed(() => draft.value?.id ?? '');
const selectedIds = computed(() => {
  const ids = new Set([selection.value, sourceId.value]);
  if (selectedEdge.value) { ids.add(selectedEdge.value.from); ids.add(selectedEdge.value.to); }
  for (const edge of layout.value.edges) if (edge.from.item.id === selection.value || edge.to.item.id === selection.value) { ids.add(edge.from.item.id); ids.add(edge.to.item.id); }
  return ids;
});
const candidates = computed(() => draft.value ? baseItems.value.filter(x => x.id !== draft.value.id && !draft.value.dependsOn.includes(x.id) && !wouldCycle(baseItems.value, draft.value.id, x.id)) : []);
const taskName = id => props.items.find(x => x.id === id)?.title ?? baseItems.value.find(x => x.id === id)?.title ?? '已删除的任务';
function canLeave() { return !props.busy && (!dirty.value || confirm('放弃尚未保存的任务修改？')); }
defineExpose({ canLeave });
function resetSelection() { draft.value = null; relation.value = null; selectedEdge.value = null; connecting.value = false; sourceId.value = ''; localError.value = ''; dependencyId.value = ''; }
function capture() { baseItems.value = clone(props.items); baseRevision.value = props.revision; }
function setDraft(item) {
  draft.value = { ...clone(item), dependsOn: [...(item.dependsOn ?? [])], remindTimes: reminderTimes(item), listId: item.listId ?? '' };
  original.value = JSON.stringify(draft.value);
}
function revealInspector() {
  nextTick(() => {
    const workspace = viewport.value?.closest('.task-workspace');
    if (workspace?.clientWidth < 800) workspace.querySelector('.graph-inspector')?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
  });
}
function openTask(item) {
  if (connecting.value) { chooseConnection(item.id); return; }
  if (!canLeave()) return;
  resetSelection(); capture(); setDraft(item); revealInspector();
}
function createTask(direction = null, relative = null) {
  if (!canLeave()) return;
  resetSelection(); capture();
  relation.value = relative ? { id: relative.id, direction } : null;
  setDraft({ id: crypto.randomUUID(), title: '', kind: 'other', listId: relative?.listId ?? props.defaultListId ?? '', dependsOn: [], completed: false, enabled: false, dueAt: '', remindTimes: [], notes: '' });
  nextTick(() => viewport.value?.closest('.task-workspace')?.querySelector('[name="graphTitle"]')?.focus());
}
async function persist(items, revision = props.revision) {
  if (props.busy) return false;
  localError.value = ''; notice.value = '';
  try { return Boolean(await props.saveGraph({ items, revision })); }
  catch (error) { localError.value = error.message; return false; }
}
async function saveTask() {
  if (props.busy) return;
  const item = { ...clone(draft.value), title: draft.value.title.trim(), remindTimes: [...new Set(draft.value.remindTimes.filter(Boolean))].sort() };
  if (!item.title) { localError.value = '请填写任务名称'; return; }
  if (item.enabled && !item.completed && !item.remindTimes.length) { localError.value = '启用提醒时，至少设置一个提醒时间'; return; }
  try {
    const items = saveGraphTask(baseItems.value, item, relation.value);
    if (await persist(items, baseRevision.value)) {
      resetSelection(); emit('reveal'); notice.value = '任务已保存';
    }
  } catch (error) { localError.value = error.message; }
}
async function toggle(item) {
  if (!canLeave()) return;
  if (await persist(props.items.map(x => x.id === item.id ? { ...x, completed: !x.completed } : x))) { resetSelection(); notice.value = item.completed ? '已恢复待办' : '任务已完成'; }
}
async function removeSelected() {
  if (props.busy || !draft.value || !confirm(`删除「${draft.value.title}」？相关依赖连线也会移除。`)) return;
  if (await persist(removeTask({ items: baseItems.value }, draft.value.id).items, baseRevision.value)) { resetSelection(); notice.value = '任务及相关连线已删除'; }
}
function startConnection(id = '') {
  if (!canLeave()) return;
  resetSelection(); connecting.value = true; sourceId.value = id;
}
async function chooseConnection(id) {
  if (props.busy) return;
  if (!sourceId.value) { sourceId.value = id; return; }
  try {
    const items = connectTasks(props.items, sourceId.value, id);
    if (await persist(items)) { resetSelection(); notice.value = '依赖连线已添加'; }
  } catch (error) { localError.value = error.message; }
}
function selectEdge(edge) {
  if (!canLeave()) return;
  resetSelection(); capture(); selectedEdge.value = { from: edge.from.item.id, to: edge.to.item.id }; revealInspector();
}
async function removeEdge() {
  if (props.busy || !selectedEdge.value) return;
  const { from, to } = selectedEdge.value;
  const items = baseItems.value.map(x => x.id === to ? { ...x, dependsOn: (x.dependsOn ?? []).filter(id => id !== from) } : x);
  if (await persist(items, baseRevision.value)) { resetSelection(); notice.value = '连线已移除，两个任务均保留'; }
}
function edgeSelected(edge) { return selectedEdge.value?.from === edge.from.item.id && selectedEdge.value?.to === edge.to.item.id; }
function path(edge) {
  const x = edge.from.x + taskNodeWidth, y = edge.from.y + taskNodeHeight / 2, endX = edge.to.x, endY = edge.to.y + taskNodeHeight / 2;
  if (endX - x > 80) return `M ${x} ${y} L ${x + 24} ${y} L ${x + 24} 16 L ${endX - 24} 16 L ${endX - 24} ${endY} L ${endX} ${endY}`;
  return `M ${x} ${y} C ${x + 40} ${y}, ${endX - 40} ${endY}, ${endX} ${endY}`;
}
async function setZoom(value) {
  const el = viewport.value, previous = zoom.value;
  const center = el ? { x: (el.scrollLeft + el.clientWidth / 2) / previous, y: (el.scrollTop + el.clientHeight / 2) / previous } : null;
  zoom.value = Math.max(.25, Math.min(1.5, value)); await nextTick();
  if (el && center) { el.scrollLeft = center.x * zoom.value - el.clientWidth / 2; el.scrollTop = center.y * zoom.value - el.clientHeight / 2; }
}
async function fit() {
  const el = viewport.value; if (!el) return;
  await setZoom(Math.min(1, (el.clientWidth - 20) / layout.value.width, (el.clientHeight - 20) / layout.value.height));
  el.scrollLeft = 0; el.scrollTop = 0;
}
let pan = null;
function panStart(event) {
  if (event.pointerType === 'touch' || event.button !== 0 || event.target.closest('button, .task-node, .graph-edge')) return;
  const el = viewport.value; pan = { x: event.clientX, y: event.clientY, left: el.scrollLeft, top: el.scrollTop };
  el.setPointerCapture(event.pointerId);
}
function panMove(event) { if (pan) { viewport.value.scrollLeft = pan.left - event.clientX + pan.x; viewport.value.scrollTop = pan.top - event.clientY + pan.y; } }
function endPan() { pan = null; }
function beforeUnload(event) { if (dirty.value) { event.preventDefault(); event.returnValue = ''; } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload));
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));
</script>
<template>
  <section class="task-workspace" :class="{ expanded }" aria-label="交互任务图">
    <div class="graph-toolbar">
      <div><button class="primary" :disabled="busy || items.length >= 300" @click="createTask()">＋ 添加任务</button><button class="secondary" :disabled="busy || items.length < 2" :aria-pressed="connecting" @click="connecting ? resetSelection() : startConnection()">{{ connecting ? '取消连线' : '连接任务' }}</button></div>
      <div class="graph-zoom"><button class="icon-button" aria-label="缩小任务图" :disabled="zoom <= .25" @click="setZoom(zoom - .15)">−</button><output aria-label="任务图缩放比例">{{ Math.round(zoom * 100) }}%</output><button class="icon-button" aria-label="放大任务图" :disabled="zoom >= 1.5" @click="setZoom(zoom + .15)">＋</button><button class="text-button" @click="fit">适合画布</button><button class="text-button" :aria-pressed="expanded" @click="expanded = !expanded">{{ expanded ? '收起画布' : '展开画布' }}</button></div>
    </div>
    <p class="graph-instruction" role="status">{{ connecting ? sourceId ? `已选前置任务「${taskName(sourceId)}」，点击后续任务完成连线。` : '先点击前置任务，再点击后续任务。' : '箭头表示前置 → 后续。点选节点编辑，点选连线删除；拖动画布空白处可平移。' }}</p>
    <p v-if="localError || error" class="form-error graph-error" role="alert">{{ localError || error }}</p><p v-if="notice" class="graph-notice" role="status">{{ notice }}</p>
    <div class="graph-work-area" :class="{ 'has-inspector': draft || selectedEdge }">
      <div ref="viewport" class="task-graph" :class="{ connecting }" tabindex="0" aria-label="任务依赖图，可滚动" @pointerdown="panStart" @pointermove="panMove" @pointerup="endPan" @pointercancel="endPan" @lostpointercapture="endPan" @keydown.esc="connecting && resetSelection()">
        <div v-if="!layout.nodes.length" class="graph-empty"><h3>{{ items.length ? '没有符合筛选条件的任务' : '从第一件事开始' }}</h3><p>添加任务，再用连线安排先后关系。</p><button class="secondary" :disabled="busy || items.length >= 300" @click="createTask()">添加任务</button></div>
        <div v-else class="graph-scaled-area" :style="{ width: layout.width * zoom + 'px', height: layout.height * zoom + 'px' }">
          <div class="task-graph-stage" :style="{ width: layout.width + 'px', height: layout.height + 'px', transform: `scale(${zoom})` }">
            <svg :width="layout.width" :height="layout.height" aria-label="任务依赖连线">
              <defs><marker :id="marker" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker></defs>
              <g v-for="edge in layout.edges" :key="JSON.stringify([edge.from.item.id, edge.to.item.id])" class="graph-edge" :class="{ selected: edgeSelected(edge), related: edge.from.item.id === selection || edge.to.item.id === selection }" role="button" :tabindex="busy ? -1 : 0" :aria-disabled="busy" :aria-label="`连线：${edge.from.item.title} → ${edge.to.item.title}`" @click.stop="selectEdge(edge)" @keydown.enter.prevent="selectEdge(edge)" @keydown.space.prevent="selectEdge(edge)">
                <path class="graph-edge-line" :d="path(edge)" fill="none" stroke="currentColor" stroke-width="1.6" :marker-end="`url(#${marker})`" /><path class="graph-edge-hit" :d="path(edge)" fill="none" stroke="transparent" stroke-width="18" />
              </g>
            </svg>
            <article v-for="node in layout.nodes" :key="node.item.id" class="task-node" :class="[taskState(node.item, items), { context: node.context, selected: selection === node.item.id || sourceId === node.item.id, dimmed: (selection || selectedEdge) && !selectedIds.has(node.item.id) }]" :style="{ left: node.x + 'px', top: node.y + 'px', width: taskNodeWidth + 'px', height: taskNodeHeight + 'px' }" :data-task-id="node.item.id" @click="openTask(node.item)">
              <div class="graph-node-top"><span>{{ taskStateLabels[taskState(node.item, items)] }}</span><button class="graph-complete" :disabled="busy || connecting" :aria-label="`${node.item.completed ? '恢复' : '完成'}「${node.item.title}」`" :aria-pressed="node.item.completed" @click.stop="toggle(node.item)">{{ node.item.completed ? '✓' : '○' }}</button></div>
              <button class="graph-node-title" :disabled="busy" :title="node.item.title" :aria-label="`编辑任务：${node.item.title}`" @click.stop="openTask(node.item)">{{ node.item.title }}</button>
              <div class="graph-node-footer"><small>{{ lists.find(x => x.id === node.item.listId)?.name || '收集箱' }}{{ node.context ? ' · 前置任务' : '' }}</small><button :disabled="busy || connecting || items.length >= 300" :aria-label="`为「${node.item.title}」添加后续任务`" @click.stop="createTask('after', node.item)">＋ 后续</button></div>
              <button class="graph-port" :disabled="busy" :aria-label="`从「${node.item.title}」开始连线`" @click.stop="startConnection(node.item.id)">＋</button>
            </article>
          </div>
        </div>
      </div>
      <aside v-if="draft" class="graph-inspector" aria-label="图中任务编辑">
        <div class="graph-inspector-heading"><h3>{{ isNew ? '添加任务' : '编辑任务' }}</h3><button class="icon-button" aria-label="关闭任务编辑" :disabled="busy" @click="canLeave() && resetSelection()">×</button></div>
        <p v-if="relation" class="field-help">{{ relation.direction === 'before' ? '此任务将成为' : '此任务将在' }}「{{ taskName(relation.id) }}」{{ relation.direction === 'before' ? '的前置任务。' : '之后进行。' }}</p>
        <p v-if="baseRevision !== revision" class="graph-stale" role="status">事项已被更新。当前草稿仍保留，保存时会检查版本；重新选择任务可载入最新内容。</p>
        <form class="graph-task-form" @submit.prevent="saveTask"><fieldset :disabled="busy">
          <label>任务名称<input v-model="draft.title" name="graphTitle" maxlength="120" required></label>
          <div class="form-row"><label>所属清单<select v-model="draft.listId" name="graphList"><option value="">收集箱</option><option v-for="list in lists" :key="list.id" :value="list.id">{{ list.name }}</option></select></label><label>类型<select v-model="draft.kind" name="graphKind"><option value="homework">作业</option><option value="exam">考试</option><option value="other">其他事项</option></select></label></div>
          <label>事项时间（选填）<input v-model="draft.dueAt" name="graphDueAt" type="datetime-local"></label>
          <label>备注<textarea v-model="draft.notes" name="graphNotes" rows="3" maxlength="2000"></textarea></label>
          <div class="graph-prerequisites"><p>前置任务</p><ul><li v-for="id in draft.dependsOn" :key="id"><span>{{ taskName(id) }}</span><button type="button" class="text-button danger" :aria-label="`移除前置任务：${taskName(id)}`" @click="draft.dependsOn = draft.dependsOn.filter(x => x !== id)">移除</button></li></ul><label>添加前置任务<select v-model="dependencyId" aria-label="添加前置任务" @change="dependencyId && draft.dependsOn.push(dependencyId); dependencyId = ''"><option value="">选择任务…</option><option v-for="item in candidates" :key="item.id" :value="item.id">{{ item.title }}</option></select></label></div>
          <label class="check-label"><input v-model="draft.completed" name="graphCompleted" type="checkbox">已完成</label>
          <details class="graph-reminders"><summary>提醒设置 · {{ draft.enabled ? '已启用' : '未启用' }}</summary><label class="check-label"><input v-model="draft.enabled" name="graphEnabled" type="checkbox">启用提醒</label><div v-for="(_, index) in draft.remindTimes" :key="index" class="graph-reminder-row"><label>提醒 {{ index + 1 }}<input v-model="draft.remindTimes[index]" type="datetime-local" :required="draft.enabled && !draft.completed"></label><button type="button" class="text-button danger" :aria-label="`移除图中第 ${index + 1} 次提醒`" @click="draft.remindTimes.splice(index, 1)">移除</button></div><button type="button" class="text-button" :disabled="draft.remindTimes.length >= 20" @click="draft.remindTimes.push('')">＋ 添加提醒时间</button></details>
          <button type="submit" class="primary graph-save">{{ busy ? '保存中…' : '保存任务' }}</button>
        </fieldset></form>
        <div v-if="!isNew" class="graph-inspector-actions"><button class="secondary" :disabled="busy || items.length >= 300" @click="createTask('before', draft)">＋ 前置任务</button><button class="secondary" :disabled="busy || items.length >= 300" @click="createTask('after', draft)">＋ 后续任务</button><button class="text-button danger" :disabled="busy" @click="removeSelected">删除任务</button></div>
      </aside>
      <aside v-else-if="selectedEdge" class="graph-inspector" aria-label="连线管理"><div class="graph-inspector-heading"><h3>依赖关系</h3><button class="icon-button" aria-label="关闭连线管理" :disabled="busy" @click="resetSelection">×</button></div><p class="graph-edge-description">{{ taskName(selectedEdge.from) }}<span>↓</span>{{ taskName(selectedEdge.to) }}</p><p class="field-help">移除连线会解除先后关系，保留两个任务。</p><button class="secondary danger" :disabled="busy" @click="removeEdge">移除连线</button></aside>
    </div>
    <p class="task-graph-help">筛选后仍显示相关前置任务，以虚线边框标记。任务和连线仅在保存成功后更新。</p>
  </section>
</template>

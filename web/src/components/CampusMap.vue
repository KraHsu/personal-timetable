<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import mapImage from '../assets/campus-map.webp';
import mapPdf from '../assets/campus-map.pdf';

defineEmits(['close']);
const viewport = ref(null), zoom = ref(1), loaded = ref(false), failed = ref(false);
const size = ref({ width: 1, height: 1 });
const ratio = 4800 / 3401;
const fittedWidth = computed(() => Math.min(size.value.width, size.value.height * ratio));
const imageWidth = computed(() => fittedWidth.value * zoom.value);
const maxZoom = computed(() => Math.max(1, 4800 / fittedWidth.value));
let observer, drag;

async function setZoom(value) {
  const el = viewport.value;
  const oldWidth = imageWidth.value, oldHeight = oldWidth / ratio;
  const centerX = (el.scrollLeft + size.value.width / 2 - Math.max(0, (size.value.width - oldWidth) / 2)) / oldWidth;
  const centerY = (el.scrollTop + size.value.height / 2 - Math.max(0, (size.value.height - oldHeight) / 2)) / oldHeight;
  zoom.value = Math.max(1, Math.min(maxZoom.value, value));
  await nextTick();
  el.scrollLeft = centerX * imageWidth.value + Math.max(0, (size.value.width - imageWidth.value) / 2) - size.value.width / 2;
  el.scrollTop = centerY * imageWidth.value / ratio + Math.max(0, (size.value.height - imageWidth.value / ratio) / 2) - size.value.height / 2;
}
function startDrag(event) {
  if (event.pointerType !== 'mouse' || event.button !== 0 || zoom.value === 1) return;
  const el = viewport.value;
  drag = { x: event.clientX, y: event.clientY, left: el.scrollLeft, top: el.scrollTop };
  el.setPointerCapture(event.pointerId);
}
function moveDrag(event) {
  if (!drag) return;
  viewport.value.scrollLeft = drag.left - event.clientX + drag.x;
  viewport.value.scrollTop = drag.top - event.clientY + drag.y;
}
function endDrag() { drag = null; }
onMounted(() => {
  observer = new ResizeObserver(() => {
    size.value = { width: viewport.value.clientWidth, height: viewport.value.clientHeight };
    zoom.value = Math.min(zoom.value, maxZoom.value);
  });
  observer.observe(viewport.value);
});
onUnmounted(() => observer?.disconnect());
</script>

<template>
  <div class="dialog-heading map-heading">
    <div><p class="eyebrow">CAMPUS MAP</p><h2>中关村校区地图</h2><p class="map-subtitle">北京理工大学 · 查找教学楼与上课地点</p></div>
    <button class="icon-button" aria-label="关闭地图" @click="$emit('close')">×</button>
  </div>
  <div class="map-tools">
    <div class="map-zoom" aria-label="地图缩放">
      <button class="icon-button" aria-label="缩小地图" :disabled="zoom <= 1" @click="setZoom(zoom / 1.5)">−</button>
      <output aria-live="polite">{{ Math.round(zoom * 100) }}%</output>
      <button class="icon-button" aria-label="放大地图" :disabled="zoom >= maxZoom" @click="setZoom(zoom * 1.5)">＋</button>
      <button class="text-button" @click="setZoom(1)">全图</button>
    </div>
    <a class="text-button" :href="mapPdf" target="_blank" rel="noopener noreferrer">打开原始 PDF ↗</a>
  </div>
  <p id="map-help" class="map-help">放大后拖动或滑动查看；也可聚焦地图后用方向键移动。</p>
  <div ref="viewport" class="map-viewport" :class="{ zoomed: zoom > 1 }" tabindex="0" role="region" aria-label="校园地图，可滚动查看" aria-describedby="map-help" @pointerdown="startDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="endDrag" @lostpointercapture="endDrag">
    <div v-if="!loaded || failed" class="map-status" role="status">{{ failed ? '地图暂时未能加载，请打开原始 PDF 查看。' : '正在展开校园地图…' }}</div>
    <div class="map-stage" :style="{ width: Math.max(size.width, imageWidth) + 'px', height: Math.max(size.height, imageWidth / ratio) + 'px' }">
      <img :src="mapImage" alt="北京理工大学中关村校区平面示意图，包含教学楼、学生公寓、校门和道路" :style="{ width: imageWidth + 'px' }" :class="{ pending: !loaded || failed }" draggable="false" decoding="async" @load="loaded = true" @error="failed = true">
    </div>
  </div>
</template>

<style scoped>
.map-heading { margin-bottom: 16px; }
.map-subtitle { margin: 7px 0 0; color: var(--muted); font-size: 12px; }
.map-tools, .map-zoom { display: flex; align-items: center; gap: 12px; }
.map-tools { justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.map-zoom output { min-width: 44px; text-align: center; font: 12px ui-monospace, monospace; }
.map-tools a { text-decoration: underline; text-underline-offset: 4px; }
.map-help { margin: 10px 0 12px; font-size: 11px; color: var(--muted); }
.map-viewport { height: min(62dvh, 720px); min-height: 200px; overflow: auto; position: relative; border: 1px solid var(--line); border-radius: 5px; background: var(--panel); overscroll-behavior: contain; touch-action: pan-x pan-y pinch-zoom; }
.map-viewport:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.map-stage { display: grid; place-items: center; }
.map-stage img { display: block; max-width: none; height: auto; user-select: none; }
.map-stage img.pending { visibility: hidden; }
.map-viewport.zoomed { cursor: grab; }
.map-viewport.zoomed:active { cursor: grabbing; }
.map-status { position: absolute; inset: 0; display: grid; place-items: center; padding: 24px; text-align: center; font-size: 13px; color: var(--muted); }
@media (max-width: 700px) {
  .map-heading h2 { font-size: 21px; }
  .map-subtitle { font-size: 11px; }
  .map-zoom { gap: 7px; }
  .map-tools .text-button { font-size: 11px; }
  .map-viewport { height: 56dvh; }
}
</style>

<script setup>
import { ref, watch } from 'vue';
const props = defineProps(['config', 'busy']);
const emit = defineEmits(['save']);
const name = ref(''), editing = ref(null);
watch(() => props.config, () => { name.value = ''; editing.value = null; });
function save() {
  if (!name.value.trim() || props.busy) return;
  const lists = editing.value ? props.config.lists.map(x => x.id === editing.value ? { ...x, name: name.value.trim() } : x) : [...props.config.lists, { id: crypto.randomUUID(), name: name.value.trim() }];
  emit('save', { ...props.config, lists });
}
function remove(list) {
  if (!confirm(`删除清单「${list.name}」？其中的任务将移到收集箱，依赖关系保留。`)) return;
  emit('save', { ...props.config, lists: props.config.lists.filter(x => x.id !== list.id), items: props.config.items.map(x => x.listId === list.id ? { ...x, listId: '' } : x) });
}
</script>
<template>
  <details class="task-list-manager"><summary>管理清单 <small>{{ config.lists.length }}/50</small></summary>
    <ul><li v-for="list in config.lists" :key="list.id"><span>{{ list.name }}</span><button class="text-button" :disabled="busy" @click="editing = list.id; name = list.name">重命名</button><button class="text-button danger" :disabled="busy" @click="remove(list)">删除清单</button></li></ul>
    <form class="task-list-form" @submit.prevent="save"><label>{{ editing ? '清单新名称' : '新清单名称' }}<input v-model="name" name="listName" maxlength="60" required :disabled="busy" placeholder="例如：毕业设计、个人计划"></label><button class="secondary" :disabled="busy || (!editing && config.lists.length >= 50)" type="submit">{{ editing ? '保存名称' : '创建清单' }}</button><button v-if="editing" class="text-button" type="button" :disabled="busy" @click="editing = null; name = ''">取消</button></form>
    <p class="field-help">未分类的任务放在收集箱。不同清单的任务也可以互相依赖。</p>
  </details>
</template>

<script setup>
import { ref, onMounted } from 'vue';
defineProps(['label']);
const emit = defineEmits(['close']);
const dialog = ref();
onMounted(() => dialog.value.showModal());
</script>
<template><dialog ref="dialog" :aria-label="label" @cancel.prevent="emit('close')"><slot /></dialog></template>

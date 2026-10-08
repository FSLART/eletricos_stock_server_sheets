<script setup>
import { computed } from 'vue'
const props = defineProps({ item: { type: Object, required: true }, busy: Boolean })
defineEmits(['step', 'delete'])
const mainValue = computed(() => {
  const p = props.item.props
  return p.valor || p.capacidade || Object.values(p)[0] || '—'
})
const color = computed(() => `hsl(${[...props.item.cat].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7)} 65% 48%)`)
</script>

<template>
  <div class="row" :class="{ low: item.qty <= 5 }">
    <span class="pill"><i class="dot" :style="{ background: color }"></i>{{ item.cat }}</span>
    <img v-if="item.image" class="item-image" :src="item.image" :alt="`Imagem de ${item.cat}`">
    <span v-else></span>
    <div>
      <div><span class="val">{{ mainValue }}</span><span v-if="item.qty <= 5" class="tag">pouco stock</span></div>
      <div class="chips"><span v-for="(value, key) in item.props" :key="key" class="chip"><b>{{ key }}</b>{{ value }}</span></div>
    </div>
    <div class="qty">
      <button v-for="delta in [-10, -1]" :key="delta" :class="{ 'step-one': delta === -1 }" :aria-label="`Retirar ${-delta}`" :disabled="busy" @click="$emit('step', delta)">{{ delta === -1 ? '−' : '−10' }}</button>
      <output>{{ item.qty }}</output>
      <button v-for="delta in [1, 10]" :key="delta" :class="{ 'step-one': delta === 1 }" :aria-label="`Adicionar ${delta}`" :disabled="busy" @click="$emit('step', delta)">{{ delta === 1 ? '+' : '+10' }}</button>
    </div>
    <button class="del" aria-label="Apagar item" title="Apagar item" :disabled="busy" @click="$emit('delete')">✕</button>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { defaultImage } from '../defaultImages.js'
const props = defineProps({ item: { type: Object, required: true }, propertyKeys: { type: Array, default: () => [] }, busy: Boolean, canEdit: Boolean, locked: Boolean })
defineEmits(['step', 'delete', 'edit'])
const imageFailed = ref(false)
watch(() => props.item.image, () => { imageFailed.value = false })
const usesDefaultImage = computed(() => !props.item.image || imageFailed.value)
const imageSource = computed(() => usesDefaultImage.value ? defaultImage(props.item.cat) : props.item.image)
const mainValue = computed(() => {
  const p = props.item.props
  return p.valor || p.capacidade || Object.values(p)[0] || '—'
})
const color = computed(() => `hsl(${[...props.item.cat].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7)} 65% 48%)`)
</script>

<template>
  <tr class="row" :class="{ low: item.qty <= 5 }">
    <td class="image-cell">
    <img class="item-image" :class="{ 'default-image': usesDefaultImage }" :src="imageSource" :alt="`${usesDefaultImage ? 'Ícone padrão' : 'Imagem'} de ${item.cat}`" :title="usesDefaultImage ? `Ícone padrão de ${item.cat}` : item.cat" @error="imageFailed = true">
    </td>
    <td><span class="pill"><i class="dot" :style="{ background: color }"></i>{{ item.cat }}</span></td>
    <td class="component-cell"><span class="val">{{ mainValue }}</span><span v-if="item.qty <= 5" class="tag">{{ item.qty === 0 ? 'sem stock' : 'pouco stock' }}</span></td>
    <td v-for="key in propertyKeys" :key="key" class="chips property-cell">{{ item.props[key] || '—' }}</td>
    <td>
    <div class="qty">
      <button v-for="delta in [-10, -1]" :key="delta" :class="{ 'step-one': delta === -1 }" :aria-label="`Retirar ${-delta}`" :disabled="busy" @click="$emit('step', delta)">{{ delta === -1 ? '−' : '−10' }}</button>
      <output>{{ item.qty }}</output>
      <button v-for="delta in [1, 10]" :key="delta" :class="{ 'step-one': delta === 1 }" :aria-label="`Adicionar ${delta}`" :disabled="busy" @click="$emit('step', delta)">{{ delta === 1 ? '+' : '+10' }}</button>
    </div>
    </td>
    <td>
    <div class="item-actions">
      <button v-if="canEdit" class="edit" aria-label="Editar componente" :disabled="busy || locked" @click="$emit('edit')">Editar</button>
      <button class="del" aria-label="Apagar item" title="Apagar item" :disabled="busy || locked" @click="$emit('delete')">✕</button>
    </div>
    </td>
  </tr>
</template>

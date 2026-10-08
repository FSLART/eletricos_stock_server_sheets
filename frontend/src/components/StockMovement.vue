<script setup>
import { computed, ref } from 'vue'
const props = defineProps({ categories: Array, items: Array, busy: Boolean, error: String })
const emit = defineEmits(['submit', 'clear-error'])
const dialog = ref(null)
const fileInput = ref(null)
const category = ref('')
const values = ref({})
const mode = ref('in')
const qty = ref(1)
const editing = ref(null), removeImage = ref(false)
const selected = computed(() => props.categories.find(c => c.name === category.value))
const hint = computed(() => mode.value === 'in'
  ? 'Se já existir um item com as mesmas propriedades, a quantidade é somada.'
  : 'Preenche as propriedades do item de onde queres retirar.')
function resetFields() {
  values.value = {}
  if (fileInput.value) fileInput.value.value = ''
  emit('clear-error')
}
function open(current) {
  editing.value = null
  removeImage.value = false
  category.value = props.categories.some(c => c.name === current) ? current : props.categories[0]?.name || ''
  mode.value = 'in'
  qty.value = 1
  resetFields()
  dialog.value.showModal()
}
function edit(item) {
  category.value = item.cat
  editing.value = { ...item }
  removeImage.value = false
  qty.value = item.qty
  resetFields()
  values.value = { ...item.props }
  dialog.value.showModal()
}
function suggestions(prop) {
  return [...new Set(props.items.filter(it => it.cat === category.value).map(it => it.props[prop]).filter(Boolean))]
}
function submit() {
  const payload = {
    cat: category.value,
    props: Object.fromEntries((selected.value?.props || []).map(p => [p, (values.value[p] || '').trim()])),
    qty: Number(qty.value), mode: mode.value, file: fileInput.value?.files[0],
  }
  if (editing.value) {
    payload.id = editing.value.id
    if (removeImage.value) payload.image = ''
  }
  emit('submit', payload)
}
defineExpose({ open, edit, close: () => dialog.value.close() })
</script>

<template>
  <dialog ref="dialog" aria-labelledby="movement-title">
    <form @submit.prevent="submit">
      <h2 id="movement-title">{{ editing ? 'Editar componente' : 'Movimento de stock' }}</h2>
      <div v-if="!editing" class="seg" role="group" aria-label="Tipo de movimento">
        <button v-for="m in ['in', 'out']" :key="m" type="button" :aria-pressed="mode === m" @click="mode = m; emit('clear-error')">{{ m === 'in' ? 'Entrada' : 'Saída' }}</button>
      </div>
      <label>Categoria <select v-model="category" :disabled="!!editing" required @change="resetFields"><option v-for="c in categories" :key="c.name">{{ c.name }}</option></select></label>
      <div class="fields">
        <label v-for="(p, i) in selected?.props || []" :key="category + p">{{ p }}
          <input v-model="values[p]" :list="`suggestion-${i}`" required autocomplete="off">
          <datalist :id="`suggestion-${i}`"><option v-for="value in suggestions(p)" :key="value" :value="value"></option></datalist>
        </label>
      </div>
      <img v-if="editing?.image && !removeImage" :src="editing.image" class="item-image" alt="Imagem atual">
      <label v-if="editing?.image" class="check"><input v-model="removeImage" type="checkbox"> Remover imagem atual</label>
      <label v-show="selected?.image">{{ editing ? 'Substituir imagem' : 'Imagem' }} <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label>
      <label>Quantidade <input v-model.number="qty" type="number" :min="editing ? 0 : 1" step="1" required></label>
      <p class="hint" :class="{ error }" role="status">{{ error || (editing ? 'A quantidade indicada substitui o stock atual. Sem nova imagem, a existente é mantida.' : hint) }}</p>
      <div class="actions"><button type="button" class="ghost" :disabled="busy" @click="dialog.close()">Cancelar</button><button class="primary" :disabled="busy || !selected">{{ editing ? 'Guardar alterações' : mode === 'in' ? 'Adicionar ao stock' : 'Retirar do stock' }}</button></div>
    </form>
  </dialog>
</template>

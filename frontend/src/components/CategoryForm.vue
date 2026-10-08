<script setup>
import { ref } from 'vue'
defineProps({ busy: Boolean, error: String })
const emit = defineEmits(['submit'])
const dialog = ref(null)
const name = ref(''), properties = ref(''), image = ref(false)
const originalName = ref(null), fields = ref([]), originalFields = ref([])
function open(category) {
  originalName.value = category?.name || null
  originalFields.value = [...(category?.props || [])]
  fields.value = (category?.props || []).map(p => ({ source: p, name: p }))
  name.value = ''; properties.value = ''; image.value = false
  if (category) { name.value = category.name; image.value = category.image }
  dialog.value.showModal()
}
function submit() {
  if (originalName.value) {
    const removed = originalFields.value.filter(p => !fields.value.some(f => f.source === p))
    if (removed.length && !confirm(`Remover as propriedades ${removed.join(', ')} e os seus valores de todos os componentes desta categoria?`)) return
    emit('submit', { originalName: originalName.value, name: name.value.trim(), fields: fields.value.map(f => ({ ...f, name: f.name.trim() })), image: image.value })
  } else {
    emit('submit', { name: name.value.trim(), props: properties.value.split(',').map(p => p.trim()).filter(Boolean), image: image.value })
  }
}
defineExpose({ open, close: () => dialog.value.close() })
</script>

<template>
  <dialog ref="dialog" aria-labelledby="category-title">
    <form @submit.prevent="submit">
      <h2 id="category-title">{{ originalName ? 'Editar categoria' : 'Nova categoria' }}</h2>
      <label>Nome <input v-model="name" placeholder="Ex.: Díodos" required></label>
      <template v-if="originalName">
        <div v-for="(field, index) in fields" :key="index" class="property-editor">
          <label>Propriedade <input v-model="field.name" required></label>
          <button type="button" class="del" :disabled="fields.length === 1" aria-label="Remover propriedade" @click="fields.splice(index, 1)">✕</button>
        </div>
        <button type="button" class="ghost" @click="fields.push({ source: null, name: '' })">+ Adicionar propriedade</button>
      </template>
      <label v-else>Propriedades (separadas por vírgula) <input v-model="properties" placeholder="Ex.: tipo, tensão, corrente" required></label>
      <label class="check"><input v-model="image" type="checkbox"> Permitir uma imagem por componente</label>
      <p class="hint">{{ originalName ? 'Renomear uma propriedade mantém os valores existentes. Novas propriedades ficam vazias até editares cada componente.' : 'Itens com todas as propriedades iguais ficam agrupados e a quantidade soma.' }}</p>
      <p v-if="error" class="hint error" role="alert">{{ error }}</p>
      <div class="actions"><button type="button" class="ghost" :disabled="busy" @click="dialog.close()">Cancelar</button><button class="primary" :disabled="busy">{{ originalName ? 'Guardar alterações' : 'Criar categoria' }}</button></div>
    </form>
  </dialog>
</template>

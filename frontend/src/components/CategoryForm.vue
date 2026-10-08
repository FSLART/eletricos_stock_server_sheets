<script setup>
import { ref } from 'vue'
defineProps({ busy: Boolean })
const emit = defineEmits(['submit'])
const dialog = ref(null)
const name = ref(''), properties = ref(''), image = ref(false)
function open() {
  name.value = ''; properties.value = ''; image.value = false
  dialog.value.showModal()
}
function submit() {
  emit('submit', { name: name.value.trim(), props: properties.value.split(',').map(p => p.trim()).filter(Boolean), image: image.value })
}
defineExpose({ open, close: () => dialog.value.close() })
</script>

<template>
  <dialog ref="dialog" aria-labelledby="category-title">
    <form @submit.prevent="submit">
      <h2 id="category-title">Nova categoria</h2>
      <label>Nome <input v-model="name" placeholder="Ex.: Díodos" required></label>
      <label>Propriedades (separadas por vírgula) <input v-model="properties" placeholder="Ex.: tipo, tensão, corrente" required></label>
      <label class="check"><input v-model="image" type="checkbox"> Permitir uma imagem por componente</label>
      <p class="hint">Itens com todas as propriedades iguais ficam agrupados e a quantidade soma.</p>
      <div class="actions"><button type="button" class="ghost" :disabled="busy" @click="dialog.close()">Cancelar</button><button class="primary" :disabled="busy">Criar categoria</button></div>
    </form>
  </dialog>
</template>

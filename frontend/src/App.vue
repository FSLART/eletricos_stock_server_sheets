<script setup>
import { computed, onMounted, onUnmounted, ref, shallowReactive } from 'vue'
import { createApi } from './api.js'
import StockItem from './components/StockItem.vue'
import StockMovement from './components/StockMovement.vue'
import CategoryForm from './components/CategoryForm.vue'

const api = createApi()
const categories = ref([]), items = ref([]), current = ref(null), query = ref('')
const busy = ref(false), loading = ref(true), toastMessage = ref(''), formError = ref('')
const movement = ref(null), categoryForm = ref(null)
const queues = shallowReactive(new Map())
let timer, toastTimer, refreshing = false, disposed = false
const normalize = value => String(value).toLowerCase().replace(/\s+/g, '')
const shown = computed(() => items.value.filter(item =>
  (!current.value || item.cat === current.value) &&
  normalize(item.cat + Object.values(item.props).join('')).includes(normalize(query.value))))
const units = computed(() => shown.value.reduce((sum, item) => sum + item.qty, 0))
const total = name => items.value.filter(item => !name || item.cat === name).reduce((sum, item) => sum + item.qty, 0)
const color = name => `hsl(${[...name].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7)} 65% 48%)`
const locked = computed(() => busy.value || queues.size > 0)

function toast(message) {
  toastMessage.value = message || ''
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMessage.value = '' }, 3000)
}
async function load() {
  const data = await api.load()
  if (disposed) return
  categories.value = data.categories
  items.value = data.items
  if (current.value && !categories.value.some(c => c.name === current.value)) current.value = null
}
async function act(action, payload, success) {
  if (busy.value || queues.size) return
  busy.value = true
  toast('A sincronizar...')
  try {
    const result = await api.request(action, payload)
    success?.(result)
    toast(result.msg)
    if (!result.queued) await load()
  } catch (error) { toast(error.message) }
  finally { busy.value = false }
}
function deleteItem(item) {
  if (confirm('Apagar este item do stock?')) act('deleteItem', { id: item.id })
}
function deleteCategory(category) {
  const refs = items.value.filter(item => item.cat === category.name)
  const warning = refs.length
    ? `Isto vai apagar também ${refs.length} referência(s) (${total(category.name)} unidades) que estão lá dentro. Esta ação não pode ser desfeita.`
    : 'Esta ação não pode ser desfeita.'
  if (confirm(`Apagar a categoria "${category.name}"?\n\n${warning}`)) {
    act('deleteCategory', { name: category.name }, () => {
      if (current.value === category.name) current.value = null
    })
  }
}
function stepItem(item, requestedDelta) {
  if (busy.value) return
  const delta = Math.max(0, item.qty + requestedDelta) - item.qty
  if (!delta) return
  item.qty += delta
  const queue = queues.get(item.id) || { pending: 0, running: false, timer: null }
  queue.pending += delta
  queues.set(item.id, queue)
  if (!queue.running && !queue.timer) {
    queue.timer = setTimeout(() => { queue.timer = null; processQueue(item.id, queue) }, 150)
  }
}
async function processQueue(id, queue) {
  queue.running = true
  toast('A sincronizar...')
  try {
    while (queue.pending) {
      const delta = queue.pending
      queue.pending = 0
      try {
        const result = await api.request('step', { id, delta })
        if (result.queued) toast(result.msg)
      } catch (error) {
        const item = items.value.find(item => item.id === id)
        if (item) item.qty = Math.max(0, item.qty - delta)
        toast(error.message)
      }
    }
  } finally { queues.delete(id) }
}
async function submitMovement({ file, ...payload }) {
  if (busy.value || queues.size) return
  busy.value = true
  formError.value = ''
  try {
    payload.image = file ? await api.uploadImage(file) : ''
    const result = await api.request('move', payload)
    movement.value.close()
    toast(result.msg)
    if (!result.queued) await load()
  } catch (error) { formError.value = error.message }
  finally { busy.value = false }
}
function submitCategory(payload) {
  act('newCategory', payload, () => {
    categoryForm.value.close()
    current.value = payload.name
  })
}
async function refresh() {
  if (refreshing || busy.value || queues.size || document.visibilityState === 'hidden') return
  refreshing = true
  try {
    const count = await api.syncPending(toast)
    await load()
    if (count) toast(`${count} operação(ões) sincronizada(s)`)
  } catch { /* Preserve the last visible snapshot when the network is down. */ }
  finally { refreshing = false }
}
onMounted(async () => {
  window.addEventListener('online', refresh)
  timer = setInterval(refresh, 15000)
  try {
    await api.syncPending(toast)
    await load()
  } catch (error) { toast(error.message || 'Sem ligação ao servidor e sem dados guardados neste dispositivo') }
  finally { loading.value = false }
})
onUnmounted(() => {
  disposed = true
  clearInterval(timer)
  clearTimeout(toastTimer)
  for (const queue of queues.values()) clearTimeout(queue.timer)
  window.removeEventListener('online', refresh)
})
</script>

<template>
  <aside>
    <div class="logo">Gaveta<small>Stock de componentes</small></div>
    <nav aria-label="Categorias">
      <div class="cat-row"><button :aria-current="!current" @click="current = null">Tudo <span class="n">{{ total() }}</span></button></div>
      <div v-for="category in categories" :key="category.name" class="cat-row">
        <button :aria-current="current === category.name" @click="current = category.name"><span><i class="dot" :style="{ background: color(category.name) }"></i>{{ category.name }}</span><span class="n">{{ total(category.name) }}</span></button>
        <button class="cat-del" :aria-label="`Apagar categoria ${category.name}`" title="Apagar categoria" :disabled="locked" @click="deleteCategory(category)">✕</button>
      </div>
    </nav>
    <button class="side-btn" :disabled="locked" @click="categoryForm.open()">+ Nova categoria</button>
  </aside>
  <main>
    <div class="top">
      <div class="search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input v-model="query" type="search" aria-label="Pesquisar componentes" placeholder="Pesquisar por valor, tamanho, categoria…" autocomplete="off">
      </div>
      <button class="primary" :disabled="locked || !categories.length" @click="movement.open(current)">Adicionar / retirar</button>
    </div>
    <div class="heading"><h1>{{ current || 'Tudo' }}</h1><span class="sub">{{ shown.length }} referências · {{ units }} unidades</span></div>
    <div class="list" :aria-busy="loading">
      <div v-if="loading" class="empty">A carregar stock…</div>
      <template v-else>
        <StockItem v-for="item in shown" :key="item.id" :item="item" :busy="busy" @step="delta => stepItem(item, delta)" @delete="deleteItem(item)" />
        <div v-if="!shown.length" class="empty"><b>Nada encontrado.</b><br>Tenta outra pesquisa ou adiciona um item novo.</div>
      </template>
    </div>
  </main>
  <StockMovement ref="movement" :categories="categories" :items="items" :busy="busy" :error="formError" @submit="submitMovement" @clear-error="formError = ''" />
  <CategoryForm ref="categoryForm" :busy="busy" @submit="submitCategory" />
  <div id="toast" role="status" :class="{ on: toastMessage }">{{ toastMessage }}</div>
</template>

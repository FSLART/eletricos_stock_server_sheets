<script setup>
import { computed, onMounted, onUnmounted, ref, shallowReactive, watch } from 'vue'
import { createApi } from './api.js'
import StockItem from './components/StockItem.vue'
import StockMovement from './components/StockMovement.vue'
import CategoryForm from './components/CategoryForm.vue'
import lartBadge from './assets/lart-badge.png?inline'

const api = createApi()
const categories = ref([]), items = ref([]), current = ref(null), query = ref('')
const busy = ref(false), loading = ref(true), toastMessage = ref(''), formError = ref('')
const movement = ref(null), categoryForm = ref(null)
const canEdit = ref(false), categoryError = ref('')
const queues = shallowReactive(new Map())
let timer, toastTimer, refreshing = false, disposed = false
const normalize = value => String(value).toLowerCase().replace(/\s+/g, '')
const propertyFilters = ref({}), filterSearch = ref({}), stockFilter = ref(''), imageFilter = ref('')
const filtersOpen = ref(true), sortKey = ref(''), sortDirection = ref(1)
const scopedItems = computed(() => items.value.filter(item => !current.value || item.cat === current.value))
const propertyKeys = computed(() => [...new Set([
  ...scopedItems.value.flatMap(item => Object.keys(item.props)),
])])
const facets = computed(() => propertyKeys.value.map(key => ({ key, values: [...new Set(
  scopedItems.value.map(item => String(item.props[key] ?? '')).filter(Boolean)
)].sort((a, b) => a.localeCompare(b, 'pt', { numeric: true })) })))
const columns = computed(() => [
  { key: 'cat', label: 'Categoria' }, { key: 'component', label: 'Componente' },
  ...propertyKeys.value.map(key => ({ key: `prop:${key}`, label: key })),
  { key: 'qty', label: 'Quantidade' },
])
const activeFilters = computed(() => Object.values(propertyFilters.value).reduce((sum, values) => sum + values.length, 0) + Number(Boolean(stockFilter.value)) + Number(Boolean(imageFilter.value)))
watch(current, () => { propertyFilters.value = {}; filterSearch.value = {} })
function clearFilters() {
  current.value = null
  query.value = ''
  propertyFilters.value = {}
  filterSearch.value = {}
  stockFilter.value = ''
  imageFilter.value = ''
}
function toggleProperty(key, value) {
  const selected = propertyFilters.value[key] || []
  propertyFilters.value[key] = selected.includes(value) ? selected.filter(entry => entry !== value) : [...selected, value]
}
function sortBy(key) {
  sortDirection.value = sortKey.value === key ? -sortDirection.value : 1
  sortKey.value = key
}
const componentValue = item => item.props.valor || item.props.capacidade || Object.values(item.props)[0] || '—'
const sortValue = (item, key) => key === 'component' ? componentValue(item) : key.startsWith('prop:') ? item.props[key.slice(5)] ?? '' : item[key]
const shown = computed(() => items.value.filter(item =>
  (!current.value || item.cat === current.value) &&
  normalize(item.cat + Object.values(item.props).join('')).includes(normalize(query.value)) &&
  Object.entries(propertyFilters.value).every(([key, values]) => !values.length || values.includes(String(item.props[key] ?? ''))) &&
  (!stockFilter.value || (stockFilter.value === 'empty' ? item.qty === 0 : stockFilter.value === 'low' ? item.qty > 0 && item.qty <= 5 : item.qty > 0)) &&
  (!imageFilter.value || Boolean(item.image) === (imageFilter.value === 'yes'))
).sort((a, b) => {
  if (!sortKey.value) return 0
  const av = sortValue(a, sortKey.value), bv = sortValue(b, sortKey.value)
  return sortDirection.value * (sortKey.value === 'qty' ? av - bv : String(av).localeCompare(String(bv), 'pt', { numeric: true, sensitivity: 'base' }))
}))
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
  canEdit.value = Boolean(data.can_edit)
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
    const editing = payload.id !== undefined
    if (file) payload.image = await api.uploadImage(file)
    else if (!editing) payload.image = ''
    if (editing) { delete payload.mode; delete payload.cat }
    const result = await api.request(editing ? 'editItem' : 'move', payload)
    movement.value.close()
    toast(result.msg)
    if (!result.queued) await load()
  } catch (error) { formError.value = error.message }
  finally { busy.value = false }
}
function openCategory(category) {
  categoryError.value = ''
  categoryForm.value.open(category)
}
async function submitCategory(payload) {
  if (busy.value || queues.size) return
  busy.value = true
  categoryError.value = ''
  try {
    const result = await api.request(payload.originalName ? 'editCategory' : 'newCategory', payload)
    categoryForm.value.close()
    current.value = payload.name
    toast(result.msg)
    if (!result.queued) await load()
  } catch (error) { categoryError.value = error.message }
  finally { busy.value = false }
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
    <div class="logo"><img class="brand-icon" :src="lartBadge" alt="LART" width="64" height="64"><div>Gaveta<small>Stock de componentes · LART</small></div></div>
    <nav aria-label="Categorias">
      <div class="cat-row"><button :aria-current="!current" @click="current = null">Tudo <span class="n">{{ total() }}</span></button></div>
      <div v-for="category in categories" :key="category.name" class="cat-row">
        <button :aria-current="current === category.name" @click="current = category.name"><span><i class="dot" :style="{ background: color(category.name) }"></i>{{ category.name }}</span><span class="n">{{ total(category.name) }}</span></button>
        <button v-if="canEdit" class="cat-edit" :aria-label="`Editar categoria ${category.name}`" :disabled="locked" @click="openCategory(category)">Editar</button>
        <button class="cat-del" :aria-label="`Apagar categoria ${category.name}`" title="Apagar categoria" :disabled="locked" @click="deleteCategory(category)">✕</button>
      </div>
    </nav>
    <button class="side-btn" :disabled="locked" @click="openCategory()">+ Nova categoria</button>
  </aside>
  <main>
    <div class="top">
      <div class="search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <input v-model="query" type="search" aria-label="Pesquisar componentes" placeholder="Pesquisar por valor, tamanho, categoria…" autocomplete="off">
      </div>
      <button class="primary" :disabled="locked || !categories.length" @click="movement.open(current)">Adicionar / retirar</button>
    </div>
    <section class="filter-section" aria-label="Filtros de componentes">
      <div class="filter-toolbar">
        <button class="filter-toggle" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen">Filtros <span v-if="activeFilters" class="filter-count">{{ activeFilters }}</span><span aria-hidden="true">{{ filtersOpen ? '⌃' : '⌄' }}</span></button>
        <div class="quick-filters">
          <select v-model="stockFilter" aria-label="Filtrar stock"><option value="">Todo o stock</option><option value="available">Em stock</option><option value="low">Pouco stock (1–5)</option><option value="empty">Sem stock</option></select>
          <select v-model="imageFilter" aria-label="Filtrar imagens"><option value="">Todas as imagens</option><option value="yes">Com imagem</option><option value="no">Sem imagem</option></select>
          <button class="clear-filters" aria-label="Limpar filtros" :disabled="!activeFilters && !query && !current" @click="clearFilters">✕ Limpar filtros</button>
        </div>
      </div>
      <div v-show="filtersOpen" class="filter-panels">
        <div v-for="facet in facets" :key="facet.key" class="filter-panel">
          <h2>{{ facet.key }}</h2>
          <input v-model="filterSearch[facet.key]" type="text" :aria-label="`Pesquisar filtro ${facet.key}`" placeholder="Pesquisar…">
          <div class="filter-options">
            <label v-for="value in facet.values.filter(value => normalize(value).includes(normalize(filterSearch[facet.key] || '')))" :key="value" class="filter-option">
              <input type="checkbox" :aria-label="`Filtrar ${facet.key}: ${value}`" :checked="(propertyFilters[facet.key] || []).includes(value)" @change="toggleProperty(facet.key, value)"><span :title="value">{{ value }}</span>
            </label>
            <p v-if="!facet.values.length" class="filter-no-values">Sem valores</p>
          </div>
        </div>
        <p v-if="!facets.length" class="filter-no-values">As propriedades das categorias aparecem aqui como filtros.</p>
      </div>
    </section>
    <div class="heading"><h1>{{ current || 'Tudo' }}</h1><span class="sub">{{ shown.length }} referências · {{ units }} unidades</span></div>
    <div class="list" :aria-busy="loading">
      <div v-if="loading" class="empty">A carregar stock…</div>
      <template v-else>
        <table class="stock-table">
          <caption class="sr-only">Stock de componentes</caption>
          <thead><tr>
            <th scope="col" class="image-column">Imagem</th>
            <th v-for="column in columns" :key="column.key" scope="col" :aria-sort="sortKey === column.key ? (sortDirection === 1 ? 'ascending' : 'descending') : 'none'">
              <button :aria-label="`Ordenar por ${column.label}`" @click="sortBy(column.key)">{{ column.label }} <span aria-hidden="true">{{ sortKey === column.key ? (sortDirection === 1 ? '↑' : '↓') : '↕' }}</span></button>
            </th>
            <th scope="col">Ações</th>
          </tr></thead>
          <tbody><StockItem v-for="item in shown" :key="item.id" :item="item" :property-keys="propertyKeys" :busy="busy" :locked="locked" :can-edit="canEdit" @edit="movement.edit(item)" @step="delta => stepItem(item, delta)" @delete="deleteItem(item)" /></tbody>
        </table>
        <div v-if="!shown.length" class="empty"><b>Nada encontrado.</b><br>Tenta outra pesquisa ou adiciona um item novo.</div>
      </template>
    </div>
  </main>
  <StockMovement ref="movement" :categories="categories" :items="items" :busy="busy" :error="formError" @submit="submitMovement" @clear-error="formError = ''" />
  <CategoryForm ref="categoryForm" :busy="busy" :error="categoryError" @submit="submitCategory" />
  <div id="toast" role="status" :class="{ on: toastMessage }">{{ toastMessage }}</div>
</template>

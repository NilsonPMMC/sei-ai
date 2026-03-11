<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useUnidadesSinapse } from './composables/useUnidadesSinapse'
import SGDLeDataTable from './components/SGDLeDataTable.vue'

const API_BASE = 'https://protocolosei.mogidascruzes.sp.gov.br'
const processos = ref([])
const carregando = ref(true)
const erro = ref(null)

const {
  opcoesUnidade,
  loading: loadingUnidades,
  erro: erroUnidades,
  fetchUnidades,
  getUnidadeByProcesso,
  getUnidadeIdByProcesso,
} = useUnidadesSinapse()

const viewMode = ref('card') // 'card' | 'table'

const filtroStatus = ref('')
const filtroUnidade = ref('')
const buscaPalavras = ref('')

/** Unidades da API Sinapse (id + sigla/nome) para o select de rota Human-in-the-Loop */
const listaUnidades = ref([])

/** Unidade destino selecionada por processo (numero_sei → unidadeId) */
const unidadesSelecionadas = ref({})

function _extrairUnidades(data) {
  if (Array.isArray(data)) return data
  for (const key of ['data', 'results', 'items']) {
    if (data[key] && Array.isArray(data[key])) return data[key]
  }
  return []
}

/** Lista computada: reflete filtros de Status, Unidade e busca textual automaticamente */
const processosFiltrados = computed(() => {
  let lista = [...processos.value]
  if (filtroStatus.value) {
    lista = lista.filter((p) => p.status_documentacao === filtroStatus.value)
  }
  if (filtroUnidade.value) {
    const unidadeId = Number(filtroUnidade.value)
    lista = lista.filter((p) => getUnidadeIdByProcesso(p) === unidadeId)
  }
  if (buscaPalavras.value.trim()) {
    const termos = buscaPalavras.value.trim().toLowerCase().split(/\s+/)
    lista = lista.filter((p) => {
      const unidade = getUnidadeByProcesso(p)
      const texto = [
        p.numero_sei,
        p.servico_nome,
        unidade,
        p.resumo_ia,
        ...(p.documentos_faltantes || []),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return termos.every((t) => texto.includes(t))
    })
  }
  return lista
})

/** Lista filtrada — serve tanto para Cards quanto para DataTable */
const filteredData = computed(() => processosFiltrados.value)

/** Carrega a fila de processos do backend (GET /v1/fila) */
async function carregarFila() {
  carregando.value = true
  erro.value = null
  try {
    const res = await fetch(`${API_BASE}/v1/fila`)
    if (!res.ok) throw new Error(`Erro ${res.status}: ${res.statusText}`)
    processos.value = await res.json()
  } catch (e) {
    erro.value = e.message
    processos.value = []
  } finally {
    carregando.value = false
  }
}

/** Aprova e tramita o processo (PATCH /v1/fila/{numero_sei}/acao) com unidade destino */
async function aprovarTramitar(numeroSei, processo) {
  const unidadeId = unidadesSelecionadas.value[numeroSei] ?? (processo && obterUnidadeSugerida(processo))
  if (!unidadeId) {
    alert('Selecione a unidade de destino antes de aprovar.')
    return
  }
  try {
    const res = await fetch(`${API_BASE}/v1/fila/${encodeURIComponent(numeroSei)}/acao`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        novo_status: 'APROVADO',
        unidade_destino_id: Number(unidadeId),
      }),
    })
    if (!res.ok) throw new Error(`Erro ${res.status}`)
    processos.value = processos.value.filter((p) => p.numero_sei !== numeroSei)
  } catch (e) {
    alert('Falha ao aprovar: ' + e.message)
  }
}

/** Define sugestão inicial de unidade para um processo (baseado em servico_id → unidade_responsavel) */
function obterUnidadeSugerida(p) {
  return getUnidadeIdByProcesso(p) ?? ''
}

function limparFiltros() {
  filtroStatus.value = ''
  filtroUnidade.value = ''
  buscaPalavras.value = ''
}

/** Devolve o processo com exigência (PATCH /v1/fila/{numero_sei}/acao) */
async function devolverExigencia(numeroSei) {
  try {
    const res = await fetch(`${API_BASE}/v1/fila/${encodeURIComponent(numeroSei)}/acao`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ novo_status: 'DEVOLVIDO' }),
    })
    if (!res.ok) throw new Error(`Erro ${res.status}`)
    processos.value = processos.value.filter((p) => p.numero_sei !== numeroSei)
  } catch (e) {
    alert('Falha ao devolver: ' + e.message)
  }
}

/** Carrega listaUnidades da API (via proxy para evitar CORS) */
async function carregarListaUnidades() {
  try {
    const res = await fetch(`${API_BASE}/v1/sinapse/unidades`)
    if (!res.ok) return
    const data = await res.json()
    const raw = _extrairUnidades(data)
    listaUnidades.value = (raw || [])
      .filter((u) => u.ativo !== false)
      .map((u) => ({
        id: u.id,
        label: u.sigla || u.nome || u.nome_reduzido || String(u.id),
      }))
  } catch {
    listaUnidades.value = []
  }
}

/** Inicializa unidadeSelecionada para cada processo com sugestão do servico_id */
watch(
  () => [...(processos.value || [])],
  (novos) => {
    novos.forEach((p) => {
      if (unidadesSelecionadas.value[p.numero_sei] === undefined) {
        unidadesSelecionadas.value[p.numero_sei] = obterUnidadeSugerida(p) ?? ''
      }
    })
  },
  { deep: true, immediate: true }
)

onMounted(() => {
  carregarFila()
  carregarListaUnidades()
})
</script>

<template>
  <div class="min-h-screen bg-slate-50">
    <!-- Header -->
    <header class="bg-white shadow-sm border-b border-slate-200">
      <div class="max-w-6xl mx-auto px-4 py-4">
        <h1 class="text-xl font-semibold text-slate-800">
          SEI AI - Fila de Triagem
        </h1>
      </div>
    </header>

    <!-- Conteúdo -->
    <main class="max-w-6xl mx-auto px-4 py-8">
      <p v-if="carregando" class="text-slate-600">Carregando fila...</p>
      <p v-else-if="erro" class="text-red-600">
        {{ erro }} — Verifique se o backend está rodando em {{ API_BASE }}
      </p>
      <template v-else>
        <!-- Alerta de erro na API Sinapse -->
        <div
          v-if="erroUnidades"
          class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
          role="alert"
        >
          {{ erroUnidades }}
        </div>

        <!-- Barra de filtros e contador -->
        <div class="mb-6 flex flex-col gap-4">
          <div class="flex flex-wrap items-center justify-between gap-4">
            <p class="text-slate-700 font-medium">
              <span class="text-slate-900">{{ filteredData.length }}</span>
              processo(s) exibido(s)
              <span v-if="processosFiltrados.length !== processos.length" class="text-slate-500">
                de {{ processos.length }} na fila
              </span>
            </p>
            <div class="flex items-center gap-3">
              <button
                v-if="filtroStatus || filtroUnidade || buscaPalavras.trim()"
                type="button"
                @click="limparFiltros"
                class="text-sm text-slate-600 hover:text-slate-900 underline"
              >
                Limpar filtros
              </button>
              <div class="flex rounded-md border border-slate-200 bg-white p-0.5 shadow-sm" role="group">
                <button
                  type="button"
                  :class="[
                    'inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors',
                    viewMode === 'card'
                      ? 'bg-slate-100 text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900',
                  ]"
                  title="Modo Grade (Cards)"
                  @click="viewMode = 'card'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
                  </svg>
                  Card
                </button>
                <button
                  type="button"
                  :class="[
                    'inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium transition-colors',
                    viewMode === 'table'
                      ? 'bg-slate-100 text-slate-900 shadow-sm'
                      : 'text-slate-600 hover:text-slate-900',
                  ]"
                  title="Modo Tabela (Lista)"
                  @click="viewMode = 'table'"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                  </svg>
                  Tabela
                </button>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-4 items-center">
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-slate-500">Status</label>
              <select
                v-model="filtroStatus"
                class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Todos</option>
                <option value="COMPLETA">Completa</option>
                <option value="INCOMPLETA">Incompleta</option>
                <option value="ERRO">Erro</option>
              </select>
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-xs font-medium text-slate-500">
                Unidade Responsável
                <span v-if="loadingUnidades" class="text-slate-400">(carregando…)</span>
                <span v-else-if="erroUnidades" class="text-amber-600" :title="erroUnidades">(!) API Sinapse: {{ erroUnidades }}</span>
              </label>
              <select
                v-model="filtroUnidade"
                class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-w-[180px]"
              >
                <option value="">Todos</option>
                <option v-for="u in opcoesUnidade" :key="u.id" :value="u.id">
                  {{ u.nome }}
                </option>
              </select>
            </div>
            <div class="flex flex-col gap-1 flex-1 min-w-[200px]">
              <label class="text-xs font-medium text-slate-500">Buscar por palavras</label>
              <input
                v-model="buscaPalavras"
                type="text"
                placeholder="Ex: CPF, processo, licença..."
                class="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-full"
              />
            </div>
          </div>
        </div>

        <p v-if="processos.length === 0" class="text-slate-600">Nenhum processo na fila.</p>
        <p v-else-if="filteredData.length === 0" class="text-slate-600">Nenhum processo encontrado com os filtros aplicados.</p>

        <SGDLeDataTable
          v-else-if="viewMode === 'table'"
          :processos="filteredData"
          :get-unidade="getUnidadeByProcesso"
          @aprovar="aprovarTramitar"
          @devolver="devolverExigencia"
        />

        <div v-else-if="viewMode === 'card'" class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <article
            v-for="p in filteredData"
          :key="p.numero_sei"
          class="bg-white rounded-lg shadow-md border border-slate-200 overflow-hidden flex flex-col"
        >
          <!-- Cabeçalho do Card -->
          <div class="px-4 py-3 border-b border-slate-100 flex items-center justify-between gap-2">
            <a
              v-if="p.link_sei"
              :href="p.link_sei"
              target="_blank"
              rel="noopener noreferrer"
              class="font-mono text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline truncate"
            >
              {{ p.numero_sei }}
            </a>
            <span v-else class="font-mono text-sm font-medium text-slate-600 truncate">
              {{ p.numero_sei }}
            </span>
            <span
              :class="[
                'shrink-0 px-2.5 py-0.5 rounded-full text-xs font-medium',
                p.status_documentacao === 'COMPLETA'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-amber-100 text-amber-800',
              ]"
            >
              {{ p.status_documentacao }}
            </span>
          </div>

          <!-- Corpo do Card -->
          <div class="px-4 py-4 flex-1">
            <p class="mb-1 text-xs font-medium text-slate-500">Unidade Responsável</p>
            <h3 class="text-base font-bold text-slate-900 mb-2">
              {{ getUnidadeByProcesso(p) }}
            </h3>
            <p class="text-sm text-gray-600 leading-relaxed">
              {{ p.resumo_ia || 'Sem resumo.' }}
            </p>

            <!-- Anexos Identificados -->
            <div v-if="p.anexos_enviados?.length" class="mt-3">
              <p class="text-xs font-medium text-slate-500 mb-1.5">📎 Anexos Identificados:</p>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="anexo in p.anexos_enviados"
                  :key="anexo"
                  class="inline-block px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-700"
                >
                  {{ anexo }}
                </span>
              </div>
            </div>

            <!-- Alerta de Documentos Faltantes -->
            <div
              v-if="p.status_documentacao === 'INCOMPLETA' && p.documentos_faltantes?.length"
              class="mt-4 p-3 bg-red-50 border border-red-100 rounded-md"
            >
              <p class="text-xs font-medium text-red-800 mb-2">Documentos faltantes:</p>
              <ul class="list-disc list-inside text-sm text-red-700 space-y-0.5">
                <li v-for="doc in p.documentos_faltantes" :key="doc">
                  {{ doc }}
                </li>
              </ul>
            </div>
          </div>

          <!-- Edição de Rota (Human-in-the-Loop) + Ações -->
          <div class="px-4 py-3 border-t border-slate-100 bg-slate-50 space-y-3">
            <div v-if="p.status_documentacao === 'COMPLETA'" class="flex flex-col gap-1">
              <label class="text-xs font-medium text-slate-500">Unidade de destino</label>
              <select
                :model-value="unidadesSelecionadas[p.numero_sei] ?? obterUnidadeSugerida(p) ?? ''"
                @update:model-value="(v) => (unidadesSelecionadas[p.numero_sei] = v)"
                class="rounded-md border border-slate-300 px-3 py-1.5 text-sm w-full focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Selecione...</option>
                <option v-for="u in listaUnidades" :key="u.id" :value="u.id">
                  {{ u.label }}
                </option>
              </select>
            </div>
            <button
              v-if="p.status_documentacao === 'COMPLETA'"
              type="button"
              @click="aprovarTramitar(p.numero_sei, p)"
              class="w-full py-2 px-4 bg-green-600 hover:bg-green-700 text-white font-medium text-sm rounded-md transition-colors"
            >
              Aprovar e Tramitar
            </button>
            <button
              v-else
              type="button"
              @click="devolverExigencia(p.numero_sei)"
              class="w-full py-2 px-4 bg-red-600 hover:bg-red-700 text-white font-medium text-sm rounded-md transition-colors"
            >
              Devolver (Exigência)
            </button>
          </div>
        </article>
      </div>
      </template>
    </main>
  </div>
</template>

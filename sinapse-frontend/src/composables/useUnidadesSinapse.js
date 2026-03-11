/**
 * Composable: Unidades da API Sinapse para filtro na listagem SGDLe.
 * Usa proxy do backend para evitar CORS (GET /v1/sinapse/unidades e /v1/sinapse/servicos).
 */
import { ref, computed, onMounted } from 'vue'

const API_BASE = import.meta.env.VITE_API_BASE || 'https://protocolosei.mogidascruzes.sp.gov.br'
const SINAPSE_PROXY_BASE = `${API_BASE}/v1/sinapse`

function _extrairLista(data) {
  if (Array.isArray(data)) return data
  for (const key of ['data', 'results', 'items']) {
    if (data[key] && Array.isArray(data[key])) return data[key]
  }
  return []
}

export function useUnidadesSinapse() {
  /** Variável reativa com a lista de unidades da API Sinapse */
  const unidades = ref([])
  const servicos = ref([])
  const loading = ref(false)
  const erro = ref(null)

  /** Mapa servico_id → { unidade_responsavel, nome_unidade } (para exibição e filtro) */
  const servicosPorId = computed(() => {
    const map = {}
    for (const s of servicos.value || []) {
      if (s.id != null)
        map[s.id] = {
          unidade_responsavel: s.unidade_responsavel,
          nome_unidade: s.nome_unidade || s.nome || '',
          sigla_unidade: s.sigla_unidade || s.sigla || '',
        }
    }
    return map
  })

  /** Opções para o filtro: unidades da API (id + nome) */
  const opcoesUnidade = computed(() =>
    (unidades.value || []).map((u) => ({ id: u.id, nome: u.nome || u.nome_reduzido || u.sigla || String(u.id) }))
  )

  /** Retorna a Unidade Responsável de um processo (da Carta). Fallback: servico_nome (referência SEI). */
  function getUnidadeByProcesso(processo) {
    if (!processo) return '—'
    const info = processo.servico_id != null && servicosPorId.value[processo.servico_id]
    if (info?.nome_unidade) return info.nome_unidade
    if (info?.sigla_unidade) return info.sigla_unidade
    return processo.servico_nome || '—'
  }

  /** ID da unidade vinculada ao serviço do processo (para filtro). */
  function getUnidadeIdByProcesso(processo) {
    if (!processo?.servico_id) return null
    return servicosPorId.value[processo.servico_id]?.unidade_responsavel ?? null
  }

  async function carregar() {
    loading.value = true
    erro.value = null
    try {
      const [resServicos, resUnidades] = await Promise.all([
        fetch(`${SINAPSE_PROXY_BASE}/servicos`),
        fetch(`${SINAPSE_PROXY_BASE}/unidades`),
      ])

      if (resServicos.ok) {
        const data = await resServicos.json()
        servicos.value = _extrairLista(data)
      } else {
        servicos.value = []
      }

      if (resUnidades.ok) {
        const data = await resUnidades.json()
        const raw = _extrairLista(data)
        unidades.value = raw.filter((u) => u.ativo !== false)
      } else {
        unidades.value = []
      }
    } catch (e) {
      erro.value = 'API Sinapse indisponível. Unidade baseada em referência SEI.'
      servicos.value = []
      unidades.value = []
    } finally {
      loading.value = false
    }
  }

  /**
   * Busca unidades em https://api.mogidascruzes.sp.gov.br/api/v1/unidades/
   * Popula a variável reativa `unidades` e trata loading/erro.
   */
  async function fetchUnidades() {
    return carregar()
  }

  onMounted(fetchUnidades)

  return {
    unidades,
    servicos,
    servicosPorId,
    opcoesUnidade,
    loading,
    erro,
    carregar,
    fetchUnidades,
    getUnidadeByProcesso,
    getUnidadeIdByProcesso,
  }
}

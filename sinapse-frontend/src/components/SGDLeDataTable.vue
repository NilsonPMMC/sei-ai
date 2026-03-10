<script setup>
/**
 * SGDLeDataTable - Tabela de listagem.
 * Colunas: Protocolo, Serviço/Assunto, Unidade Responsável, Data, Status, Ações.
 */
defineProps({
  processos: {
    type: Array,
    required: true,
  },
  getUnidade: {
    type: Function,
    default: (p) => p.servico_nome || '—',
  },
})
const emit = defineEmits(['aprovar', 'devolver'])
</script>

<template>
  <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
    <table class="min-w-full divide-y divide-slate-200">
      <thead class="bg-slate-50">
        <tr>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Protocolo
          </th>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Serviço / Assunto
          </th>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Unidade Responsável
          </th>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Data
          </th>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Status
          </th>
          <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-600">
            Ações
          </th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-200 bg-white">
        <tr v-for="p in processos" :key="p.numero_sei" class="hover:bg-slate-50">
          <td class="px-4 py-3 text-sm">
            <a
              v-if="p.link_sei"
              :href="p.link_sei"
              target="_blank"
              rel="noopener noreferrer"
              class="font-mono text-blue-600 hover:underline"
            >
              {{ p.numero_sei }}
            </a>
            <span v-else class="font-mono text-slate-600">{{ p.numero_sei }}</span>
          </td>
          <td class="px-4 py-3">
            <span class="font-medium text-slate-900">{{ p.servico_nome || '—' }}</span>
            <p class="mt-0.5 max-w-md truncate text-xs text-slate-500" :title="p.resumo_ia">
              {{ p.resumo_ia || 'Sem resumo' }}
            </p>
          </td>
          <td class="px-4 py-3 text-sm text-slate-600">
            {{ getUnidade(p) }}
          </td>
          <td class="px-4 py-3 text-sm text-slate-600">
            {{ p.data_criacao ? new Date(p.data_criacao).toLocaleDateString('pt-BR') : '—' }}
          </td>
          <td class="px-4 py-3">
            <span
              :class="[
                'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                p.status_documentacao === 'COMPLETA'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-amber-100 text-amber-800',
              ]"
            >
              {{ p.status_documentacao }}
            </span>
          </td>
          <td class="px-4 py-3">
            <button
              v-if="p.status_documentacao === 'COMPLETA'"
              type="button"
              @click="emit('aprovar', p.numero_sei)"
              class="rounded bg-green-600 px-2 py-1 text-xs font-medium text-white hover:bg-green-700"
            >
              Aprovar
            </button>
            <button
              v-else
              type="button"
              @click="emit('devolver', p.numero_sei)"
              class="rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700"
            >
              Devolver
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

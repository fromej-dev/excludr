import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { getErrorMessage } from '@/utils/errors'
import type {
  Agreement,
  AiDisagreement,
  ExportFormat,
  PrismaFlow,
  ScreeningStage,
} from '@/types'

type ReportStage = Exclude<ScreeningStage, 'completed'>

/** Parse the filename out of a Content-Disposition header. */
export function filenameFromDisposition(header: string | undefined, fallback: string): string {
  if (!header) return fallback
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (star) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      /* fall through */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1] : fallback
}

export const useReportsStore = defineStore('reports', () => {
  const { get, api } = useApi()

  const prisma = ref<PrismaFlow | null>(null)
  const agreement = ref<Agreement | null>(null)
  const disagreements = ref<AiDisagreement[]>([])
  const loading = ref(false)
  const exporting = ref<ExportFormat | null>(null)
  const error = ref<string | null>(null)

  const fetchPrisma = async (projectId: number) => {
    try {
      prisma.value = await get<PrismaFlow>(`/projects/${projectId}/prisma`)
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load PRISMA flow')
    }
  }

  const fetchAgreement = async (projectId: number, stage: ReportStage) => {
    try {
      agreement.value = await get<Agreement>(`/projects/${projectId}/screening/agreement`, {
        params: { stage },
      })
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load agreement statistics')
    }
  }

  const fetchDisagreements = async (projectId: number, stage: ReportStage) => {
    try {
      disagreements.value = await get<AiDisagreement[]>(
        `/projects/${projectId}/screening/ai-disagreements`,
        { params: { stage } }
      )
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Failed to load AI disagreements')
    }
  }

  const load = async (projectId: number, stage: ReportStage, isOwner: boolean) => {
    loading.value = true
    error.value = null
    await Promise.all([
      fetchPrisma(projectId),
      ...(isOwner ? [fetchAgreement(projectId, stage), fetchDisagreements(projectId, stage)] : []),
    ])
    loading.value = false
  }

  /** Download an export through the authenticated API and save it via a temporary link. */
  const exportArticles = async (projectId: number, format: ExportFormat) => {
    exporting.value = format
    error.value = null
    try {
      const res = await api.get<Blob>(`/projects/${projectId}/export`, {
        params: { format },
        responseType: 'blob',
      })
      const name = filenameFromDisposition(
        res.headers['content-disposition'] as string | undefined,
        `export.${format}`
      )
      const url = URL.createObjectURL(res.data)
      const link = document.createElement('a')
      link.href = url
      link.download = name
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      return name
    } catch (err: unknown) {
      error.value = getErrorMessage(err, 'Export failed')
      return null
    } finally {
      exporting.value = null
    }
  }

  return {
    prisma,
    agreement,
    disagreements,
    loading,
    exporting,
    error,
    load,
    fetchAgreement,
    fetchDisagreements,
    exportArticles,
  }
})

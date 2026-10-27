<script setup lang="ts">
import type { PrismaFlow } from '@/types'
import PrismaBox from './PrismaBox.vue'

interface Props {
  flow: PrismaFlow
}

defineProps<Props>()
</script>

<template>
  <div class="overflow-x-auto" data-testid="prisma-diagram">
    <div class="min-w-[520px] grid grid-cols-[minmax(0,1fr)_2rem_minmax(0,1fr)] items-center gap-y-0">
      <!-- Identification -->
      <p class="col-span-3 mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Identification
      </p>
      <PrismaBox title="Records identified from databases and files" :count="flow.identification.records_identified">
        <p v-for="s in flow.identification.sources" :key="s.filename + s.imported_at" class="break-all">
          {{ s.filename }}: {{ s.records_found }}
        </p>
      </PrismaBox>
      <svg class="h-4 w-8 text-muted-foreground" viewBox="0 0 32 16" aria-hidden="true">
        <path d="M2 8h24m-6-5 6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
      <PrismaBox
        title="Duplicate records removed"
        :count="flow.identification.duplicates_removed"
        tone="exclude"
      />

      <div class="flex justify-center py-1">
        <svg class="h-6 w-4 text-muted-foreground" viewBox="0 0 16 24" aria-hidden="true">
          <path d="M8 2v18m-5-6 5 6 5-6" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </div>
      <div class="col-span-2" />

      <!-- Screening -->
      <p class="col-span-3 my-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Screening
      </p>
      <PrismaBox title="Records screened" :count="flow.screening.records_screened" />
      <svg class="h-4 w-8 text-muted-foreground" viewBox="0 0 32 16" aria-hidden="true">
        <path d="M2 8h24m-6-5 6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
      <PrismaBox
        title="Records excluded (title / abstract)"
        :count="flow.screening.records_excluded"
        tone="exclude"
      />

      <div class="flex justify-center py-1">
        <svg class="h-6 w-4 text-muted-foreground" viewBox="0 0 16 24" aria-hidden="true">
          <path d="M8 2v18m-5-6 5 6 5-6" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </div>
      <div class="col-span-2" />

      <PrismaBox title="Reports sought for retrieval" :count="flow.retrieval.reports_sought" />
      <svg class="h-4 w-8 text-muted-foreground" viewBox="0 0 32 16" aria-hidden="true">
        <path d="M2 8h24m-6-5 6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
      <PrismaBox
        title="Reports not retrieved"
        :count="flow.retrieval.reports_not_retrieved"
        tone="exclude"
      />

      <div class="flex justify-center py-1">
        <svg class="h-6 w-4 text-muted-foreground" viewBox="0 0 16 24" aria-hidden="true">
          <path d="M8 2v18m-5-6 5 6 5-6" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </div>
      <div class="col-span-2" />

      <!-- Eligibility -->
      <p class="col-span-3 my-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Eligibility
      </p>
      <PrismaBox title="Reports assessed for eligibility" :count="flow.eligibility.reports_assessed" />
      <svg class="h-4 w-8 text-muted-foreground" viewBox="0 0 32 16" aria-hidden="true">
        <path d="M2 8h24m-6-5 6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
      <PrismaBox
        title="Reports excluded (full text)"
        :count="flow.eligibility.reports_excluded"
        tone="exclude"
      >
        <p v-for="r in flow.eligibility.exclusion_reasons" :key="r.reason">
          {{ r.reason }}: {{ r.count }}
        </p>
      </PrismaBox>

      <div class="flex justify-center py-1">
        <svg class="h-6 w-4 text-muted-foreground" viewBox="0 0 16 24" aria-hidden="true">
          <path d="M8 2v18m-5-6 5 6 5-6" fill="none" stroke="currentColor" stroke-width="1.5" />
        </svg>
      </div>
      <div class="col-span-2" />

      <!-- Included -->
      <p class="col-span-3 my-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Included
      </p>
      <PrismaBox title="Studies included in review" :count="flow.included.studies_included" tone="include" />
    </div>
  </div>
</template>

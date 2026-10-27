<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useProjectsStore } from '@/stores/projects'
import { useMembersStore } from '@/stores/members'
import { useProjectNavStore } from '@/stores/projectNav'

const route = useRoute()
const projectsStore = useProjectsStore()
const membersStore = useMembersStore()
const nav = useProjectNavStore()
const { pendingTitleAbstract, pendingFullText, conflicts, criteria } = storeToRefs(nav)

type CountTone = 'muted' | 'pending' | 'conflict'

interface NavItem {
  key: string
  label: string
  to: RouteLocationRaw
  active: boolean
  count: number | null
  tone: CountTone
  countLabel?: string
}
interface NavGroup {
  label: string
  items: NavItem[]
}

const projectId = computed(() => Number(route.params.id))
const name = computed(() => (route.name as string) ?? '')
const stage = computed(() => (route.query.stage === 'full_text' ? 'full_text' : 'title_abstract'))

const groups = computed<NavGroup[]>(() => {
  const params = { id: projectId.value }
  const link = (routeName: string, key: string, label: string, extra: Partial<NavItem> = {}): NavItem => ({
    key,
    label,
    to: { name: routeName, params },
    active: name.value === routeName,
    count: null,
    tone: 'muted',
    ...extra,
  })
  const review = membersStore.canReview
  const screeningLink = (s: 'title_abstract' | 'full_text', label: string, count: number | null): NavItem => ({
    key: s,
    label,
    to: { name: 'project-screening', params, query: { stage: s } },
    active: name.value === 'project-screening' && stage.value === s,
    count: review ? count : null,
    tone: 'pending',
    countLabel: 'pending',
  })

  const screening: NavItem[] = [
    screeningLink('title_abstract', 'Title/abstract', pendingTitleAbstract.value),
    screeningLink('full_text', 'Full text', pendingFullText.value),
  ]
  if (membersStore.isOwner) {
    screening.push(
      link('project-conflicts', 'conflicts', 'Conflicts', {
        count: conflicts.value,
        tone: 'conflict',
        countLabel: 'unresolved',
      })
    )
  }
  const reporting: NavItem[] = [link('project-reports', 'reports', 'Reports')]
  if (membersStore.isOwner) reporting.push(link('project-audit', 'audit', 'Audit'))

  return [
    {
      label: 'Setup',
      items: [
        link('project-overview', 'overview', 'Overview'),
        link('project-criteria', 'criteria', 'Criteria', { count: criteria.value }),
        link('project-articles', 'articles', 'Articles', {
          active: name.value === 'project-articles' || name.value === 'article-detail',
          count: projectsStore.currentProject?.number_of_articles ?? null,
        }),
        link('project-members', 'members', 'Members'),
      ],
    },
    { label: 'Screening', items: screening },
    { label: 'Reporting', items: reporting },
  ]
})

// Keep the active pill visible in the scrollable mobile nav
watch(
  () => groups.value.flatMap((g) => g.items).find((i) => i.active)?.key,
  async () => {
    await nextTick()
    document
      .querySelector('[data-testid="project-pills"] [aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'center' })
  },
  { immediate: true, flush: 'post' }
)

const showCount = (item: NavItem) => item.count !== null && (item.tone !== 'conflict' || item.count > 0)

const countClasses = (item: NavItem, mobile: boolean): string => {
  if (item.tone === 'conflict') return 'bg-uncertain-soft text-uncertain-soft-foreground border border-uncertain/60 font-semibold'
  if (item.tone === 'pending') return 'bg-secondary text-secondary-foreground font-semibold'
  return mobile ? 'text-muted-foreground' : 'text-muted-foreground'
}

const countAria = (item: NavItem) => (item.countLabel ? `${item.count} ${item.countLabel}` : `${item.count}`)
</script>

<template>
  <!-- Desktop sidebar -->
  <aside
    class="sticky top-20 hidden max-h-[calc(100vh-6rem)] w-60 shrink-0 self-start overflow-y-auto lg:block"
    aria-label="Project"
    data-testid="project-sidebar"
  >
    <p
      class="mb-4 truncate px-3 text-sm font-semibold"
      :title="projectsStore.currentProject?.name"
      data-testid="sidebar-project-name"
    >
      {{ projectsStore.currentProject?.name }}
    </p>
    <nav aria-label="Project sections" class="space-y-5">
      <div v-for="group in groups" :key="group.label">
        <p class="mb-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{{ group.label }}</p>
        <ul class="space-y-0.5">
          <li v-for="item in group.items" :key="item.key">
            <router-link
              :to="item.to"
              :aria-current="item.active ? 'page' : undefined"
              class="flex items-center justify-between gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :class="item.active ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'"
            >
              <span class="truncate">{{ item.label }}</span>
              <span
                v-if="showCount(item)"
                class="min-w-5 rounded-full px-1.5 text-center text-xs tabular-nums"
                :class="countClasses(item, false)"
                :aria-label="countAria(item)"
                :data-testid="`nav-count-${item.key}`"
                >{{ item.count }}</span
              >
            </router-link>
          </li>
        </ul>
      </div>
    </nav>
  </aside>

  <!-- Below lg: project name and horizontally scrollable pills -->
  <div class="min-w-0 space-y-2 lg:hidden">
    <p class="truncate text-xl font-bold" :title="projectsStore.currentProject?.name">
      {{ projectsStore.currentProject?.name }}
    </p>
  <nav
    aria-label="Project sections"
    class="-mx-4 overflow-x-auto px-4 pb-1"
    data-testid="project-pills"
  >
    <ul class="flex w-max items-center gap-1.5">
      <template v-for="(group, gi) in groups" :key="group.label">
        <li v-if="gi > 0" aria-hidden="true" class="mx-1 h-5 w-px bg-border" />
        <li v-for="item in group.items" :key="item.key">
          <router-link
            :to="item.to"
            :aria-current="item.active ? 'page' : undefined"
            class="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :class="item.active ? 'border-transparent bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:text-foreground'"
          >
            {{ item.label }}
            <span
              v-if="showCount(item)"
              class="min-w-4 rounded-full px-1 text-center text-xs tabular-nums"
              :class="item.active ? 'bg-primary-foreground/20 text-primary-foreground' : countClasses(item, true)"
              :aria-label="countAria(item)"
              >{{ item.count }}</span
            >
          </router-link>
        </li>
      </template>
    </ul>
  </nav>
  </div>
</template>

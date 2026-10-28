<script setup lang="ts">
import { formatCount, formatDate } from '@/utils/format'
import { formatPrice } from '@/stores/billing'
import type { AdminProject } from '@/types'
import Button from '@/components/ui/Button.vue'
import StateBadge from './StateBadge.vue'

defineProps<{ projects: AdminProject[]; showOwner?: boolean }>()
const emit = defineEmits<{ manage: [project: AdminProject] }>()

const usage = (p: AdminProject) =>
  p.plan ? `${formatCount(p.ai_fulltext_used)} / ${formatCount(p.plan.fulltext_limit)}` : formatCount(p.ai_fulltext_used)
</script>

<template>
  <div class="overflow-x-auto rounded-lg border">
    <table class="w-full text-sm">
      <thead class="bg-muted/50 text-left text-muted-foreground">
        <tr>
          <th class="px-3 py-2 font-medium">Project</th>
          <th v-if="showOwner" class="px-3 py-2 font-medium">Owner</th>
          <th class="px-3 py-2 font-medium">Plan</th>
          <th class="px-3 py-2 text-right font-medium">AI full texts</th>
          <th class="px-3 py-2 font-medium">Ends</th>
          <th class="px-3 py-2 text-right font-medium">Paid</th>
          <th class="px-3 py-2" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="p in projects" :key="p.id" class="border-t" data-testid="admin-project-row">
          <td class="px-3 py-2">
            <div class="font-medium">{{ p.name }}</div>
            <div class="text-xs text-muted-foreground">
              {{ formatCount(p.article_count) }} articles · created {{ formatDate(p.created_at) }}
            </div>
          </td>
          <td v-if="showOwner" class="px-3 py-2">
            <router-link
              v-if="p.owner_email"
              :to="{ name: 'admin-user', params: { userId: p.owner_id } }"
              class="hover:text-primary hover:underline"
            >
              {{ p.owner_email }}
            </router-link>
          </td>
          <td class="px-3 py-2">
            <div class="flex items-center gap-2">
              <StateBadge :state="p.state" />
              <span v-if="p.plan" class="text-xs text-muted-foreground">{{ p.plan.tier }}</span>
            </div>
          </td>
          <td class="px-3 py-2 text-right tabular-nums">{{ usage(p) }}</td>
          <td class="px-3 py-2">{{ p.plan ? formatDate(p.plan.expires_at) : '-' }}</td>
          <td class="px-3 py-2 text-right tabular-nums">
            {{ p.plan?.amount_paid_cents ? formatPrice(p.plan.amount_paid_cents) : '-' }}
          </td>
          <td class="px-3 py-2 text-right">
            <Button size="sm" variant="outline" :data-testid="`manage-${p.id}`" @click="emit('manage', p)">
              {{ p.plan ? 'Manage' : 'Grant pass' }}
            </Button>
          </td>
        </tr>
        <tr v-if="!projects.length">
          <td :colspan="showOwner ? 7 : 6" class="px-3 py-6 text-center text-muted-foreground">
            No projects found
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

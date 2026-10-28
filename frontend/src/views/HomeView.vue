<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { formatPrice } from '@/stores/billing'
import type { PublicPlans } from '@/types'
import PublicHeader from '@/components/layout/PublicHeader.vue'

const authStore = useAuthStore()

// Shown only when configured, so no placeholder address ships
const contactEmail = import.meta.env.VITE_CONTACT_EMAIL

const steps = [
  {
    title: 'Set up your review',
    body: 'Create a project around your review question and import records from RIS or PubMed exports.',
  },
  {
    title: 'Define your criteria',
    body: 'Write inclusion and exclusion criteria (I1, E1, …) with descriptions and rationale, exactly as in your protocol.',
  },
  {
    title: 'Screen with AI assistance',
    body: 'The screening agent reads each full text and assesses every criterion with a confidence score and its reasoning.',
  },
  {
    title: 'Decide as a team',
    body: 'Reviewers confirm or override, conflicts surface automatically, and the final set is ready for reporting.',
  },
]

const features = [
  {
    title: 'Per-criterion AI assessments',
    body: 'Not a black-box score. Every recommendation shows which criteria were met, how confident the agent is, and why.',
  },
  {
    title: 'Automatic full-text retrieval',
    body: 'Open-access PDFs and full texts are fetched from Unpaywall, PubMed Central and Europe PMC. Upload the rest manually.',
  },
  {
    title: 'Dual screening & conflicts',
    body: 'Require one or two independent reviewers. Disagreements are flagged and resolved by the project owner.',
  },
  {
    title: 'PRISMA-ready reporting',
    body: 'PRISMA flow counts, Cohen’s kappa for inter-rater agreement, and CSV or RIS export of your decisions.',
  },
  {
    title: 'Complete audit trail',
    body: 'Every decision, override and resolution is logged, so your methods section can account for every article.',
  },
  {
    title: 'Roles for your team',
    body: 'Owners manage the project, reviewers screen, viewers follow along. Invite supervisors and co-authors with the right access.',
  },
]

interface Plan {
  name: string
  price: string
  prefix?: string
  period?: string
  tagline: string
  tiers?: { label: string; price: string }[]
  items: string[]
  cta: string
  highlighted: boolean
  /** Sold by contact rather than self-service sign-up */
  contactOnly?: boolean
}

// Same values the API enforces; refreshed from /billing/plans when it loads
const pricing = ref<PublicPlans>({
  billing_enabled: true,
  currency: 'eur',
  pass_duration_days: 365,
  free: { fulltext_limit: 50 },
  tiers: [
    { tier: 'pass_250', label: '', fulltext_limit: 250, price_cents: 4900 },
    { tier: 'pass_1000', label: '', fulltext_limit: 1000, price_cents: 12900 },
  ],
})

onMounted(async () => {
  try {
    const res = await axios.get<PublicPlans>('/api/v1/billing/plans')
    if (res.data?.tiers?.length) pricing.value = res.data
  } catch {
    // Keep the built-in prices
  }
})

const count = (n: number) => n.toLocaleString('en')

// Review passes are priced by full-text count, the driver of AI cost
const plans = computed<Plan[]>(() => {
  const { currency, free, tiers } = pricing.value
  const cheapest = Math.min(...tiers.map((t) => t.price_cents))
  const largest = Math.max(...tiers.map((t) => t.fulltext_limit))
  return [
    {
      name: 'Free',
      price: formatPrice(0, currency),
      tagline: 'Try Excludr on a real review.',
      items: [
        `AI screening of ${count(free.fulltext_limit)} full texts`,
        'Title/abstract AI screening included',
        'Single screening',
        'PRISMA & exports',
      ],
      cta: 'Start for free',
      highlighted: false,
    },
    {
      name: 'Review pass',
      prefix: 'from',
      price: formatPrice(cheapest, currency),
      period: 'per review',
      tagline: 'One-off payment for a single systematic review.',
      tiers: [
        ...tiers.map((t) => ({
          label: `Up to ${count(t.fulltext_limit)} full texts`,
          price: formatPrice(t.price_cents, currency),
        })),
        { label: `Over ${count(largest)} full texts`, price: 'Contact us' },
      ],
      items: [
        'Active for 12 months, no subscription',
        'Dual screening with a co-reviewer',
        'PRISMA, exports & audit log',
        'Read-only access and exports forever',
      ],
      cta: 'Start a review',
      highlighted: true,
    },
    {
      name: 'Team',
      price: '€990',
      period: 'per year',
      tagline: 'For groups that run reviews all year.',
      items: [
        'Unlimited reviews',
        'Up to 10 members',
        '5,000 AI-screened full texts / year',
        'Annual invoice & priority support',
      ],
      cta: 'Talk to us',
      highlighted: false,
      contactOnly: true,
    },
  ]
})
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground">
    <PublicHeader />

    <main>
      <!-- Hero -->
      <section class="mx-auto max-w-6xl px-4 py-20 text-center sm:py-28">
        <p class="mb-4 inline-block rounded-full border px-3 py-1 text-xs font-medium text-muted-foreground">
          For systematic reviews and meta-analyses
        </p>
        <h1 class="mx-auto max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
          Full-text screening, with an AI co-reviewer that shows its work
        </h1>
        <p class="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          Excludr screens articles against your inclusion and exclusion criteria, explains every
          assessment, and keeps your team in control of the final decision.
        </p>
        <div class="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <router-link
            :to="authStore.isAuthenticated ? '/dashboard' : '/register'"
            class="inline-flex h-11 items-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            {{ authStore.isAuthenticated ? 'Go to your projects' : 'Start your first review' }}
          </router-link>
          <a href="#how-it-works" class="inline-flex h-11 items-center rounded-md border border-input px-8 text-sm font-medium hover:bg-accent">
            See how it works
          </a>
        </div>

        <!-- Product sketch: one AI assessment -->
        <div class="mx-auto mt-16 max-w-3xl rounded-lg border bg-card p-6 text-left shadow-sm">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b pb-4">
            <div>
              <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">AI recommendation</p>
              <p class="mt-1 font-semibold">Exercise interventions for older adults with chronic pain: an RCT</p>
            </div>
            <span class="rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary">Include · 0.91</span>
          </div>
          <ul class="mt-4 space-y-3 text-sm">
            <li class="flex gap-3">
              <span class="w-8 shrink-0 font-mono font-semibold">I1</span>
              <span class="text-muted-foreground"><span class="font-medium text-foreground">Met (0.95).</span> Participants aged 65+ with pain lasting over three months.</span>
            </li>
            <li class="flex gap-3">
              <span class="w-8 shrink-0 font-mono font-semibold">I2</span>
              <span class="text-muted-foreground"><span class="font-medium text-foreground">Met (0.90).</span> Randomised, parallel-group design with a usual-care control.</span>
            </li>
            <li class="flex gap-3">
              <span class="w-8 shrink-0 font-mono font-semibold">E1</span>
              <span class="text-muted-foreground"><span class="font-medium text-foreground">Not met (0.88).</span> Not a conference abstract; full report available.</span>
            </li>
          </ul>
        </div>
      </section>

      <!-- How it works -->
      <section id="how-it-works" class="border-t bg-muted/40 py-20">
        <div class="mx-auto max-w-6xl px-4">
          <h2 class="text-center text-3xl font-bold">How it works</h2>
          <p class="mx-auto mt-4 max-w-2xl text-center text-muted-foreground">
            From search export to included studies, in one place.
          </p>
          <ol class="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <li v-for="(step, i) in steps" :key="step.title" class="rounded-lg border bg-card p-6">
              <span class="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {{ i + 1 }}
              </span>
              <h3 class="mt-4 font-semibold">{{ step.title }}</h3>
              <p class="mt-2 text-sm text-muted-foreground">{{ step.body }}</p>
            </li>
          </ol>
        </div>
      </section>

      <!-- Features -->
      <section id="features" class="py-20">
        <div class="mx-auto max-w-6xl px-4">
          <h2 class="text-center text-3xl font-bold">Built for methodological rigour</h2>
          <p class="mx-auto mt-4 max-w-2xl text-center text-muted-foreground">
            AI speeds up the work. Your reviewers stay accountable for every decision.
          </p>
          <div class="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <div v-for="feature in features" :key="feature.title" class="rounded-lg border bg-card p-6">
              <h3 class="font-semibold">{{ feature.title }}</h3>
              <p class="mt-2 text-sm text-muted-foreground">{{ feature.body }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- Pricing -->
      <section id="pricing" class="border-t bg-muted/40 py-20">
        <div class="mx-auto max-w-6xl px-4">
          <h2 class="text-center text-3xl font-bold">Pay per review</h2>
          <p class="mx-auto mt-4 max-w-2xl text-center text-muted-foreground">
            No subscription to cancel between reviews. Pay once for the review you are running,
            or take an annual plan if your group reviews all year.
          </p>
          <div class="mt-12 grid gap-6 lg:grid-cols-3">
            <div
              v-for="plan in plans"
              :key="plan.name"
              class="flex flex-col rounded-lg border bg-card p-6"
              :class="plan.highlighted ? 'border-primary ring-1 ring-primary' : ''"
            >
              <h3 class="font-semibold">{{ plan.name }}</h3>
              <p class="mt-1 text-sm text-muted-foreground">{{ plan.tagline }}</p>
              <p class="mt-6">
                <span v-if="plan.prefix" class="mr-1 text-sm text-muted-foreground">{{ plan.prefix }}</span>
                <span class="text-4xl font-bold">{{ plan.price }}</span>
                <span v-if="plan.period" class="ml-1 text-sm text-muted-foreground">{{ plan.period }}</span>
              </p>
              <dl v-if="plan.tiers" class="mt-6 divide-y rounded-md border text-sm">
                <div v-for="tier in plan.tiers" :key="tier.label" class="flex justify-between gap-4 px-3 py-2">
                  <dt class="text-muted-foreground">{{ tier.label }}</dt>
                  <dd class="font-medium">{{ tier.price }}</dd>
                </div>
              </dl>
              <ul class="mt-6 flex-1 space-y-2 text-sm">
                <li v-for="item in plan.items" :key="item" class="flex gap-2">
                  <span class="text-primary" aria-hidden="true">✓</span>
                  <span>{{ item }}</span>
                </li>
              </ul>
              <p
                v-if="plan.contactOnly && !contactEmail"
                class="mt-8 flex h-10 items-center justify-center text-sm text-muted-foreground"
              >
                Available on request
              </p>
              <a
                v-else-if="plan.contactOnly"
                :href="`mailto:${contactEmail}?subject=Excludr%20${plan.name}%20plan`"
                class="mt-8 inline-flex h-10 items-center justify-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-accent"
              >
                {{ plan.cta }}
              </a>
              <router-link
                v-else
                to="/register"
                class="mt-8 inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-medium"
                :class="plan.highlighted
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'border border-input bg-background hover:bg-accent'"
              >
                {{ plan.cta }}
              </router-link>
            </div>
          </div>
          <p class="mt-8 text-center text-sm text-muted-foreground">
            Need more seats, single sign-on or an institutional licence?
            <a v-if="contactEmail" :href="`mailto:${contactEmail}`" class="font-medium text-primary hover:underline">Talk to us.</a>
            <span v-else>Institutional plans are available on request.</span>
          </p>
        </div>
      </section>

      <!-- Closing CTA -->
      <section class="py-20">
        <div class="mx-auto max-w-3xl px-4 text-center">
          <h2 class="text-3xl font-bold">Spend your time on synthesis, not screening</h2>
          <p class="mt-4 text-muted-foreground">
            Set up a project in minutes and let Excludr take the first pass at your full texts.
          </p>
          <router-link
            :to="authStore.isAuthenticated ? '/dashboard' : '/register'"
            class="mt-8 inline-flex h-11 items-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            {{ authStore.isAuthenticated ? 'Go to your projects' : 'Create a free account' }}
          </router-link>
        </div>
      </section>
    </main>

    <footer class="border-t py-8">
      <div class="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-muted-foreground sm:flex-row">
        <p>© {{ new Date().getFullYear() }} Excludr</p>
        <nav class="flex gap-6">
          <a href="#features" class="hover:text-foreground">Features</a>
          <a href="#pricing" class="hover:text-foreground">Pricing</a>
          <a v-if="contactEmail" :href="`mailto:${contactEmail}`" class="hover:text-foreground">Contact</a>
          <router-link to="/login" class="hover:text-foreground">Sign in</router-link>
        </nav>
      </div>
    </footer>
  </div>
</template>

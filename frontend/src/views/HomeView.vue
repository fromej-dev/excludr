<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

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
}

// Review passes are priced by full-text count, the driver of AI cost
const plans: Plan[] = [
  {
    name: 'Free',
    price: '€0',
    tagline: 'Try Excludr on a real review.',
    items: ['1 review', 'Up to 50 full texts', 'AI screening included', '1 reviewer'],
    cta: 'Start for free',
    highlighted: false,
  },
  {
    name: 'Review pass',
    prefix: 'from',
    price: '€49',
    period: 'per review',
    tagline: 'One-off payment for a single systematic review.',
    tiers: [
      { label: 'Up to 250 full texts', price: '€49' },
      { label: 'Up to 1,000 full texts', price: '€129' },
      { label: 'Over 1,000 full texts', price: 'Contact us' },
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
    cta: 'Get started',
    highlighted: false,
  },
]
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <!-- Navigation -->
    <header class="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div class="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <router-link to="/" class="text-xl font-bold">Excludr</router-link>
        <nav class="flex items-center gap-2 sm:gap-6">
          <a href="#how-it-works" class="hidden text-sm font-medium text-muted-foreground hover:text-foreground sm:inline">How it works</a>
          <a href="#features" class="hidden text-sm font-medium text-muted-foreground hover:text-foreground sm:inline">Features</a>
          <a href="#pricing" class="hidden text-sm font-medium text-muted-foreground hover:text-foreground sm:inline">Pricing</a>
          <template v-if="authStore.isAuthenticated">
            <router-link
              to="/dashboard"
              data-testid="home-open-app"
              class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Open app
            </router-link>
          </template>
          <template v-else>
            <router-link to="/login" class="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium hover:bg-accent">
              Sign in
            </router-link>
            <router-link
              to="/register"
              class="inline-flex h-9 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Get started
            </router-link>
          </template>
        </nav>
      </div>
    </header>

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
              <router-link
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
            Updating a review later? Updates cost less than a new pass.
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

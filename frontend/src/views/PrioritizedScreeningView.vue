<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import PublicHeader from '@/components/layout/PublicHeader.vue'

const authStore = useAuthStore()

// Worked example (computed with the app's recall test): 50 relevant records found, every further record excluded
const examples = [
  { target: '95%', missing: 'at most 2', needed: 'about 1,900' },
  { target: '90%', missing: 'at most 5', needed: 'about 1,180' },
  { target: '80%', missing: 'at most 12', needed: 'about 620' },
]

const references = [
  {
    text: 'Callaghan MW, Müller-Hansen F. Statistical stopping criteria for automated screening in systematic reviews. Syst Rev. 2020;9:273.',
    href: 'https://doi.org/10.1186/s13643-020-01521-4',
  },
  {
    text: 'Page MJ, McKenzie JE, Bossuyt PM, et al. The PRISMA 2020 statement: an updated guideline for reporting systematic reviews. BMJ. 2021;372:n71.',
    href: 'https://doi.org/10.1136/bmj.n71',
  },
]
</script>

<template>
  <div class="min-h-dvh bg-background text-foreground">
    <PublicHeader />

    <main class="mx-auto max-w-3xl px-4 py-16 sm:py-20">
      <p class="text-sm font-medium text-primary">Methods</p>
      <h1 class="mt-2 text-4xl font-bold tracking-tight">Prioritized screening and stopping rules</h1>
      <p class="mt-6 text-lg text-muted-foreground">
        Most records found by a systematic search are irrelevant. Prioritized screening shows your
        team the likely relevant titles and abstracts first, so relevant studies turn up early. A
        stopping rule then tells you when it is reasonable to stop, and Excludr reports exactly what
        you did so your methods section can account for it.
      </p>
      <p class="mt-4 text-sm text-muted-foreground">
        It is optional and off by default. The project owner turns it on per review, and it only
        changes title/abstract screening; full-text screening works as before.
      </p>

      <section class="mt-14" aria-labelledby="ranking">
        <h2 id="ranking" class="text-2xl font-semibold">How records are ranked</h2>
        <ul class="mt-4 list-disc space-y-3 pl-5 text-muted-foreground">
          <li>
            Excludr learns from your reviewers' title/abstract decisions with a simple, transparent
            model: word frequencies (TF-IDF) of titles, abstracts and keywords, and a logistic regression
            classifier. The queue is re-ranked in the background as decisions come in.
          </li>
          <li>
            Only human decisions train the ranking. AI screening verdicts are never used, and no language
            model is called, so ranking costs nothing and does not count towards your review pass.
          </li>
          <li>
            Before the first include and exclude, records are ordered by their similarity to your review
            question and inclusion criteria. You can also ask for a number of records in random order first.
          </li>
          <li>
            With dual screening, a record only trains the model once it is settled (both reviewers agree or
            the owner resolves it), so the order of one reviewer's queue never reveals how the other voted.
          </li>
        </ul>
      </section>

      <section class="mt-14" aria-labelledby="stopping">
        <h2 id="stopping" class="text-2xl font-semibold">Deciding when to stop</h2>
        <p class="mt-4 text-muted-foreground">Choose one of two rules, and state it in your protocol before screening starts.</p>

        <div class="mt-6 grid gap-4 sm:grid-cols-2">
          <div class="rounded-lg border bg-card p-6">
            <h3 class="font-semibold">Consecutive exclusions</h3>
            <p class="mt-2 text-sm text-muted-foreground">
              Stop after a set number of records in a row were excluded, for example 100. Simple and
              widely used, but a heuristic: it gives no guarantee about how many relevant records remain.
            </p>
          </div>
          <div class="rounded-lg border bg-card p-6">
            <h3 class="font-semibold">Statistical stopping criterion</h3>
            <p class="mt-2 text-sm text-muted-foreground">
              Stop when a hypothesis test shows your recall target has been reached, for example 95%
              recall at a significance level of 0.05 (Callaghan and Müller-Hansen, 2020).
            </p>
          </div>
        </div>

        <h3 class="mt-10 text-lg font-semibold">How the statistical test works</h3>
        <p class="mt-3 text-muted-foreground">
          The test starts from the hypothesis that recall is still below your target. Given the relevant
          records found so far, that would mean at least a certain number of relevant records are still
          unscreened. Excludr then asks how likely it would be, if they were, to see as few relevant records
          as you did among the records screened most recently. When that probability (the p-value) falls
          below your significance level, the hypothesis is rejected and the rule is met. The screening view
          shows the current p-value as you go, for example “Recall ≥ 95% not yet shown (p = 0.21)”.
        </p>
        <p class="mt-3 text-muted-foreground">
          The recently screened records came from the top of a ranked queue, so they are, if anything,
          more likely to be relevant than the records left. Treating them as a random sample of the
          records not yet screened is therefore conservative, which is the argument the method rests on.
          Excludr tests every run of most recently screened records and uses the smallest p-value, as in
          the original method.
        </p>

        <h3 class="mt-10 text-lg font-semibold">What it asks of you</h3>
        <p class="mt-3 text-muted-foreground">
          The statistical rule is demanding, and that is what makes it defensible. Suppose you have found 50
          relevant records and 3,000 are still unscreened. If every further record is excluded, the rule is
          met after:
        </p>
        <div class="mt-4 overflow-x-auto rounded-lg border">
          <table class="w-full text-left text-sm">
            <thead class="bg-muted/50 text-muted-foreground">
              <tr>
                <th scope="col" class="px-4 py-2 font-medium">Recall target</th>
                <th scope="col" class="px-4 py-2 font-medium">Relevant records that may be missed</th>
                <th scope="col" class="px-4 py-2 font-medium">Further exclusions needed</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr v-for="row in examples" :key="row.target">
                <td class="px-4 py-2 font-medium">{{ row.target }}</td>
                <td class="px-4 py-2">{{ row.missing }}</td>
                <td class="px-4 py-2">{{ row.needed }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="mt-3 text-sm text-muted-foreground">
          Significance level 0.05. The more relevant records you have found, the larger the share of the
          remainder the rule lets you leave: with 100 found and 10,000 unscreened, about 3,930 further
          exclusions meet a 95% target.
        </p>
      </section>

      <section class="mt-14" aria-labelledby="applying">
        <h2 id="applying" class="text-2xl font-semibold">When the rule is met</h2>
        <ul class="mt-4 list-disc space-y-3 pl-5 text-muted-foreground">
          <li>
            Nothing is closed automatically. The project owner reviews the numbers and confirms.
          </li>
          <li>
            Only records nobody has voted on are closed, as “not screened (stopping rule)”. Records with a
            vote, a conflict or an uncertain decision stay open for your team to finish.
          </li>
          <li>
            Closing is reversible: the owner can reopen the records at any time. Records imported later
            are screened as usual, and the rule starts counting again.
          </li>
          <li>
            The owner can also stop before the rule is met, but only with a written reason, which is kept
            in the audit log.
          </li>
        </ul>
      </section>

      <section class="mt-14" aria-labelledby="reporting">
        <h2 id="reporting" class="text-2xl font-semibold">How it is reported</h2>
        <ul class="mt-4 list-disc space-y-3 pl-5 text-muted-foreground">
          <li>
            In the PRISMA 2020 flow diagram, records closed by the stopping rule appear under “records
            removed before screening: marked as ineligible by automation tools”, the box PRISMA provides for
            this. They are not counted as exclusions by your reviewers.
          </li>
          <li>
            The Reports page drafts a methods paragraph that names the ranking model, the stopping rule and,
            for the statistical rule, the recall target, significance level, p-value and reference. Treat it
            as suggested wording and check it against your protocol.
          </li>
          <li>
            CSV and RIS exports mark these records “Not screened (stopping rule)” and include each record's
            relevance score. The audit log records every setting change, application and reopening.
          </li>
        </ul>
      </section>

      <section class="mt-14" aria-labelledby="limits">
        <h2 id="limits" class="text-2xl font-semibold">Good practice and limitations</h2>
        <ul class="mt-4 list-disc space-y-3 pl-5 text-muted-foreground">
          <li>Register the stopping rule and its settings in your protocol before you start screening.</li>
          <li>
            The consecutive-exclusions rule is a heuristic. The statistical rule rests on the assumption
            above about ranked records, and the test is repeated as screening goes on.
          </li>
          <li>Neither rule is proof that no relevant study was missed; consider screening a random sample of the remaining records as an extra check.</li>
          <li>For small searches of a few hundred records, screening everything is often simpler.</li>
        </ul>
      </section>

      <section class="mt-14" aria-labelledby="references">
        <h2 id="references" class="text-2xl font-semibold">References</h2>
        <ol class="mt-4 list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
          <li v-for="ref in references" :key="ref.href">
            {{ ref.text }}
            <a :href="ref.href" class="font-medium text-primary hover:underline" target="_blank" rel="noopener">{{ ref.href.replace('https://', '') }}</a>
          </li>
        </ol>
      </section>

      <div class="mt-16 rounded-lg border bg-muted/40 p-8 text-center">
        <h2 class="text-2xl font-semibold">Try it on your next review</h2>
        <p class="mt-2 text-muted-foreground">Turn on prioritized screening in a project's settings.</p>
        <router-link
          :to="authStore.isAuthenticated ? '/dashboard' : '/register'"
          class="mt-6 inline-flex h-11 items-center rounded-md bg-primary px-8 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {{ authStore.isAuthenticated ? 'Go to your projects' : 'Create a free account' }}
        </router-link>
      </div>
    </main>

    <footer class="border-t py-8">
      <div class="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-muted-foreground sm:flex-row">
        <p>© {{ new Date().getFullYear() }} Excludr</p>
        <nav class="flex gap-6">
          <router-link to="/" class="hover:text-foreground">Home</router-link>
          <router-link :to="{ path: '/', hash: '#pricing' }" class="hover:text-foreground">Pricing</router-link>
          <router-link to="/login" class="hover:text-foreground">Sign in</router-link>
        </nav>
      </div>
    </footer>
  </div>
</template>

/**
 * Fictional demo review used for the homepage screenshots.
 *
 * Every article, author and journal here is invented. Do not replace them with real
 * records: the screenshots are public marketing material.
 */

export type Vote = 'include' | 'exclude' | 'uncertain'
export type Code = 'I1' | 'I2' | 'I3' | 'I4' | 'E1' | 'E2'

export const owner = { name: 'Sofia Martens', email: 'sofia.martens@demo.excludr.test', password: 'DemoPass123!' }
export const reviewer = { name: 'Daniel Okafor', email: 'daniel.okafor@demo.excludr.test', password: 'DemoPass123!' }

export const project = {
  name: 'Exercise for chronic pain 65+',
  description: 'Systematic review of exercise interventions for older adults with chronic musculoskeletal pain.',
  review_question:
    'In adults aged 65 and over with chronic musculoskeletal pain, do structured exercise programmes reduce pain and improve physical function compared with usual care?',
}

export const criteria: { type: 'inclusion' | 'exclusion'; code: Code; description: string; rationale: string }[] = [
  {
    type: 'inclusion',
    code: 'I1',
    description: 'Adults aged 65 or older with musculoskeletal pain lasting at least three months',
    rationale: 'Target population of the review question.',
  },
  {
    type: 'inclusion',
    code: 'I2',
    description: 'Structured exercise programme (supervised or home-based) lasting at least four weeks',
    rationale: 'Shorter or unstructured activity advice is not comparable.',
  },
  {
    type: 'inclusion',
    code: 'I3',
    description: 'Randomised controlled trial',
    rationale: 'Only randomised evidence is pooled in the meta-analysis.',
  },
  {
    type: 'inclusion',
    code: 'I4',
    description: 'Reports pain intensity or physical function as an outcome',
    rationale: 'Primary outcomes of the review.',
  },
  {
    type: 'exclusion',
    code: 'E1',
    description: 'Conference abstract, protocol or trial registration without results',
    rationale: 'Insufficient data for extraction and risk-of-bias assessment.',
  },
  {
    type: 'exclusion',
    code: 'E2',
    description: 'Pain caused by cancer, recent surgery or acute injury',
    rationale: 'Different pain mechanisms and care pathways.',
  },
]

/** Per-criterion AI result: met (true/false/null for unclear) with confidence and, optionally, reasoning. */
export type Assessment = [met: boolean | null, confidence: number, reasoning?: string]

export interface AiVerdict {
  decision: Vote
  confidence: number
  summary: string
  exclusionReason?: string
  criteria: Record<Code, Assessment>
}

export interface DemoArticle {
  title: string
  authors: string[]
  year: number
  journal: string
  abstract: string
  keywords?: string[]
  /** Title/abstract votes: [owner, reviewer]. */
  ta: [Vote, Vote]
  /** Owner's resolution when the title/abstract votes disagree. */
  taResolution?: Vote
  aiTa: AiVerdict
  /** Full-text body (sections) for articles that pass title/abstract; null when it cannot be retrieved. */
  fullText?: string[] | null
  /** Full-text votes: [owner, reviewer]; null leaves that reviewer undecided. */
  ft?: [Vote | null, Vote | null]
  aiFt?: AiVerdict
  /** Reviewer notes for full-text decisions, shown on the conflicts page. */
  ftNotes?: [string, string]
  /** Exclusion reason reviewers give at full text (PRISMA "reports excluded" breakdown). */
  ftReason?: string
}

const met = (c: number): Assessment => [true, c]
const notMet = (c: number): Assessment => [false, c]
const unclear = (c: number): Assessment => [null, c]

const allMet: Record<Code, Assessment> = {
  I1: met(0.9),
  I2: met(0.88),
  I3: met(0.93),
  I4: met(0.9),
  E1: notMet(0.94),
  E2: notMet(0.9),
}

const include = (summary: string, confidence = 0.86, overrides: Partial<Record<Code, Assessment>> = {}): AiVerdict => ({
  decision: 'include',
  confidence,
  summary,
  criteria: { ...allMet, ...overrides },
})

const exclude = (
  summary: string,
  exclusionReason: string,
  overrides: Partial<Record<Code, Assessment>>,
  confidence = 0.9
): AiVerdict => ({
  decision: 'exclude',
  confidence,
  summary,
  exclusionReason,
  criteria: { ...allMet, ...overrides },
})

const uncertain = (summary: string, overrides: Partial<Record<Code, Assessment>>, confidence = 0.55): AiVerdict => ({
  decision: 'uncertain',
  confidence,
  summary,
  criteria: { ...allMet, ...overrides },
})

/** Generic full-text body for the articles that are not on screen. */
const body = (design: string, sample: string, intervention: string, result: string): string[] => [
  `Methods. ${design}`,
  `Participants. ${sample}`,
  `Intervention. ${intervention}`,
  `Results. ${result}`,
  'Discussion. The findings are discussed in the context of current guidance for the management of persistent pain in later life, together with the limitations of the trial and implications for practice.',
]

/** The article shown in the screening screenshot. Keep it first in the queue (see capture.spec.ts). */
export const heroTitle =
  'Supervised progressive resistance training versus usual care for chronic low back pain in adults aged 65 and over: a randomised controlled trial'

export const articles: DemoArticle[] = [
  {
    title: heroTitle,
    authors: ['Lindqvist, Maja', 'Haddad, Omar', 'Brouwer, Anne', 'Castell, Pau'],
    year: 2024,
    journal: 'Journal of Ageing and Musculoskeletal Care',
    abstract:
      'Background: Chronic low back pain is common in later life, yet trials of resistance training rarely enrol adults over 65. Methods: We randomised 212 community-dwelling adults aged 65 to 89 with low back pain of at least three months to 12 weeks of supervised progressive resistance training (two sessions per week) or usual care. Primary outcomes were pain intensity (0–10 numeric rating scale) and physical function (Roland-Morris Disability Questionnaire) at 12 weeks. Results: Pain decreased by 1.6 points more in the training group (95% CI 1.0 to 2.2) and disability by 3.1 points (95% CI 1.9 to 4.3). Adherence was 81%; no serious adverse events were attributed to training. Conclusions: Supervised resistance training is safe and reduces pain and disability in older adults with chronic low back pain.',
    keywords: ['resistance training', 'low back pain', 'older adults', 'randomised controlled trial'],
    ta: ['include', 'include'],
    aiTa: include('Older adults with chronic low back pain randomised to resistance training; pain and function reported.', 0.92),
    fullText: [
      'Methods',
      'Design. This was a two-arm, parallel-group, assessor-blinded randomised controlled trial conducted at three community physiotherapy centres. Participants were allocated 1:1 by a computer-generated sequence with permuted blocks of four, concealed in a central web system.',
      'Participants. Eligible participants were community-dwelling adults aged 65 years or older with non-specific low back pain on most days for at least three months and a mean pain intensity of 3 or more on a 0–10 numeric rating scale. We excluded people with suspected serious spinal pathology, a history of cancer in the past five years, spinal surgery within 12 months, or a fracture in the previous six months.',
      'Intervention. The training group attended two supervised 60-minute sessions per week for 12 weeks. Each session included a warm-up and five machine and free-weight exercises for the trunk and lower limbs, progressed from 50% to 75% of one-repetition maximum. The control group continued usual care from their general practitioner, with written advice on staying active.',
      'Outcomes. The co-primary outcomes were pain intensity (numeric rating scale) and back-specific physical function (Roland-Morris Disability Questionnaire) at 12 weeks. Secondary outcomes included gait speed, the Timed Up and Go test, fear of movement and adverse events.',
      'Results',
      'Of 348 people screened, 212 were randomised (mean age 72.4 years, 61% women); 196 (92%) completed the 12-week assessment. Mean pain intensity fell from 5.8 to 3.4 in the training group and from 5.7 to 4.9 with usual care (adjusted difference −1.6, 95% CI −2.2 to −1.0). The Roland-Morris score improved by 3.1 points more with training (95% CI 1.9 to 4.3). Participants attended 81% of planned sessions. Eleven minor adverse events (transient muscle soreness) occurred in the training group.',
      'Discussion',
      'In this trial, supervised progressive resistance training produced clinically relevant reductions in pain and disability compared with usual care in adults aged 65 and over with chronic low back pain.',
    ],
    ft: [null, 'include'],
    aiFt: include(
      'Randomised trial in adults aged 65+ with low back pain of at least three months; 12-week supervised resistance programme versus usual care, reporting pain (NRS) and function (RMDQ). No exclusion criterion applies.',
      0.94,
      {
        I1: [true, 0.96, 'Participants were community-dwelling adults aged 65 or older (mean age 72.4) with non-specific low back pain on most days for at least three months.'],
        I2: [true, 0.95, 'Two supervised 60-minute resistance sessions per week for 12 weeks, progressed from 50% to 75% of one-repetition maximum.'],
        I3: [true, 0.98, 'Two-arm, parallel-group, assessor-blinded RCT with computer-generated, centrally concealed allocation.'],
        I4: [true, 0.97, 'Co-primary outcomes were pain intensity (0–10 NRS) and the Roland-Morris Disability Questionnaire at 12 weeks.'],
        E1: [false, 0.97, 'Full report of a completed trial with results; not an abstract, protocol or registration.'],
        E2: [false, 0.9, 'People with recent cancer, spinal surgery within 12 months or a recent fracture were excluded, so pain is not post-surgical, cancer-related or acute.'],
      }
    ),
  },
  {
    title: 'Home-based strength and balance exercise for knee osteoarthritis pain in older adults: a pragmatic randomised trial',
    authors: ['Moreau, Claire', 'Adeyemi, Tunde', 'Visser, Joost'],
    year: 2023,
    journal: 'Clinical Rehabilitation in Older Age',
    abstract:
      'We randomised 164 adults aged 65 and over with painful knee osteoarthritis to a 16-week home exercise programme with telephone coaching or to usual care. Knee pain and function (WOMAC) improved more with exercise at 16 weeks.',
    ta: ['include', 'include'],
    aiTa: include('RCT of a 16-week home exercise programme in adults aged 65+ with knee osteoarthritis pain.', 0.9),
    fullText: body(
      'Pragmatic parallel-group randomised controlled trial with blinded outcome assessment.',
      '164 adults aged 65 to 86 with knee pain on most days for at least six months and radiographic osteoarthritis.',
      'Sixteen weeks of home strength and balance exercise, three times weekly, with fortnightly telephone coaching.',
      'WOMAC pain improved by 2.3 points more than usual care (95% CI 1.1 to 3.5); function improved similarly.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Older adults with chronic knee pain; 16-week home exercise vs usual care; pain and function reported.', 0.93),
  },
  {
    title: 'Tai chi versus aerobic exercise for chronic widespread pain in older women: a randomised comparative effectiveness trial',
    authors: ['Chen, Wei', 'Albrecht, Hanna', 'Okoro, Grace'],
    year: 2022,
    journal: 'Journal of Integrative Geriatric Medicine',
    abstract:
      'Women aged 65 and over with chronic widespread pain were randomised to 24 weeks of tai chi or aerobic exercise. Both groups improved; tai chi produced larger improvements in pain interference.',
    ta: ['include', 'include'],
    aiTa: include('Randomised trial of two structured exercise programmes in older women with chronic widespread pain.', 0.84),
    fullText: body(
      'Randomised comparative effectiveness trial with two active arms.',
      '138 women aged 65 or over with widespread pain for at least three months.',
      'Twenty-four weeks of twice-weekly supervised tai chi or moderate-intensity aerobic exercise.',
      'Pain interference decreased in both arms, more with tai chi (difference 0.8, 95% CI 0.2 to 1.4).'
    ),
    ft: ['include', 'exclude'],
    ftNotes: [
      'Both arms are structured exercise and the population and outcomes fit. The protocol does not require a usual-care comparator, so the trial is eligible.',
      'No usual-care or non-exercise control, so this cannot answer our comparison. Exclude, or keep only for the narrative synthesis?',
    ],
    aiFt: include(
      'Both arms deliver structured exercise for 24 weeks in women aged 65+ with chronic widespread pain; comparator is active rather than usual care.',
      0.71,
      { I2: [true, 0.82, 'Twenty-four weeks of supervised tai chi or aerobic exercise.'] }
    ),
  },
  {
    title: 'Aquatic exercise and pain in adults over 70 with hip osteoarthritis: a randomised controlled trial',
    authors: ['Rossi, Giulia', 'Nakamura, Ken', 'de Wit, Sanne'],
    year: 2023,
    journal: 'Ageing and Physical Activity Review',
    abstract:
      'Adults over 70 with hip osteoarthritis were randomised to 12 weeks of supervised aquatic exercise or a waiting list. Hip pain and walking ability improved with aquatic exercise.',
    ta: ['include', 'include'],
    aiTa: include('RCT of a 12-week aquatic exercise programme in adults over 70 with hip osteoarthritis.', 0.89),
    fullText: body(
      'Two-arm randomised controlled trial with a waiting-list control.',
      '96 adults aged 70 to 91 with hip pain for at least six months.',
      'Twelve weeks of supervised aquatic exercise, twice weekly, 45 minutes per session.',
      'Hip pain fell by 1.4 points more than with the waiting list; six-minute walk distance improved by 38 metres.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Adults over 70 with chronic hip pain; 12-week aquatic exercise vs waiting list; pain and walking reported.', 0.91),
  },
  {
    title: 'Yoga for chronic neck pain in older adults: a randomised trial with 12-month follow-up',
    authors: ['Sharma, Priya', 'Lindgren, Erik'],
    year: 2021,
    journal: 'Complementary Therapies in Later Life',
    abstract:
      'Adults aged 65 and older with chronic neck pain were randomised to ten weeks of yoga or a self-care booklet. Neck pain and disability improved more with yoga, sustained at 12 months.',
    ta: ['include', 'include'],
    aiTa: include('Older adults with chronic neck pain randomised to 10 weeks of yoga or self-care.', 0.86),
    fullText: body(
      'Randomised controlled trial with 12-month follow-up.',
      '120 adults aged 65 or over with neck pain for at least three months.',
      'Ten weekly 75-minute yoga classes with home practice.',
      'Neck pain intensity decreased by 1.9 points more than with self-care at ten weeks and by 1.3 points at 12 months.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Chronic neck pain in adults 65+; structured yoga programme vs self-care; pain and disability outcomes.', 0.9),
  },
  {
    title: 'Walking programmes for chronic low back pain in adults aged 60 to 85: a randomised trial',
    authors: ['Fitzgerald, Aoife', 'Mensah, Kwame', 'Hartmann, Lena'],
    year: 2022,
    journal: 'Journal of Ageing and Musculoskeletal Care',
    abstract:
      'Adults aged 60 to 85 with chronic low back pain were randomised to a progressive walking programme or education. Disability improved with walking at 12 weeks.',
    ta: ['include', 'include'],
    aiTa: uncertain('Walking programme RCT in chronic low back pain; the age range starts at 60, so part of the sample may be under 65.', {
      I1: unclear(0.52),
    }),
    fullText: body(
      'Randomised controlled trial.',
      '180 adults aged 60 to 85 (mean 69.8) with low back pain for at least three months; results reported separately for participants aged 65 and over.',
      'Twelve weeks of progressive, pedometer-guided walking with weekly group sessions.',
      'In participants aged 65 and over, disability improved by 2.4 points more than with education.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Subgroup data for participants aged 65+ are reported; structured walking programme vs education.', 0.78, {
      I1: met(0.74),
    }),
  },
  {
    title: 'Group exercise versus physiotherapy advice for chronic shoulder pain in older adults: a feasibility randomised trial',
    authors: ['Novak, Petra', 'Ibrahim, Yusuf'],
    year: 2024,
    journal: 'Pilot and Feasibility Studies in Rehabilitation',
    abstract:
      'This feasibility trial randomised 48 adults aged 65 and over with chronic shoulder pain to group exercise or advice. Recruitment, retention and acceptability were assessed; pain was a secondary outcome.',
    ta: ['include', 'uncertain'],
    taResolution: 'include',
    aiTa: include('Feasibility RCT in older adults with chronic shoulder pain; pain reported as a secondary outcome.', 0.74),
    fullText: body(
      'Feasibility randomised controlled trial.',
      '48 adults aged 65 or over with shoulder pain for at least three months.',
      'Eight weeks of twice-weekly group shoulder exercise.',
      'Feasibility targets were met. Pain intensity was reported descriptively without a formal comparison.'
    ),
    ft: ['exclude', 'include'],
    ftNotes: [
      'Feasibility trial; pain only reported descriptively with no between-group estimate. Too little data to extract.',
      'It is randomised and reports pain at eight weeks, so I4 is met. Low weight in the meta-analysis, but eligible.',
    ],
    aiFt: uncertain('Randomised feasibility trial; pain is reported only descriptively, so it is unclear whether usable outcome data are available.', {
      I4: unclear(0.48),
    }),
  },
  {
    title: 'Pilates for chronic low back pain in older adults: a randomised trial',
    authors: ['Santos, Mariana', 'Berg, Thomas'],
    year: 2020,
    journal: 'Physiotherapy Practice in Older Age',
    abstract:
      'Adults aged 65 and over with chronic low back pain were randomised to eight weeks of Pilates or no intervention. Pain and disability improved with Pilates.',
    ta: ['include', 'include'],
    aiTa: include('RCT of eight weeks of Pilates in older adults with chronic low back pain.', 0.88),
    fullText: body(
      'Randomised controlled trial.',
      '72 adults aged 65 to 80 with low back pain for at least three months.',
      'Eight weeks of supervised mat Pilates, twice weekly.',
      'Pain decreased by 1.7 points more than in the control group.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Older adults with chronic low back pain; 8-week Pilates vs no intervention; pain and disability.', 0.9),
  },
  {
    title: 'Exercise after total knee replacement in adults over 65: a randomised trial of two rehabilitation programmes',
    authors: ['Kowalski, Marek', 'Ahmed, Leila'],
    year: 2023,
    journal: 'Orthopaedic Rehabilitation Journal',
    abstract:
      'Adults over 65 were randomised to supervised or home-based rehabilitation exercise in the six weeks after total knee replacement. Pain and function were similar between groups.',
    ta: ['include', 'exclude'],
    taResolution: 'include',
    aiTa: exclude('Post-operative rehabilitation after knee replacement; pain is post-surgical.', 'E2: pain after recent surgery', {
      E2: met(0.83),
    }, 0.8),
    fullText: body(
      'Randomised controlled trial of two post-operative programmes.',
      '140 adults aged 65 or over in the first week after total knee replacement.',
      'Six weeks of supervised or home-based rehabilitation exercise.',
      'Pain and function did not differ between programmes at six weeks.'
    ),
    ft: ['exclude', 'exclude'],
    ftReason: 'E2: pain after recent surgery',
    aiFt: exclude('All participants were within six weeks of total knee replacement, so pain is post-surgical.', 'E2: pain after recent surgery', {
      E2: met(0.95),
    }, 0.93),
  },
  {
    title: 'Resistance band training and knee pain in older adults with obesity: a randomised controlled trial',
    authors: ['Olsen, Ingrid', 'Bello, Chidi', 'Ramos, Lucía'],
    year: 2021,
    journal: 'Obesity and Ageing',
    abstract:
      'Adults aged 65 and over with obesity and chronic knee pain were randomised to 12 weeks of resistance band training or diet advice. Knee pain improved with training.',
    ta: ['include', 'include'],
    aiTa: include('RCT of resistance band training in older adults with chronic knee pain.', 0.87),
    fullText: body(
      'Randomised controlled trial.',
      '110 adults aged 65 to 84 with a body mass index of 30 or more and knee pain for at least three months.',
      'Twelve weeks of home resistance band exercise with monthly supervised sessions.',
      'Knee pain decreased by 1.2 points more than with diet advice alone.'
    ),
    ft: ['include', 'include'],
    aiFt: include('Older adults with chronic knee pain; 12-week resistance band programme vs diet advice; pain reported.', 0.89),
  },
  {
    title: 'Hydrotherapy for chronic pain in nursing home residents: a cluster randomised trial',
    authors: ['Dubois, Hélène', 'Patel, Ravi'],
    year: 2019,
    journal: 'Journal of Long-Term Care Research',
    abstract:
      'Nursing homes were randomised to offer weekly hydrotherapy or usual activities to residents with chronic pain for 16 weeks. Pain scores were assessed with an observational scale.',
    ta: ['include', 'include'],
    aiTa: include('Cluster RCT of hydrotherapy for chronic pain in nursing home residents.', 0.8),
    fullText: body(
      'Cluster randomised trial in 14 nursing homes.',
      '212 residents aged 65 or over with chronic pain documented for at least three months.',
      'Sixteen weeks of weekly group hydrotherapy sessions of 30 minutes.',
      'Observed pain scores did not differ significantly between arms.'
    ),
    ft: ['exclude', 'exclude'],
    ftReason: 'I2: not a structured exercise programme',
    aiFt: exclude('Weekly 30-minute hydrotherapy is passive immersion rather than a structured exercise programme.', 'I2: not a structured exercise programme', {
      I2: notMet(0.81),
    }, 0.79),
  },
  {
    title: 'Nordic walking for chronic hip and knee pain in older adults: a randomised trial',
    authors: ['Virtanen, Aino', 'Schmidt, Felix'],
    year: 2022,
    journal: 'Ageing and Physical Activity Review',
    abstract:
      'Adults aged 65 and over with chronic hip or knee pain were randomised to 12 weeks of Nordic walking or usual care. Pain improved modestly with Nordic walking.',
    ta: ['include', 'include'],
    aiTa: include('RCT of Nordic walking in older adults with chronic hip or knee pain.', 0.87),
    fullText: null,
  },
  // Excluded at title/abstract
  ...(
    [
      ['Prevalence of chronic musculoskeletal pain in adults over 65: a population survey', 'Cross-sectional survey; no intervention.', 'I3: not a randomised trial', { I2: notMet(0.95), I3: notMet(0.97) }],
      ['Opioid prescribing for older adults with chronic back pain: a cohort study', 'Observational cohort of opioid prescribing.', 'I2: no exercise intervention', { I2: notMet(0.96), I3: notMet(0.95) }],
      ['Exercise for cancer-related pain in older survivors: a randomised trial', 'Pain is cancer-related.', 'E2: cancer-related pain', { E2: met(0.94) }],
      ['Resistance training for chronic back pain in adults aged 18 to 50: a randomised trial', 'Participants are aged 18 to 50.', 'I1: wrong age group', { I1: notMet(0.96) }],
      ['Protocol for a randomised trial of yoga for knee osteoarthritis in older adults', 'Trial protocol without results.', 'E1: protocol without results', { E1: met(0.97) }],
      ['Physiotherapist experiences of delivering exercise to older adults with pain: a qualitative study', 'Qualitative interview study.', 'I3: not a randomised trial', { I3: notMet(0.97), I4: notMet(0.9) }],
      ['Acupuncture versus sham for chronic neck pain in older adults: a randomised trial', 'Intervention is acupuncture, not exercise.', 'I2: no exercise intervention', { I2: notMet(0.95) }],
      ['Balance training after hip fracture: a randomised controlled trial', 'Pain follows an acute injury (hip fracture).', 'E2: acute injury', { E2: met(0.88), I4: unclear(0.5) }],
      ['Exercise and chronic pain in older adults: abstracts from an annual scientific meeting', 'Conference abstracts.', 'E1: conference abstract', { E1: met(0.96) }],
      ['Massage therapy for chronic low back pain in adults over 65: a randomised trial', 'Intervention is massage, not exercise.', 'I2: no exercise intervention', { I2: notMet(0.94) }],
      ['A single exercise education session for older adults with knee pain: a randomised trial', 'One education session; not a programme of at least four weeks.', 'I2: programme shorter than four weeks', { I2: notMet(0.86) }],
    ] as [string, string, string, Partial<Record<Code, Assessment>>][]
  ).map(([title, summary, reason, overrides], i): DemoArticle => ({
    title,
    authors: [['Jansen, Pieter', 'Wright, Emma'], ['Kaur, Simran', 'Novak, Tomas'], ['Garcia, Elena', 'Muller, Jan']][i % 3],
    year: 2018 + (i % 7),
    journal: ['Journal of Ageing and Musculoskeletal Care', 'Clinical Rehabilitation in Older Age', 'Ageing and Physical Activity Review'][i % 3],
    abstract: `${summary} Further details are given in the full report.`,
    ta: ['exclude', 'exclude'],
    aiTa: exclude(summary, reason, overrides),
  })),
  {
    title: 'Dance-based exercise and chronic pain in older adults: a non-randomised controlled study',
    authors: ['Ferreira, Ana', 'Lee, Min-jun'],
    year: 2021,
    journal: 'Arts and Health in Ageing',
    abstract:
      'Older adults with chronic pain chose between a 12-week dance programme and usual activities. Pain improved in the dance group.',
    ta: ['exclude', 'include'],
    taResolution: 'exclude',
    aiTa: exclude('Participants chose their group; allocation was not randomised.', 'I3: not a randomised trial', { I3: notMet(0.88) }, 0.86),
  },
]

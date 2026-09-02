// Regenerates scoring_parity.json by EXECUTING frontend/src/lib/scoring.js, so
// the fixtures are what the browser actually computes rather than a reading of
// the source. Run from the Journeyman root:
//
//   node backend/tests/fixtures/generate_scoring_parity.mjs \
//       > backend/tests/fixtures/scoring_parity.json
//
// scoring.js uses ESM syntax but frontend/package.json has no "type": "module",
// so Node would load it as CommonJS and fail. Reading the source and importing
// it as a data: URL sidesteps that without touching the frontend's config.

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(here, '../../../frontend/src/lib/scoring.js'), 'utf8')
const { calculate_score, calculate_streaks } =
  await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'))

const cases = []
for (const result of ['win', 'loss'])
  for (const time_seconds of [0, 1, 29, 30, 31, 60, 120, 500, 930, 1000, 10000])
    for (const wrong_guesses of [0, 1, 2, 3])
      for (const hint_used of [false, true])
        for (const hard_mode of [false, true])
          cases.push({
            input: { result, time_seconds, wrong_guesses, hint_used, hard_mode },
            expected: calculate_score({ result, time_seconds, wrong_guesses, hint_used, hard_mode }),
          })

const streaks = []
const seqs = [
  [], ['win'], ['loss'],
  ['win','win','loss','win'], ['loss','win','win','win'],
  ['win','loss','win','win','win','loss'], ['win','win','win','loss','win'],
  ['loss','loss'], ['win','win','win','win'], ['win','loss','loss','win','win'],
]
for (const s of seqs) {
  const games = s.map(r => ({ result: r }))
  streaks.push({ input: s, expected: calculate_streaks(games) })
}

console.log(JSON.stringify({ score: cases, streaks }, null, 1))

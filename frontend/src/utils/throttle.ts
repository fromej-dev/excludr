export interface Throttled {
  /** Run now if the last run was at least `waitMs` ago, otherwise once at the end of the window. */
  call: () => void
  /** Drop any scheduled run and run now. */
  flush: () => void
  /** Drop any scheduled run. */
  cancel: () => void
}

/**
 * Leading + trailing throttle: `fn` runs at most once per `waitMs`, and a call inside the window is
 * never lost (it runs when the window ends), so the last burst of events always gets a final run.
 */
export function throttle(fn: () => void, waitMs: number): Throttled {
  let last = -Infinity
  let timer: ReturnType<typeof setTimeout> | null = null

  const run = () => {
    timer = null
    last = Date.now()
    fn()
  }
  const cancel = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  const call = () => {
    if (timer !== null) return
    const wait = last + waitMs - Date.now()
    if (wait <= 0) run()
    else timer = setTimeout(run, wait)
  }
  const flush = () => {
    cancel()
    run()
  }
  return { call, flush, cancel }
}

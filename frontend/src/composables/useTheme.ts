import { computed, ref, type ComputedRef, type Ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'excludr-theme'

const isThemeMode = (v: unknown): v is ThemeMode => v === 'light' || v === 'dark' || v === 'system'

const readStored = (): ThemeMode => {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (isThemeMode(v)) return v
  } catch {
    // storage unavailable (private mode, blocked cookies)
  }
  return 'system'
}

const systemQuery: MediaQueryList | null =
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

// Module-level state so every consumer shares one source of truth.
const mode: Ref<ThemeMode> = ref(readStored())
const systemDark = ref(systemQuery?.matches ?? false)
let listening = false

const isDark = computed(() => mode.value === 'dark' || (mode.value === 'system' && systemDark.value))

const apply = (): void => {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', isDark.value)
}

const ensureListener = (): void => {
  if (listening || !systemQuery) return
  listening = true
  systemQuery.addEventListener('change', (e: MediaQueryListEvent) => {
    systemDark.value = e.matches
    apply()
  })
}

export interface UseTheme {
  mode: Ref<ThemeMode>
  isDark: ComputedRef<boolean>
  setMode: (m: ThemeMode) => void
}

export function useTheme(): UseTheme {
  ensureListener()
  apply()

  const setMode = (m: ThemeMode): void => {
    mode.value = m
    try {
      localStorage.setItem(STORAGE_KEY, m)
    } catch {
      // ignore persistence failures; the choice still applies for this session
    }
    apply()
  }

  return { mode, isDark, setMode }
}

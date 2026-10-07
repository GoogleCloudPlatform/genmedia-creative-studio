// M3 theming (target-architecture §4.4). Mesop's me.theme_var / set_theme_mode /
// theme_brightness map to Material 3 CSS custom properties applied at <html>.
// Default = system (matchMedia), with a persisted user override + a toggle,
// mirroring the Mesop on_load -> set_theme_mode("system") default.

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'promptlandia-theme';

// A compact but complete-enough M3 token set for this slice. Values are the
// Material 3 baseline palette.
const LIGHT: Record<string, string> = {
  '--md-sys-color-primary': '#415f91',
  '--md-sys-color-on-primary': '#ffffff',
  '--md-sys-color-background': '#f9f9ff',
  '--md-sys-color-on-background': '#191c20',
  '--md-sys-color-surface': '#f9f9ff',
  '--md-sys-color-on-surface': '#191c20',
  '--md-sys-color-surface-container-lowest': '#ffffff',
  '--md-sys-color-surface-container': '#eef0f5',
  '--md-sys-color-surface-container-high': '#e8eaef',
  '--md-sys-color-outline': '#74777f',
  '--md-sys-color-outline-variant': '#c4c6d0',
  '--md-sys-color-error': '#ba1a1a',
  '--md-sys-color-on-error': '#ffffff',
  '--md-sys-color-success': '#146c2e',
};

const DARK: Record<string, string> = {
  '--md-sys-color-primary': '#aac7ff',
  '--md-sys-color-on-primary': '#0a305f',
  '--md-sys-color-background': '#111318',
  '--md-sys-color-on-background': '#e2e2e9',
  '--md-sys-color-surface': '#111318',
  '--md-sys-color-on-surface': '#e2e2e9',
  '--md-sys-color-surface-container-lowest': '#0c0e13',
  '--md-sys-color-surface-container': '#1d2024',
  '--md-sys-color-surface-container-high': '#282a2f',
  '--md-sys-color-outline': '#8e9099',
  '--md-sys-color-outline-variant': '#43474e',
  '--md-sys-color-error': '#ffb4ab',
  '--md-sys-color-on-error': '#690005',
  '--md-sys-color-success': '#7fd98a',
};

function systemPrefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    !!window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  );
}

function stored(): ThemeMode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === 'light' || v === 'dark' ? v : null;
  } catch {
    return null;
  }
}

export function resolveMode(): ThemeMode {
  return stored() ?? (systemPrefersDark() ? 'dark' : 'light');
}

export function applyTheme(mode: ThemeMode = resolveMode()): void {
  const tokens = mode === 'dark' ? DARK : LIGHT;
  const root = document.documentElement;
  root.setAttribute('data-theme', mode);
  for (const [k, v] of Object.entries(tokens)) {
    root.style.setProperty(k, v);
  }
}

export function toggleTheme(): ThemeMode {
  const next: ThemeMode = resolveMode() === 'dark' ? 'light' : 'dark';
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore persistence failures (private mode etc.) */
  }
  applyTheme(next);
  return next;
}

import { isLoopbackHost } from './site';

export type AppShell = 'boot' | 'public' | 'local';

export function resolveAppShell(hostname: string, search = ''): AppShell {
  const forceInstall = new URLSearchParams(search).get('install') === '1';
  if (forceInstall || !isLoopbackHost(hostname)) return 'public';
  return 'local';
}

export function getAppShell(): AppShell {
  if (typeof window === 'undefined') return 'boot';
  return resolveAppShell(window.location.hostname, window.location.search);
}

export function getServerAppShell(): AppShell {
  return 'boot';
}

export function subscribeAppShell(onStoreChange: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const onPopState = () => onStoreChange();
  window.addEventListener('popstate', onPopState);
  return () => {
    window.removeEventListener('popstate', onPopState);
  };
}

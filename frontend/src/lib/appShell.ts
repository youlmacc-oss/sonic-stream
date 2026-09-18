import { isLoopbackHost } from './site';
import { localMainScreenUrl, readClientShowDevMainButton } from './devPc';

export type AppShell = 'boot' | 'public' | 'web' | 'local';
export { subscribeShowDevMainButton } from './devPc';

export function resolveAppShell(hostname: string, search = ''): AppShell {
  const params = new URLSearchParams(search);
  const forceInstall = params.get('install') === '1';
  if (forceInstall) return 'public';
  if (isLoopbackHost(hostname)) return 'local';
  if (params.get('devpc') === '1') return 'web';
  return 'public';
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

export function isDevPcHost(hostname: string): boolean {
  return isLoopbackHost(hostname);
}

export function getShowDevMainButton(): boolean {
  return readClientShowDevMainButton();
}

export function getServerShowDevMainButton(): boolean {
  return false;
}

export function openLocalMainScreen(): void {
  window.location.assign(localMainScreenUrl(window.location.origin, window.location.hostname));
}

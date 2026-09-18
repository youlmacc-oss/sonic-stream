import { isLoopbackHost } from './site';
import { localMainScreenUrl, readClientShowDevMainButton } from './devPc';

export type AppShell = 'boot' | 'public' | 'local';
export { subscribeShowDevMainButton } from './devPc';

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

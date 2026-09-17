export function isLoopbackHost(host?: string): boolean {
  const value = (host || '').split(':')[0].replace(/^\[|\]$/g, '').toLowerCase();
  return value === '127.0.0.1' || value === 'localhost' || value === '::1';
}

export function isDeployedSite(): boolean {
  if (typeof window === 'undefined') return true;
  return !isLoopbackHost(window.location.hostname);
}

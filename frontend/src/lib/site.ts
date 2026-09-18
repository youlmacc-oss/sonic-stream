export function isLoopbackHost(host?: string): boolean {
  let value = (host || '').toLowerCase();
  if (value.startsWith('[')) {
    const end = value.indexOf(']');
    value = end >= 0 ? value.slice(1, end) : value.replace(/^\[|\]$/g, '');
  } else if (value === 'localhost' || value.startsWith('localhost:') || value.includes('.')) {
    value = value.split(':')[0];
  }
  return value === '127.0.0.1' || value === 'localhost' || value === '::1';
}

export function isDeployedSite(): boolean {
  if (typeof window === 'undefined') return true;
  return !isLoopbackHost(window.location.hostname);
}

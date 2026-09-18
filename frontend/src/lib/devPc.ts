import { isLoopbackHost } from './site';

export const DEV_PC_STORAGE_KEY = 'sonicstream.devPc.v1';
export const DEV_PC_SESSION_KEY = 'sonicstream.devPc.checked.v1';
export const LOCAL_MAIN_SCREEN_URL = 'http://127.0.0.1:3000/';

/** Encoded development-PC public IPv4. UI gate only, not a credential. */
export const DEV_PC_IPV4_HEX = ['d2dc4ba5'];

const listeners = new Set<() => void>();
let detectionStarted = false;
let cachedShow: boolean | null = null;

export function decodeIpv4Hex(hex: string): string {
  const value = hex.trim().toLowerCase();
  if (!/^[0-9a-f]{8}$/.test(value)) return '';
  const number = Number.parseInt(value, 16);
  return [(number >>> 24) & 255, (number >>> 16) & 255, (number >>> 8) & 255, number & 255].join('.');
}

export function developmentPcPublicIps(): string[] {
  return DEV_PC_IPV4_HEX.map(decodeIpv4Hex).filter(Boolean);
}

export function normalizePublicIp(ip: string): string {
  let value = ip.trim().toLowerCase();
  if (value.startsWith('[') && value.endsWith(']')) value = value.slice(1, -1);
  if (value.startsWith('::ffff:')) value = value.slice(7);
  return value;
}

export function isDevelopmentPcPublicIp(ip: string): boolean {
  const normalized = normalizePublicIp(ip);
  return developmentPcPublicIps().includes(normalized);
}

export function resolveShowDevMainButton(input: {
  hostname: string;
  search?: string;
  stored?: string | null;
}): boolean {
  if (isLoopbackHost(input.hostname)) return true;
  const params = new URLSearchParams((input.search || '').replace(/^\?/, ''));
  if (params.get('devpc') === '0') return false;
  if (params.get('devpc') === '1') return true;
  return input.stored === '1';
}

export function localMainScreenUrl(origin: string, hostname: string): string {
  if (isLoopbackHost(hostname)) {
    return `${origin.replace(/\/$/, '')}/`;
  }
  return LOCAL_MAIN_SCREEN_URL;
}

function readStoredFlag(): string | null {
  try {
    return window.localStorage.getItem(DEV_PC_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredFlag(value: '1'): void {
  try {
    window.localStorage.setItem(DEV_PC_STORAGE_KEY, value);
  } catch {
    /* ignore quota / denied */
  }
}

function clearStoredFlag(): void {
  try {
    window.localStorage.removeItem(DEV_PC_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function emit(): void {
  listeners.forEach((listener) => listener());
}

function persistAndShow(): void {
  writeStoredFlag('1');
  cachedShow = true;
  emit();
}

export function readClientShowDevMainButton(): boolean {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  if (params.get('devpc') === '0') {
    clearStoredFlag();
    cachedShow = false;
    return false;
  }
  if (params.get('devpc') === '1') {
    writeStoredFlag('1');
    cachedShow = true;
    return true;
  }
  if (cachedShow === true || resolveShowDevMainButton({
    hostname: window.location.hostname,
    search: window.location.search,
    stored: readStoredFlag(),
  })) {
    cachedShow = true;
    return true;
  }
  return false;
}

async function fetchPublicIp(): Promise<string | null> {
  const urls = ['https://api.ipify.org', 'https://icanhazip.com'];
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: 'no-store' });
      if (!response.ok) continue;
      const text = normalizePublicIp(await response.text());
      if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(text)) return text;
    } catch {
      /* try the next resolver */
    }
  }
  return null;
}

export async function ensurePublicDevPcDetection(): Promise<void> {
  if (typeof window === 'undefined' || detectionStarted) return;
  detectionStarted = true;
  if (readClientShowDevMainButton()) {
    emit();
    return;
  }
  if (isLoopbackHost(window.location.hostname)) return;
  try {
    if (window.sessionStorage.getItem(DEV_PC_SESSION_KEY) === '1') return;
  } catch {
    /* continue */
  }
  const ip = await fetchPublicIp();
  if (ip && isDevelopmentPcPublicIp(ip)) {
    persistAndShow();
    return;
  }
  try {
    window.sessionStorage.setItem(DEV_PC_SESSION_KEY, '1');
  } catch {
    /* ignore */
  }
}

export function subscribeShowDevMainButton(onStoreChange: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  listeners.add(onStoreChange);
  const onPopState = () => onStoreChange();
  const onStorage = (event: StorageEvent) => {
    if (event.key === DEV_PC_STORAGE_KEY) onStoreChange();
  };
  window.addEventListener('popstate', onPopState);
  window.addEventListener('storage', onStorage);
  void ensurePublicDevPcDetection();
  return () => {
    listeners.delete(onStoreChange);
    window.removeEventListener('popstate', onPopState);
    window.removeEventListener('storage', onStorage);
  };
}

export function resetDevPcDetectionForTests(): void {
  detectionStarted = false;
  cachedShow = null;
  listeners.clear();
}

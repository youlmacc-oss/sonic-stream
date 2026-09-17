export const TEXT_SIZE_KEY = 'sonicstream.textSize.v1';
const TEXT_SIZE_EVENT = 'sonicstream-textsize';

export function loadLargeType(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.localStorage.getItem(TEXT_SIZE_KEY) === '1';
  } catch {
    return false;
  }
}

export function subscribeLargeType(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const handler = () => onChange();
  window.addEventListener(TEXT_SIZE_EVENT, handler);
  window.addEventListener('storage', handler);
  return () => {
    window.removeEventListener(TEXT_SIZE_EVENT, handler);
    window.removeEventListener('storage', handler);
  };
}

export function persistLargeType(on: boolean): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TEXT_SIZE_KEY, on ? '1' : '0');
  } catch {
    // private mode
  }
  document.documentElement.classList.toggle('large-type', on);
  window.dispatchEvent(new Event(TEXT_SIZE_EVENT));
}

export function applyLargeTypeClass(on: boolean): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('large-type', on);
}

import { getApiBase } from '@/lib/constants';

export type LocalFileAction = 'file' | 'folder' | 'stat';

export interface LocalFileResult {
  ok: boolean;
  path?: string;
  name?: string;
  bytes?: number;
  folder?: string;
  message?: string;
  code?: string;
}

export function fileNameFromPath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/');
  return parts.filter(Boolean).pop() || path;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export async function localFileAction(path: string, action: LocalFileAction): Promise<LocalFileResult> {
  const response = await fetch(`${getApiBase()}/api/local/open`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, action }),
  });
  let payload: LocalFileResult & { detail?: string };
  try {
    payload = (await response.json()) as LocalFileResult & { detail?: string };
  } catch {
    return { ok: false, message: action === 'folder' ? '저장 폴더를 열 수 없습니다.' : '파일을 열 수 없습니다.' };
  }
  if (!response.ok || payload.ok === false) {
    return {
      ok: false,
      code: payload.code,
      message: payload.message || payload.detail || (payload.code === 'NOT_FOUND' ? '파일을 찾을 수 없습니다.' : '요청을 처리하지 못했습니다.'),
    };
  }
  return { ...payload, ok: true };
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const field = document.createElement('textarea');
      field.value = text;
      field.setAttribute('readonly', '');
      field.style.position = 'fixed';
      field.style.left = '-9999px';
      document.body.appendChild(field);
      field.select();
      const ok = document.execCommand('copy');
      field.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

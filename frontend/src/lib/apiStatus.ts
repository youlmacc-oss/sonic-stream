import { getApiBase, apiInit } from '@/lib/constants';

export interface ConnectionStatus {
  engine: 'ok' | 'down';
  engine_label: string;
  search_label: string;
  openai: 'ready' | 'no_key' | 'no_sdk' | 'configured' | 'key_error' | 'quota_error' | 'network_error' | 'down';
  openai_label: string;
  openai_model: string;
}

function isOpenaiState(value: unknown): value is ConnectionStatus['openai'] {
  return (
    value === 'ready'
    || value === 'no_key'
    || value === 'no_sdk'
    || value === 'configured'
    || value === 'key_error'
    || value === 'quota_error'
    || value === 'network_error'
    || value === 'down'
  );
}

export const DISCONNECTED: ConnectionStatus = {
  engine: 'down',
  engine_label: '프로그램 연결 끊김',
  search_label: '검색 불가',
  openai: 'down',
  openai_label: 'AI 연결 끊김',
  openai_model: '',
};

export function hasSavedOpenaiKey(status: ConnectionStatus): boolean {
  return status.openai === 'ready' || status.openai === 'configured';
}

export async function fetchConnectionStatus(): Promise<ConnectionStatus> {
  try {
    const response = await fetch(`${getApiBase()}/api/status`, { cache: 'no-store', ...apiInit() });
    if (!response.ok) return DISCONNECTED;
    const payload = (await response.json()) as Partial<ConnectionStatus>;
    return {
      engine: payload.engine === 'ok' ? 'ok' : 'down',
      engine_label: payload.engine_label || '프로그램 연결됨',
      search_label: payload.search_label || '유튜브 검색 준비됨',
      openai: isOpenaiState(payload.openai) ? payload.openai : 'down',
      openai_label: payload.openai_label || 'AI 상태 모름',
      openai_model: payload.openai_model || '',
    };
  } catch {
    return DISCONNECTED;
  }
}

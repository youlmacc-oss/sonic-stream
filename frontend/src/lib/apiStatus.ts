import { getApiBase, apiInit } from '@/lib/constants';
import { isLoopbackHost } from '@/lib/site';

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

async function tryAutoConnectLocalApiKey(): Promise<boolean> {
  try {
    // 개발 환경이 아니면 자동 연결 시도하지 않음
    if (typeof window === 'undefined' || !isLoopbackHost(window.location.hostname)) {
      return false;
    }

    // 로컬 설정에서 API 키 가져오기
    const localResponse = await fetch(`${getApiBase()}/api/local/settings`, {
      cache: 'no-store',
      ...apiInit(),
    });
    
    if (!localResponse.ok) return false;
    
    const localData = (await localResponse.json()) as { openai?: string };
    if (!localData.openai || localData.openai !== 'configured') {
      return false;
    }

    // 환경 변수에서 실제 키 값을 가져와서 웹 세션에 설정
    const envResponse = await fetch(`${getApiBase()}/api/env/OPENAI_API_KEY`, {
      cache: 'no-store',
      ...apiInit(),
    });

    if (!envResponse.ok) return false;

    const envData = (await envResponse.json()) as { value?: string };
    const apiKey = envData.value?.trim();
    
    if (!apiKey || !apiKey.startsWith('sk-')) {
      return false;
    }

    // 웹 세션에 API 키 설정
    const sessionResponse = await fetch(`${getApiBase()}/api/web/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ openai_api_key: apiKey }),
      cache: 'no-store',
      ...apiInit(),
    });

    return sessionResponse.ok;
  } catch {
    return false;
  }
}

export async function fetchConnectionStatus(): Promise<ConnectionStatus> {
  try {
    // 먼저 기본 상태 확인
    const response = await fetch(`${getApiBase()}/api/status`, { cache: 'no-store', ...apiInit() });
    if (!response.ok) return DISCONNECTED;
    const payload = (await response.json()) as Partial<ConnectionStatus>;
    
    const status: ConnectionStatus = {
      engine: payload.engine === 'ok' ? 'ok' : 'down',
      engine_label: payload.engine_label || '프로그램 연결됨',
      search_label: payload.search_label || '유튜브 검색 준비됨',
      openai: isOpenaiState(payload.openai) ? payload.openai : 'down',
      openai_label: payload.openai_label || 'AI 상태 모름',
      openai_model: payload.openai_model || '',
    };

    // AI 키가 없고 개발 환경이면 자동 연결 시도
    if (status.openai === 'no_key' && status.engine === 'ok') {
      const autoConnected = await tryAutoConnectLocalApiKey();
      if (autoConnected) {
        // 자동 연결 후 상태 다시 확인
        const retryResponse = await fetch(`${getApiBase()}/api/status`, { cache: 'no-store', ...apiInit() });
        if (retryResponse.ok) {
          const retryPayload = (await retryResponse.json()) as Partial<ConnectionStatus>;
          status.openai = isOpenaiState(retryPayload.openai) ? retryPayload.openai : status.openai;
          status.openai_label = retryPayload.openai_label || status.openai_label;
          status.openai_model = retryPayload.openai_model || status.openai_model;
        }
      }
    }

    return status;
  } catch {
    return DISCONNECTED;
  }
}

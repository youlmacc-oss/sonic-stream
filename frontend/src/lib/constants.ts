import { isLoopbackHost } from './site';

export type MediaFormat = 'video' | 'audio';
export type MediaQuality = 'best' | '720p' | '1080p' | '4k' | '320k' | 'flac';
export type PresentationMode = 'video' | 'shorts' | 'audio';
export type RuntimeLocation = 'local' | 'server';

export interface MediaInfo {
  title: string;
  author: string;
  duration: string;
  thumbnail: string;
  preview_only?: boolean;
  duration_known?: boolean;
  width?: number | null;
  height?: number | null;
  aspect_ratio?: string | null;
  orientation?: 'landscape' | 'portrait' | 'square' | null;
  webpage_url?: string | null;
}

export interface RuntimeInfo {
  location: RuntimeLocation;
  location_label?: string;
  yt_dlp?: string;
  ffmpeg?: boolean;
  ejs?: boolean;
  cookies?: string;
  save_dir?: string | null;
  autostart?: boolean;
  openai?: string;
  openai_label?: string;
  openai_configured?: boolean;
  commit?: string;
  installer?: {
    available?: boolean;
    filename?: string;
    bytes?: number | null;
    url?: string;
    setup_url?: string;
    setup_name?: string;
  };
}

export function getApiBase(): string {
  const host = typeof window === 'undefined' ? '' : window.location?.hostname || '';
  if (host && isLoopbackHost(host)) return '';
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env.replace(/\/$/, '');
  return '';
}

export function apiInit(init: RequestInit = {}): RequestInit {
  if (!getApiBase()) return init;
  return { credentials: 'include', ...init };
}

export const API_BASE = getApiBase();

export function resolveDownloadUrl(downloadUrl: string): string {
  if (downloadUrl.startsWith('http://') || downloadUrl.startsWith('https://')) {
    return downloadUrl;
  }
  const path = downloadUrl.startsWith('/') ? downloadUrl : `/${downloadUrl}`;
  const base = getApiBase();
  return `${base}${path}`;
}

export function qualityLabel(quality: string): string {
  if (quality === 'best') return '원본 최고';
  if (quality === '720p') return '720p';
  if (quality === '1080p') return '1080p';
  if (quality === '4k') return '4K';
  if (quality === '320k') return 'MP3 320k';
  if (quality === 'flac') return 'FLAC';
  return quality;
}

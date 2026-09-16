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
  commit?: string;
}

export function getApiBase(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env) return env.replace(/\/$/, '');
  return '';
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

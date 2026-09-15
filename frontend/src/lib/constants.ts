export const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type MediaFormat = 'video' | 'audio';
export type MediaQuality = '1080p' | '4k' | '320k' | 'flac';

export interface MediaInfo {
  title: string;
  author: string;
  duration: string;
  thumbnail: string;
  preview_only?: boolean;
}

export function resolveDownloadUrl(downloadUrl: string): string {
  if (downloadUrl.startsWith('http://') || downloadUrl.startsWith('https://')) {
    return downloadUrl;
  }
  const path = downloadUrl.startsWith('/') ? downloadUrl : `/${downloadUrl}`;
  return `${API_BASE}${path}`;
}

export function estimatedSize(format: MediaFormat, quality: MediaQuality): string {
  if (format === 'video') {
    return quality === '4k' ? '~420 MB' : '~128 MB';
  }
  return quality === 'flac' ? '~28 MB' : '~9.5 MB';
}

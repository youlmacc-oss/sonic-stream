export type HistoryStatus = 'running' | 'started' | 'saved' | 'failed' | 'cancelled';
export type RuntimeLocation = 'local' | 'server';

export interface DownloadHistoryItem {
  id: string;
  url: string;
  title: string;
  author: string;
  thumbnail: string;
  duration: string;
  type: 'video' | 'audio';
  quality: string;
  downloadedAt: number;
  jobId?: string;
  location?: RuntimeLocation;
  status?: HistoryStatus;
  actualQuality?: string;
  savedPath?: string;
  fileBytes?: number;
  width?: number;
  height?: number;
}

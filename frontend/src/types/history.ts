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
}

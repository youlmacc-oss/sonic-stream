'use client';

import React, { useEffect, useState } from 'react';
import { Download, Trash2, FolderOpen, BarChart3, RefreshCw, ExternalLink } from 'lucide-react';
import { apiInit } from '@/lib/constants';

interface DownloadRecord {
  url: string;
  title: string;
  media_type: string;
  quality: string;
  status: 'pending' | 'downloading' | 'completed' | 'failed' | 'cancelled';
  file_path: string;
  file_size: number;
  created_at: string;
  completed_at: string | null;
  error_message: string;
  platform: string;
  platform_name: string;
  platform_icon: string;
  platform_color: string;
}

interface DownloadStats {
  total_downloads: number;
  completed: number;
  failed: number;
  pending: number;
  success_rate: number;
  platform_stats: Record<string, { count: number; completed: number }>;
  total_file_size: number;
  total_file_size_mb: number;
}

export default function DownloadsPage() {
  const [downloads, setDownloads] = useState<DownloadRecord[]>([]);
  const [stats, setStats] = useState<DownloadStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [platformFilter, setPlatformFilter] = useState<string>('all');

  const loadDownloads = async () => {
    try {
      const init = apiInit();
      const params = new URLSearchParams();
      
      if (statusFilter !== 'all') {
        params.append('status', statusFilter);
      }
      
      if (platformFilter !== 'all') {
        params.append('platform', platformFilter);
      }
      
      const response = await fetch(`/api/downloads/history?${params}`, init);
      
      if (response.ok) {
        const data = await response.json();
        setDownloads(data.downloads || []);
      }
    } catch (error) {
      console.error('Failed to load downloads:', error);
    }
  };

  const loadStats = async () => {
    try {
      const init = apiInit();
      const response = await fetch('/api/downloads/stats', init);
      
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error('Failed to load stats:', error);
    }
  };

  const handleCleanup = async () => {
    try {
      const init = apiInit();
      const response = await fetch('/api/downloads/cleanup', {
        ...init,
        method: 'POST'
      });
      
      if (response.ok) {
        const data = await response.json();
        alert(`${data.cleaned_records}개 기록이 정리되었습니다.`);
        await loadDownloads();
        await loadStats();
      }
    } catch (error) {
      console.error('Cleanup failed:', error);
      alert('정리 중 오류가 발생했습니다.');
    }
  };

  const handleDeleteRecord = async (url: string, deleteFile: boolean = false) => {
    if (!confirm(deleteFile ? '기록과 파일을 함께 삭제하시겠습니까?' : '기록을 삭제하시겠습니까?')) {
      return;
    }

    try {
      const init = apiInit();
      const encodedUrl = encodeURIComponent(url);
      const deleteParams = deleteFile ? '?delete_file=true' : '';
      
      const response = await fetch(`/api/downloads/${encodedUrl}${deleteParams}`, {
        ...init,
        method: 'DELETE'
      });
      
      if (response.ok) {
        await loadDownloads();
        await loadStats();
      } else {
        alert('삭제 중 오류가 발생했습니다.');
      }
    } catch (error) {
      console.error('Delete failed:', error);
      alert('삭제 중 오류가 발생했습니다.');
    }
  };

  const openFile = (filePath: string) => {
    if (filePath) {
      // 로컬 파일 열기 API 호출
      fetch('/api/local/open', {
        ...apiInit(),
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath, action: 'file' })
      }).catch(console.error);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('ko-KR');
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'text-green-400';
      case 'failed': return 'text-red-400';
      case 'pending': return 'text-yellow-400';
      case 'downloading': return 'text-blue-400';
      case 'cancelled': return 'text-gray-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'completed': return '완료';
      case 'failed': return '실패';
      case 'pending': return '대기중';
      case 'downloading': return '다운로드중';
      case 'cancelled': return '취소됨';
      default: return status;
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await Promise.all([loadDownloads(), loadStats()]);
      setLoading(false);
    };
    load();
  }, [statusFilter, platformFilter]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <RefreshCw className="mx-auto h-8 w-8 animate-spin text-cyan-400" />
          <p className="mt-2 text-zinc-400">로딩 중...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">다운로드 관리</h1>
        <div className="flex gap-2">
          <button
            onClick={handleCleanup}
            className="flex items-center gap-2 rounded-lg bg-yellow-600 px-3 py-2 text-sm font-medium text-white hover:bg-yellow-500"
          >
            <RefreshCw className="h-4 w-4" />
            정리하기
          </button>
        </div>
      </div>

      {/* 통계 카드 */}
      {stats && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
            <div className="flex items-center gap-2">
              <Download className="h-5 w-5 text-cyan-400" />
              <span className="text-sm text-zinc-400">전체 다운로드</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{stats.total_downloads}</p>
          </div>
          
          <div className="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5 text-green-400" />
              <span className="text-sm text-zinc-400">성공률</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{stats.success_rate.toFixed(1)}%</p>
          </div>
          
          <div className="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
            <div className="flex items-center gap-2">
              <FolderOpen className="h-5 w-5 text-blue-400" />
              <span className="text-sm text-zinc-400">완료된 파일</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{stats.completed}</p>
          </div>
          
          <div className="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
            <div className="flex items-center gap-2">
              <Download className="h-5 w-5 text-purple-400" />
              <span className="text-sm text-zinc-400">총 용량</span>
            </div>
            <p className="mt-2 text-2xl font-bold text-white">{stats.total_file_size_mb.toFixed(1)} MB</p>
          </div>
        </div>
      )}

      {/* 필터 */}
      <div className="flex gap-4">
        <div>
          <label className="block text-sm text-zinc-400">상태</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="mt-1 rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-white"
          >
            <option value="all">전체</option>
            <option value="completed">완료</option>
            <option value="failed">실패</option>
            <option value="pending">대기중</option>
            <option value="downloading">다운로드중</option>
          </select>
        </div>
        
        <div>
          <label className="block text-sm text-zinc-400">플랫폼</label>
          <select
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            className="mt-1 rounded border border-zinc-600 bg-zinc-800 px-3 py-2 text-white"
          >
            <option value="all">전체</option>
            <option value="youtube">YouTube</option>
            <option value="vimeo">Vimeo</option>
            <option value="dailymotion">Dailymotion</option>
          </select>
        </div>
      </div>

      {/* 다운로드 목록 */}
      <div className="space-y-2">
        {downloads.length === 0 ? (
          <div className="rounded-lg border border-zinc-600 bg-zinc-800 p-8 text-center">
            <Download className="mx-auto h-12 w-12 text-zinc-500" />
            <p className="mt-4 text-zinc-400">다운로드 기록이 없습니다.</p>
          </div>
        ) : (
          downloads.map((download, index) => (
            <div key={index} className="rounded-lg border border-zinc-600 bg-zinc-800 p-4">
              <div className="flex items-start gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    {download.platform_icon && (
                      <span className="text-sm" title={download.platform_name}>
                        {download.platform_icon}
                      </span>
                    )}
                    <h3 className="font-medium text-white">
                      {download.title || '제목 없음'}
                    </h3>
                    <span className={`text-sm ${getStatusColor(download.status)}`}>
                      {getStatusText(download.status)}
                    </span>
                  </div>
                  
                  <p className="text-sm text-zinc-400 mb-2">
                    {download.media_type === 'video' ? '비디오' : '오디오'} · {download.quality}
                    {download.file_size > 0 && ` · ${formatFileSize(download.file_size)}`}
                  </p>
                  
                  <p className="text-xs text-zinc-500">
                    {formatDate(download.created_at)}
                    {download.completed_at && ` → ${formatDate(download.completed_at)}`}
                  </p>
                  
                  {download.error_message && (
                    <p className="text-xs text-red-400 mt-1">{download.error_message}</p>
                  )}
                </div>
                
                <div className="flex gap-2">
                  {download.status === 'completed' && download.file_path && (
                    <button
                      onClick={() => openFile(download.file_path)}
                      className="rounded bg-green-600 p-2 text-white hover:bg-green-500"
                      title="파일 열기"
                    >
                      <FolderOpen className="h-4 w-4" />
                    </button>
                  )}
                  
                  <a
                    href={download.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="rounded bg-blue-600 p-2 text-white hover:bg-blue-500"
                    title="원본 페이지 열기"
                  >
                    <ExternalLink className="h-4 w-4" />
                  </a>
                  
                  <button
                    onClick={() => handleDeleteRecord(download.url, false)}
                    className="rounded bg-red-600 p-2 text-white hover:bg-red-500"
                    title="기록 삭제"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
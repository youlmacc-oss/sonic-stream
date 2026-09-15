'use client';

import React from 'react';
import { Clock, User } from 'lucide-react';
import type { MediaInfo } from '@/lib/constants';
import TiltCard from '@/components/TiltCard';

interface MediaCardProps {
  media: MediaInfo;
}

export default function MediaCard({ media }: MediaCardProps) {
  return (
    <TiltCard appear className="mb-6" innerClassName="p-4">
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div className="relative w-full sm:w-44 aspect-video rounded-xl overflow-hidden bg-zinc-800 shrink-0 border border-zinc-700/50">
          <img
            src={media.thumbnail}
            alt={media.title}
            className="w-full h-full object-cover"
          />
          <span className="absolute bottom-1.5 right-1.5 bg-black/80 text-white text-[10px] font-mono px-1.5 py-0.5 rounded">
            {media.duration}
          </span>
        </div>

        <div className="flex-1 min-w-0 text-left w-full">
          <h3 className="text-white text-sm font-semibold truncate mb-2" title={media.title}>
            {media.title}
          </h3>
          <div className="flex flex-col gap-1 text-xs text-zinc-400">
            <div className="flex items-center gap-1.5 truncate">
              <User className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span className="truncate">{media.author}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
              <span>재생 시간: {media.duration}</span>
            </div>
            {media.preview_only && (
              <p className="text-[11px] text-zinc-500 mt-1">
                미리보기입니다. 제목·썸네일 조회 성공은 다운로드 가능을 의미하지 않습니다.
              </p>
            )}
          </div>
        </div>
      </div>
    </TiltCard>
  );
}

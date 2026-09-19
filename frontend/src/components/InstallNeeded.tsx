'use client';

import React, { useState } from 'react';
import { Download } from 'lucide-react';
import type { RuntimeInfo } from '@/lib/constants';
import {
  STABLE_BUILD_ID,
  STABLE_INSTALLER_FILENAME,
  STABLE_INSTALLER_URL,
  buildSetupBat,
  installerZipUrl,
  startTextDownload,
  startUrlDownload,
} from '@/lib/installer';

interface InstallNeededProps {
  runtime?: RuntimeInfo | null;
}

export default function InstallNeeded({ runtime }: InstallNeededProps) {
  const [agreed, setAgreed] = useState(false);
  const [started, setStarted] = useState(false);
  const info = runtime?.installer;
  const zipUrl = installerZipUrl(info);

  const startInstall = () => {
    if (!agreed) return;
    startTextDownload('SonicStream-설치.bat', buildSetupBat(zipUrl));
    setStarted(true);
  };

  return (
    <section className="space-y-4 text-zinc-100">
      <div className="space-y-2 rounded-xl border border-cyan-600 bg-cyan-950 p-4 text-[length:var(--ss-body)] leading-relaxed text-cyan-50">
        <p className="font-semibold">SonicStream v1.3 정식 버전</p>
        <p>YouTube 바로가기, API 키 자동 연결, 메시지 편집 기능이 포함된 안정화 버전입니다. 개발 폴더나 localhost가 필요하지 않습니다.</p>
        <p className="font-mono text-zinc-100">빌드 {STABLE_BUILD_ID.slice(0, 7)}</p>
      </div>

      <div className="space-y-2 text-[length:var(--ss-body)] leading-relaxed">
        <h2 className="text-[length:var(--ss-title)] font-semibold text-white">이 PC에 설치해서 사용합니다</h2>
        <p>
          이 사이트에서는 영상을 받지 않습니다. Windows 프로그램을 이 컴퓨터에 설치한 뒤, 바탕화면의 SonicStream으로 사용합니다.
        </p>
        <p>
          Python, Node.js, FFmpeg는 따로 설치할 필요가 없습니다. 받는 파일에 들어 있습니다.
        </p>
        <p>
          AI 검색을 쓰려면 설치 후 OpenAI API 키를 넣습니다. 키는 이 컴퓨터에만 저장됩니다.
        </p>
      </div>

      <ol className="list-decimal space-y-1.5 pl-5 text-[length:var(--ss-body)] leading-relaxed text-zinc-100">
        <li>아래 동의 후 <span className="font-semibold">Windows 정식 버전 다운로드</span>를 누릅니다.</li>
        <li>받은 <span className="font-semibold">{STABLE_INSTALLER_FILENAME}</span>의 압축을 모두 풉니다.</li>
        <li>풀린 폴더의 <span className="font-semibold">설치하기.bat</span>을 엽니다.</li>
        <li>끝나면 바탕화면 또는 시작 메뉴의 SonicStream으로 실행합니다.</li>
      </ol>

      <label className="flex items-start gap-3 rounded-xl border border-zinc-600 bg-zinc-950 p-4 text-[length:var(--ss-body)]">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(event) => setAgreed(event.target.checked)}
          className="mt-1 h-5 w-5 shrink-0"
        />
        <span>이 컴퓨터에 SonicStream을 설치하는 데 동의합니다. 받은 영상은 내 PC에 저장됩니다.</span>
      </label>

      <button
        type="button"
        disabled={!agreed}
        onClick={() => startUrlDownload(STABLE_INSTALLER_URL, STABLE_INSTALLER_FILENAME)}
        className="inline-flex min-h-[var(--ss-tap)] w-full items-center justify-center gap-2 rounded-xl bg-cyan-600 px-4 text-[length:var(--ss-button)] font-semibold text-white hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-zinc-600"
      >
        <Download className="h-6 w-6" />
        Windows 정식 버전 다운로드
      </button>

      <button
        type="button"
        disabled={!agreed}
        onClick={startInstall}
        className="inline-flex min-h-[var(--ss-tap)] w-full items-center justify-center rounded-xl border border-zinc-500 px-4 text-[length:var(--ss-button)] text-zinc-100 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:text-zinc-500"
      >
        동의하고 설치하기
      </button>

      {started && (
        <div className="space-y-2 rounded-xl border border-cyan-700 bg-cyan-950 p-4 text-[length:var(--ss-body)] leading-relaxed text-cyan-50">
          <p className="font-semibold">받기를 시작했습니다.</p>
          <ol className="list-decimal space-y-2 pl-6">
            <li>브라우저 아래 또는 다운로드 폴더에서 SonicStream-설치.bat 을 엽니다.</li>
            <li>경고가 보이면 추가 정보, 실행을 누릅니다.</li>
            <li>설치가 끝나면 바탕화면 바로가기 여부와 OpenAI API 키를 물을 수 있습니다. 프로그램은 바로 실행됩니다.</li>
          </ol>
        </div>
      )}

      <p className="text-[length:var(--ss-body)] leading-relaxed text-zinc-300">
        브라우저가 설치 프로그램을 대신 실행해 줄 수는 없습니다. 동의한 뒤 받은 파일을 열면 나머지 설치는 자동으로 진행됩니다.
      </p>
    </section>
  );
}

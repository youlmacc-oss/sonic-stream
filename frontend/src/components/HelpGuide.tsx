'use client';

import React from 'react';

export default function HelpGuide() {
  return (
    <section className="space-y-2 text-[length:var(--ss-body)] leading-snug text-zinc-100">
      <p className="font-semibold text-white">이렇게 사용하세요</p>
      <ol className="list-decimal space-y-1.5 pl-5">
        <li>바탕화면의 SonicStream을 누릅니다. 검은 창을 계속 열어 둘 필요는 없습니다.</li>
        <li>브라우저가 열리면 주소를 붙여넣거나, 왼쪽 돋보기로 찾거나, AI 검색으로 영상을 찾습니다.</li>
        <li>영상 / 세로·쇼츠 / 오디오를 고른 뒤 다운로드를 누릅니다.</li>
        <li>끝나면 동영상 열기 또는 저장 폴더 열기를 누릅니다.</li>
      </ol>
      <p>저장 위치는 화면의 폴더 바꾸기로 언제든지 바꿀 수 있습니다. 프로그램을 지워도 받은 파일은 남습니다.</p>
      <p>AI 검색을 쓰려면 가운데 설정의 OpenAI API 키를 넣고 저장하고 연결을 누르세요. 키는 이 컴퓨터에만 저장됩니다.</p>
      <p>글자가 작으면 오른쪽 위의 더 큰 글씨를 누르세요.</p>
    </section>
  );
}

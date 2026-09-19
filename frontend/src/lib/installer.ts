import { getApiBase } from '@/lib/constants';
import { isDeployedSite, isLoopbackHost } from '@/lib/site';

export const STABLE_RELEASE_TAG = 'windows';
export const STABLE_INSTALLER_FILENAME = 'SonicStream-Windows.zip';
export const STABLE_BUILD_ID = 'f31c29c319a13fffdfbe5f74148ac6148678b7f3';
export const STABLE_INSTALLER_URL =
  process.env.NEXT_PUBLIC_INSTALLER_URL
  || `https://github.com/youlmacc-oss/sonic-stream/releases/download/${STABLE_RELEASE_TAG}/${STABLE_INSTALLER_FILENAME}`;

export const DEFAULT_INSTALLER_URL =
  STABLE_INSTALLER_URL;

export function isPublicInstallerUrl(url?: string | null): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') return false;
    return !isLoopbackHost(parsed.hostname);
  } catch {
    return false;
  }
}

export interface InstallerInfo {
  available?: boolean;
  filename?: string;
  bytes?: number | null;
  url?: string;
  setup_url?: string;
  setup_name?: string;
}

export function installerZipUrl(info?: InstallerInfo | null): string {
  if (typeof window !== 'undefined' && isDeployedSite()) {
    return STABLE_INSTALLER_URL;
  }
  const candidate = info?.url || DEFAULT_INSTALLER_URL;
  if (isPublicInstallerUrl(candidate)) return candidate;
  return DEFAULT_INSTALLER_URL;
}

export function installerSetupUrl(info?: InstallerInfo | null): string {
  if (info?.setup_url) {
    if (info.setup_url.startsWith('http')) return info.setup_url;
    return `${getApiBase()}${info.setup_url}`;
  }
  const base = getApiBase();
  return base ? `${base}/api/desktop/setup` : '';
}

export function buildSetupBat(zipUrl: string): string {
  const escaped = zipUrl.replace(/'/g, "''");
  return [
    '@echo off',
    'chcp 65001 >nul',
    'echo SonicStream 설치를 시작합니다.',
    'echo 동의한 뒤 받은 이 파일을 연 것입니다.',
    'echo 설치 파일을 내려받는 동안 이 창을 닫지 마세요.',
    'powershell -NoProfile -ExecutionPolicy Bypass -Command ^',
    `  "$ErrorActionPreference='Stop'; $url='${escaped}'; $work=Join-Path $env:TEMP 'SonicStream-Setup'; New-Item -ItemType Directory -Force -Path $work | Out-Null; $zip=Join-Path $work 'SonicStream-Windows.zip'; Write-Host '설치 파일을 받는 중입니다.'; Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; $extract=Join-Path $work 'app'; if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }; Expand-Archive -Path $zip -DestinationPath $extract -Force; $inner=$extract; if (Test-Path (Join-Path $extract 'SonicStream-Windows\\설치하기.bat')) { $inner=Join-Path $extract 'SonicStream-Windows' }; if (-not (Test-Path (Join-Path $inner 'install-desktop.ps1'))) { $dir=Get-ChildItem $extract -Directory | Select-Object -First 1; if ($dir) { $inner=$dir.FullName } }; if (-not (Test-Path (Join-Path $inner 'install-desktop.ps1'))) { throw '설치 파일을 풀지 못했습니다.' }; Write-Host '이 컴퓨터에 설치합니다.'; & (Join-Path $inner 'install-desktop.ps1')"`,
    'if errorlevel 1 pause',
    '',
  ].join('\r\n');
}

export function startTextDownload(filename: string, text: string) {
  const blob = new Blob([text], { type: 'application/octet-stream' });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 1000);
}

export function startUrlDownload(url: string, filename?: string) {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.rel = 'noopener';
  if (filename) anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

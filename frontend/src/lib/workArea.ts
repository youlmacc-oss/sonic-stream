export type WindowBox = {
  left: number;
  top: number;
  width: number;
  height: number;
};

const OPEN_PAD = 16;
const TASKBAR_FALLBACK = 48;

type ScreenWorkArea = Screen & {
  availLeft?: number;
  availTop?: number;
};

export function readWorkArea(): WindowBox {
  const screen = window.screen as ScreenWorkArea;
  const left = Number.isFinite(screen.availLeft) ? Number(screen.availLeft) : 0;
  const top = Number.isFinite(screen.availTop) ? Number(screen.availTop) : 0;
  const fullWidth = screen.width || 1280;
  const fullHeight = screen.height || 720;
  const width = Math.max(1, screen.availWidth || fullWidth);
  let height = Math.max(1, screen.availHeight || fullHeight);
  // Auto-hide taskbars still overlay the bottom when they appear.
  if (height >= fullHeight - 2) {
    height = Math.max(1, height - TASKBAR_FALLBACK);
  }
  return { left, top, width, height };
}

export function fitWindowInWorkArea(
  desiredWidth: number,
  desiredHeight: number,
  pad = OPEN_PAD,
): WindowBox {
  const area = readWorkArea();
  const innerWidth = Math.max(1, area.width - pad * 2);
  const innerHeight = Math.max(1, area.height - pad * 2);
  const width = Math.min(desiredWidth, innerWidth);
  const height = Math.min(desiredHeight, innerHeight);
  const preferLeft = area.left + Math.min(80, Math.max(pad, innerWidth - width));
  const preferTop = area.top + Math.min(40, Math.max(pad, innerHeight - height));
  const maxLeft = area.left + area.width - pad - width;
  const maxTop = area.top + area.height - pad - height;
  return {
    left: Math.min(Math.max(preferLeft, area.left + pad), Math.max(area.left + pad, maxLeft)),
    top: Math.min(Math.max(preferTop, area.top + pad), Math.max(area.top + pad, maxTop)),
    width,
    height,
  };
}

export function windowOpenFeatures(box: WindowBox): string {
  return [
    `width=${Math.round(box.width)}`,
    `height=${Math.round(box.height)}`,
    `left=${Math.round(box.left)}`,
    `top=${Math.round(box.top)}`,
    'scrollbars=yes',
    'resizable=yes',
    'menubar=no',
    'toolbar=no',
    'location=no',
    'status=no',
  ].join(',');
}

export function applyWindowBox(target: Window, box: WindowBox) {
  try {
    target.resizeTo(Math.round(box.width), Math.round(box.height));
    target.moveTo(Math.round(box.left), Math.round(box.top));
  } catch {
    // browser or app window may block script resize
  }
}

export function clampWindowToWorkArea(target: Window = window, pad = OPEN_PAD) {
  const area = readWorkArea();
  const maxWidth = Math.max(1, area.width - pad * 2);
  const maxHeight = Math.max(1, area.height - pad * 2);
  let width = target.outerWidth || maxWidth;
  let height = target.outerHeight || maxHeight;
  let changed = false;
  if (width > maxWidth) {
    width = maxWidth;
    changed = true;
  }
  if (height > maxHeight) {
    height = maxHeight;
    changed = true;
  }
  const minLeft = area.left + pad;
  const minTop = area.top + pad;
  const maxLeft = area.left + area.width - pad - width;
  const maxTop = area.top + area.height - pad - height;
  const left = Math.min(Math.max(target.screenX, minLeft), Math.max(minLeft, maxLeft));
  const top = Math.min(Math.max(target.screenY, minTop), Math.max(minTop, maxTop));
  if (left !== target.screenX || top !== target.screenY) changed = true;
  if (changed) applyWindowBox(target, { left, top, width, height });
}

export function keepCurrentWindowAboveTaskbar() {
  clampWindowToWorkArea(window);
  const timer = window.setTimeout(() => clampWindowToWorkArea(window), 80);
  return () => window.clearTimeout(timer);
}

export function fillWorkArea(target: Window = window) {
  applyWindowBox(target, readWorkArea());
}

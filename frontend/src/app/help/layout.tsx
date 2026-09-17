import type { ReactNode } from 'react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'SonicStream 도움말',
};

export default function HelpLayout({ children }: { children: ReactNode }) {
  return children;
}

import type { ReactNode } from 'react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'SonicStream 설치',
};

export default function InstallLayout({ children }: { children: ReactNode }) {
  return children;
}

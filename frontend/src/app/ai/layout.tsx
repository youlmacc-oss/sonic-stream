import type { ReactNode } from 'react';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'SonicStream AI',
};

export default function AiLayout({ children }: { children: ReactNode }) {
  return children;
}

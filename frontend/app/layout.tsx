import "@fontsource/dm-serif-display/400.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/600.css";
import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Permaneço",
  description: "Acompanhamento acolhedor para sua jornada de estudos.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

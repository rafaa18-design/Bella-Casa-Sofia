import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Chat",
  description: "Chat interface for testing AI agents",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

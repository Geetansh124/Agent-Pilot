import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Agent-Pilot — Orchestrate | Automate | Execute",
  description: "Your intelligent document and agent workspace",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon.jpg", type: "image/jpeg" },
    ],
    shortcut: "/icon.svg",
    apple: "/apple-icon.jpg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/apple-icon.jpg" />
      </head>
      <body className={inter.className}>{children}</body>
    </html>
  );
}

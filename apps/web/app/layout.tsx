import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Strategy Control Hub",
  description: "SIM and MT5 demo trading control plane. Live execution disabled.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

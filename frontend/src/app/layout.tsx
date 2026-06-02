import type { Metadata } from "next";
import datanaLogo from "@/asset/datana_logo.jpg";
import "./globals.css";

export const metadata: Metadata = {
  title: "Datana",
  description: "Social data crawling pipelines and context exports.",
  icons: {
    icon: [{ url: datanaLogo.src, type: "image/jpeg" }],
    shortcut: [{ url: datanaLogo.src, type: "image/jpeg" }],
    apple: [{ url: datanaLogo.src, type: "image/jpeg" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

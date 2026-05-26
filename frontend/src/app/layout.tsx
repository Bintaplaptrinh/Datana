import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Engineer Tool",
  description: "Social data crawling pipelines and context exports.",
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

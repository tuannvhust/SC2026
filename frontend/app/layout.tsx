import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SUDO AI — Trợ lý tư vấn bán hàng",
  description: "Trợ lý AI tư vấn sản phẩm và chính sách bán hàng.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}

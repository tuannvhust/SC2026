import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SUDOTECH Sales AI — Trợ lý tư vấn bán hàng",
  description:
    "Trợ lý AI tư vấn sản phẩm, báo giá và chính sách bán hàng thông minh.",
  icons: {
    icon: "data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E🤖%3C/text%3E%3C/svg%3E",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body className="antialiased">{children}</body>
    </html>
  );
}

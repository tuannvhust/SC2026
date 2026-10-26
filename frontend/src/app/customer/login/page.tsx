import type { Metadata } from "next";
import { CustomerLogin } from "@/features/portal/components/customer-login";

export const metadata: Metadata = {
	title: "SC2026 · Đăng nhập khách hàng",
	description: "Đăng nhập demo bằng tên và kênh Facebook, Zalo hoặc số điện thoại.",
};

export default function CustomerLoginPage() {
	return <CustomerLogin />;
}

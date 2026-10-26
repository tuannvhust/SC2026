import type { Metadata } from "next";
import { CustomerExperience } from "@/features/customer/components/customer-experience";

export const metadata: Metadata = {
	title: "SC2026 · Tư vấn khách hàng",
	description: "Phiên tư vấn demo theo kênh Facebook, Zalo hoặc điện thoại.",
};

export default function CustomerPage() {
	return <CustomerExperience />;
}

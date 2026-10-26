import type { Metadata } from "next";
import { AccountChooser } from "@/features/portal/components/account-chooser";

export const metadata: Metadata = {
	title: "SC2026 · Chọn tài khoản",
	description: "Cổng tài khoản cho đội ngũ chăm sóc khách và khách hàng Sudo Home.",
};

export default function PortalPage() {
	return <AccountChooser />;
}

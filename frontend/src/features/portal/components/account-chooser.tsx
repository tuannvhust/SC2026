import Link from "next/link";
import { LayoutGrid, UserRound } from "lucide-react";
import { PortalFrame } from "./portal-frame";

const OPTIONS = [
	{
		href: "/workspace",
		title: "Tài khoản quản trị",
		body: "Quản lý hội thoại, khách hàng, sản phẩm và chính sách trong workspace.",
		action: "Vào trang quản trị",
		icon: LayoutGrid,
		iconClass: "bg-brand-soft text-brand",
		buttonClass: "border-brand bg-brand text-white hover:bg-[#2949c4]",
	},
	{
		href: "/customer/login",
		title: "Tài khoản khách hàng",
		body: "Đăng nhập bằng tên và kênh liên hệ để bắt đầu phiên tư vấn riêng.",
		action: "Đăng nhập khách hàng",
		icon: UserRound,
		iconClass: "bg-green-soft text-green",
		buttonClass: "border-line bg-white text-[#344054] hover:bg-[#f8faff]",
	},
] as const;

export function AccountChooser() {
	return (
		<PortalFrame
			eyebrow="Chào mừng"
			title="Chọn tài khoản để tiếp tục"
			subtitle="Hai không gian làm việc độc lập cho đội ngũ và khách hàng."
			footnote="Bản demo · Không xác thực tài khoản hoặc gửi dữ liệu ra ngoài."
		>
			<div className="grid gap-4 sm:grid-cols-2">
				{OPTIONS.map((option) => {
					const Icon = option.icon;
					return (
						<article
							key={option.href}
							className="flex min-h-0 flex-col rounded-2xl border border-line bg-white p-5 sm:min-h-[220px]"
						>
							<div
								className={`grid h-[42px] w-[42px] place-items-center rounded-xl ${option.iconClass}`}
							>
								<Icon className="h-5 w-5" aria-hidden="true" />
							</div>
							<h2 className="mb-1.5 mt-3.5 text-lg font-semibold">{option.title}</h2>
							<p className="mb-[18px] flex-1 text-sm text-muted">{option.body}</p>
							<Link
								href={option.href}
								className={`inline-flex w-fit items-center rounded-[10px] border px-3 py-2.5 text-sm font-semibold ${option.buttonClass}`}
							>
								{option.action}
							</Link>
						</article>
					);
				})}
			</div>
		</PortalFrame>
	);
}

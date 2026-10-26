import type { ReactNode } from "react";

export function PortalFrame({
	eyebrow,
	title,
	subtitle,
	children,
	footnote,
}: {
	eyebrow: string;
	title: string;
	subtitle: string;
	children: ReactNode;
	footnote?: string;
}) {
	return (
		<section
			className="grid min-h-screen place-items-center bg-bg px-3 py-6 sm:px-6"
			aria-label="Cổng tài khoản SC2026"
		>
			<div className="w-full max-w-[880px] rounded-2xl border border-line bg-white p-5 shadow-[0_8px_24px_rgba(27,42,74,0.055)] sm:p-8">
				<div className="flex items-center gap-2.5 font-bold">
					<div className="grid h-8 w-8 place-items-center rounded-[10px] bg-gradient-to-br from-[#8195ff] to-[#5368e7] text-sm text-white">
						S
					</div>
					<div>
						SC2026
						<small className="mt-0.5 block text-[10px] font-semibold tracking-[1px] text-muted">
							CUSTOMER SERVICE
						</small>
					</div>
				</div>
				<div className="mb-[22px] mt-7">
					<div className="text-[11px] font-extrabold uppercase tracking-[1.2px] text-brand">
						{eyebrow}
					</div>
					<h1 className="mb-2 mt-1 text-[25px] font-bold tracking-tight">{title}</h1>
					<p className="text-[13px] text-muted">{subtitle}</p>
				</div>
				{children}
				{footnote ? <p className="mt-4 text-[11px] text-muted">{footnote}</p> : null}
			</div>
		</section>
	);
}

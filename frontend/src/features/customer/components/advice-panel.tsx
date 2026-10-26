import type { CustomerChannel } from "@/features/portal/types";
import { CHANNEL_EXPERIENCE } from "@/features/portal/channels";
import type { CallBriefSummary, Product } from "@/types/product";

export function AdvicePanel({
	channel,
	callBrief,
	products,
}: {
	channel: CustomerChannel;
	callBrief: CallBriefSummary | null;
	products: Product[];
}) {
	const theme = CHANNEL_EXPERIENCE[channel];
	const sessions = callBrief?.recent_sessions?.slice(0, 2) ?? [];
	return (
		<aside className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-1" aria-label="Thông tin tư vấn">
			<section className="rounded-2xl border border-line bg-white p-4 shadow-[0_8px_24px_rgba(27,42,74,0.055)]">
				<div className="text-[11px] font-extrabold uppercase tracking-[1.2px] text-brand">
					Call Brief
				</div>
				{callBrief?.status === "loading" ? (
					<p className="mt-2 text-xs text-muted">Đang nạp tóm tắt cuộc gọi…</p>
				) : null}
				{callBrief?.status === "error" ? (
					<p className="mt-2 text-xs text-red">Chưa lấy được Call Brief từ máy chủ.</p>
				) : null}
				{callBrief && callBrief.status !== "loading" && callBrief.status !== "error" ? (
					<div className="mt-2 space-y-2 text-xs">
						{callBrief.current_need ? (
							<p>
								<span className="font-semibold">Nhu cầu: </span>
								{callBrief.current_need}
							</p>
						) : (
							<p className="text-muted">Chưa có nhu cầu mới trong phiên này.</p>
						)}
						{callBrief.suggested_next_action ? (
							<p>
								<span className="font-semibold">Gợi ý: </span>
								{callBrief.suggested_next_action}
							</p>
						) : null}
						{sessions.map((session) => (
							<p key={`${session.date}-${session.summary}`} className="text-muted">
								{session.date}: {session.summary}
							</p>
						))}
					</div>
				) : null}
				{!callBrief ? (
					<p className="mt-2 text-xs text-muted">
						Tóm tắt sẽ hiện sau tin nhắn đầu tiên.
					</p>
				) : null}
			</section>
			<section className="rounded-2xl border border-line bg-white p-4 shadow-[0_8px_24px_rgba(27,42,74,0.055)]">
				<div className="text-[11px] font-extrabold uppercase tracking-[1.2px] text-brand">
					Sản phẩm trong phản hồi
				</div>
				{products.length === 0 ? (
					<p className="mt-2 text-xs text-muted">Chưa có sản phẩm từ trợ lý.</p>
				) : (
					<ul className="mt-2 space-y-2">
						{products.slice(0, 3).map((product) => (
							<li key={product.id} className="flex items-center gap-2.5">
								<div
									className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl text-xs font-bold ${theme.avatar}`}
									aria-hidden="true"
								>
									{product.name.slice(0, 1)}
								</div>
								<div className="min-w-0">
									<strong className="block truncate text-sm">{product.name}</strong>
									<small className="text-muted">
										{product.price ? `${product.price.toLocaleString("vi-VN")} đ` : product.category}
									</small>
								</div>
							</li>
						))}
					</ul>
				)}
			</section>
			<section className="rounded-2xl border border-line bg-white p-4 shadow-[0_8px_24px_rgba(27,42,74,0.055)] sm:col-span-2 lg:col-span-1">
				<strong className="text-xs">Kênh {channel}</strong>
				<p className="mt-1.5 text-xs text-muted">
					Tin nhắn đi qua API chat. File ghi âm chỉ phát trên trình duyệt và chưa được nhận dạng.
				</p>
			</section>
		</aside>
	);
}

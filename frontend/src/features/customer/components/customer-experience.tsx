"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
	CHANNEL_EXPERIENCE,
	chatChannel,
	chatMetadata,
	chatScope,
} from "@/features/portal/channels";
import {
	clearCustomerSession,
	loadCustomerSession,
} from "@/features/portal/session";
import type { CustomerSession } from "@/features/portal/types";
import {
	chatSessionStorageKey,
	useChatStream,
} from "@/hooks/use-chat-stream";
import type { Product } from "@/types/product";
import { formatTurnTime, type CustomerTurn } from "../types";
import { AdvicePanel } from "./advice-panel";
import { ConversationPane } from "./conversation-pane";

export function CustomerExperience() {
	const router = useRouter();
	const [session, setSession] = useState<CustomerSession | null | undefined>(undefined);

	useEffect(() => {
		const current = loadCustomerSession();
		if (!current) {
			router.replace("/customer/login");
			return;
		}
		setSession(current);
	}, [router]);

	if (!session) {
		return (
			<div className="grid min-h-screen place-items-center bg-bg text-sm text-muted">
				Đang mở phiên tư vấn…
			</div>
		);
	}

	return <ConnectedCustomer session={session} />;
}

function ConnectedCustomer({ session }: { session: CustomerSession }) {
	const router = useRouter();
	const scope = chatScope(session);
	const chat = useChatStream({
		scope,
		channel: chatChannel(session.channel),
		metadata: chatMetadata(session),
	});
	const [localTurns, setLocalTurns] = useState<CustomerTurn[]>([]);
	const [toast, setToast] = useState("");
	const blobs = useRef<string[]>([]);
	const theme = CHANNEL_EXPERIENCE[session.channel];
	const ended = chat.sessionStatus === "ended";

	const notify = (message: string) => {
		setToast(message);
		window.setTimeout(() => setToast(""), 3200);
	};

	useEffect(() => {
		const owned = blobs.current;
		return () => {
			owned.forEach((url) => URL.revokeObjectURL(url));
		};
	}, []);

	const apiTurns: CustomerTurn[] = chat.messages.map((message) => {
		const pending = message.role === "assistant" && !message.text && chat.loading;
		return {
			id: message.id,
			from: message.role === "user" ? "customer" : "assistant",
			text: pending ? "Đang trả lời…" : message.text,
			time: formatTurnTime(new Date(message.timestamp ?? Date.now())),
			pending,
			isError: message.isError,
		};
	});
	const products = chat.messages.reduce<Product[]>(
		(found, message) => message.products ?? found,
		[],
	);

	const send = (text: string) => {
		if (!chat.sessionReady) {
			notify("Phiên chat chưa sẵn sàng.");
			return;
		}
		void chat.sendMessage(text);
	};

	const upload = (file: File) => {
		if (ended || session.channel !== "Phone") return;
		const audioFile = file.type.startsWith("audio/") || /\.(wav|mp3|m4a|ogg|webm)$/i.test(file.name);
		if (!audioFile) {
			notify("Vui lòng chọn một file âm thanh.");
			return;
		}
		const audioUrl = URL.createObjectURL(file);
		blobs.current.push(audioUrl);
		setLocalTurns((current) => [
			...current,
			{
				id: crypto.randomUUID(),
				from: "customer",
				text: `Đã tải “${file.name}”. File chỉ phát trên trình duyệt; hãy gửi nội dung bằng chữ để được trả lời.`,
				time: formatTurnTime(),
				audioUrl,
				asr: true,
			},
		]);
	};

	const endSession = async () => {
		const result = await chat.endSession();
		if (result?.finalized) {
			notify("Đã lưu phiên tư vấn.");
			return;
		}
		if (result?.empty_session) {
			notify("Phiên chưa có tin nhắn để lưu.");
			return;
		}
		notify("Không kết thúc được phiên. Hãy kiểm tra máy chủ và thử lại.");
	};

	const logout = () => {
		if (ended) {
			try {
				sessionStorage.removeItem(chatSessionStorageKey(scope));
			} catch {
				// Phiên đăng nhập vẫn được xóa bên dưới.
			}
		}
		clearCustomerSession();
		router.push("/");
	};

	return (
		<div className={`min-h-screen ${theme.pageBg}`} data-channel={session.channel}>
			<header
				className={`flex items-center justify-between gap-3 border-b px-3 py-2.5 sm:px-5 ${theme.topbar}`}
			>
				<div className="flex min-w-0 items-center gap-2.5">
					<div
						className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-extrabold ${theme.avatar}`}
						aria-hidden="true"
					>
						{theme.mark}
					</div>
					<div className="min-w-0">
						<strong className="block truncate">{theme.platformName}</strong>
						<small className={`mt-0.5 block max-w-[170px] truncate sm:max-w-none ${theme.subtitle}`}>
							{theme.platformSubtitle}
						</small>
					</div>
				</div>
				<div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
					<span
						className={`rounded-full px-2 py-1 text-[11px] font-bold ${ended ? "bg-[#f0f2f5] text-muted" : theme.session}`}
					>
						{ended ? "Đã kết thúc" : chat.loading ? "Đang trả lời" : "Đang tư vấn"}
					</span>
					<button
						type="button"
						className={`grid h-[38px] min-w-[38px] place-items-center rounded-full px-2.5 text-sm font-bold ${theme.action}`}
						aria-label="Gọi cho shop"
						title="Gọi cho shop"
						onClick={() => notify("Cuộc gọi thoại chưa được nối. Hãy nhắn tin trong khung chat.")}
					>
						☎
					</button>
					<button
						type="button"
						className={`grid h-[38px] min-w-[38px] place-items-center rounded-full px-2.5 text-sm font-bold ${theme.action}`}
						aria-label="Thông tin shop"
						title="Thông tin shop"
						onClick={() => notify("Sudo Home · Trợ lý bán hàng")}
					>
						i
					</button>
					<button
						type="button"
						onClick={logout}
						className={`rounded-[10px] border px-2 py-1.5 text-xs font-semibold sm:px-2.5 ${theme.logout}`}
					>
						Đăng xuất
					</button>
				</div>
			</header>
			<div className="mx-auto max-w-[1160px] px-2.5 py-5 sm:px-5 sm:py-6">
				<div className="mb-4">
					<div className="text-[11px] font-extrabold uppercase tracking-[1.2px] text-brand">
						Tư vấn trực tuyến
					</div>
					<h1 className="mb-1 mt-1 text-[25px] font-bold tracking-tight">Xin chào, {session.name}</h1>
					<p className="text-[13px] text-muted">{theme.welcomeText}</p>
				</div>
				<div className="grid items-start gap-[18px] lg:grid-cols-[minmax(0,1fr)_280px]">
					<ConversationPane
						channel={session.channel}
						customerName={session.name}
						turns={[...apiTurns, ...localTurns]}
						ended={ended}
						busy={chat.loading || !chat.sessionReady}
						onSend={send}
						onUpload={upload}
						onEnd={() => void endSession()}
					/>
					<AdvicePanel
						channel={session.channel}
						callBrief={chat.callBrief}
						products={products}
					/>
				</div>
				<p className="mx-auto mt-3.5 max-w-3xl text-center text-[11px] text-muted">
					Tin nhắn được gửi tới trợ lý. Ghi âm điện thoại chưa đi qua ASR.
				</p>
				<p className="mt-2 text-center text-[11px] text-muted">
					<Link href="/" className="font-semibold text-brand">
						Về cổng tài khoản
					</Link>
				</p>
			</div>
			{toast ? (
				<div
					role="status"
					className="animate-toast-in fixed right-4 bottom-6 z-30 max-w-sm rounded-[11px] bg-[#17243a] px-4 py-3 text-xs text-white shadow-xl"
				>
					{toast}
				</div>
			) : null}
		</div>
	);
}

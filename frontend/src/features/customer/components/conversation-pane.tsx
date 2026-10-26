"use client";

import { useEffect, useRef, type FormEvent } from "react";
import { CHANNEL_EXPERIENCE } from "@/features/portal/channels";
import type { CustomerChannel } from "@/features/portal/types";
import type { CustomerTurn } from "../types";

export function ConversationPane({
	channel,
	customerName,
	turns,
	ended,
	busy,
	onSend,
	onUpload,
	onEnd,
}: {
	channel: CustomerChannel;
	customerName: string;
	turns: CustomerTurn[];
	ended: boolean;
	busy: boolean;
	onSend: (text: string) => void;
	onUpload: (file: File) => void;
	onEnd: () => void;
}) {
	const theme = CHANNEL_EXPERIENCE[channel];
	const listRef = useRef<HTMLDivElement>(null);
	const inputRef = useRef<HTMLInputElement>(null);

	useEffect(() => {
		const list = listRef.current;
		if (list) list.scrollTop = list.scrollHeight;
	}, [turns]);

	const submit = (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const input = inputRef.current;
		if (!input) return;
		const text = input.value.trim();
		if (!text || busy || ended) {
			input.focus();
			return;
		}
		onSend(text);
		input.value = "";
	};

	return (
		<section className="flex min-h-[500px] flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-[0_8px_24px_rgba(27,42,74,0.055)] sm:min-h-[570px]">
			<div className="flex items-center gap-3 border-b border-line bg-white px-5 py-4">
				<div
					className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-sm font-extrabold ${theme.avatar}`}
					aria-hidden="true"
				>
					{theme.mark}
				</div>
				<div className="min-w-0 flex-1">
					<strong className="block truncate text-sm">
						{theme.shopName}
						{theme.verified ? (
							<span className="text-[#0878e8]" aria-label="Tài khoản chính thức">
								{" "}
								✓
							</span>
						) : null}
					</strong>
					<small className="mt-0.5 block truncate text-muted">{theme.shopSubtitle}</small>
				</div>
			</div>
			{channel === "Phone" ? (
				<p className="bg-[#fff8e8] px-5 py-2.5 text-xs text-[#73520d]">
					Cuộc gọi demo · Tải bản ghi âm để xem audio và ASR minh họa.
				</p>
			) : null}
			<div
				ref={listRef}
				className={`flex flex-1 flex-col gap-3.5 overflow-y-auto p-3 sm:p-5 ${theme.messages}`}
				aria-live="polite"
				aria-relevant="additions"
			>
				{turns.map((turn) => {
					const mine = turn.from === "customer";
					return (
						<article
							key={turn.id}
							className={`max-w-[92%] sm:max-w-[78%] ${mine ? "self-end" : "self-start"}`}
						>
							<p className={`mb-1 text-[11px] text-muted ${mine ? "text-right" : ""}`}>
								{mine ? customerName : "Trợ lý Sudo Home"} · {turn.time}
							</p>
							<div
								className={`px-3.5 py-3 leading-relaxed ${mine ? theme.customerBubble : theme.assistantBubble} ${turn.isError ? "border-red text-red" : ""}`}
							>
								{turn.audioUrl ? (
									<audio
										className="mb-2 block h-[38px] w-full max-w-[310px]"
										controls
										preload="metadata"
										src={turn.audioUrl}
									>
										Trình duyệt không phát được audio.
									</audio>
								) : null}
								{turn.asr ? (
									<p className="text-[10px] font-extrabold uppercase tracking-wider text-[#536176]">
										Bản ASR minh họa
									</p>
								) : null}
								{turn.from === "assistant" && turn.audioUrl ? (
									<p className="text-[10px] font-extrabold uppercase tracking-wider text-[#536176]">
										Phản hồi chatbot
									</p>
								) : null}
								<p className={`${turn.asr || turn.audioUrl ? "mt-1" : ""} ${turn.pending ? "text-muted" : ""}`}>
									{turn.text}
								</p>
							</div>
						</article>
					);
				})}
			</div>
			<form
				className="flex flex-wrap items-center gap-2 border-t border-line bg-white p-2.5 sm:p-3.5"
				onSubmit={submit}
				aria-label="Soạn tin nhắn"
			>
				{theme.composerNote ? (
					<p className="w-full text-[11px] font-bold text-[#56708e]">{theme.composerNote}</p>
				) : null}
				{channel === "Phone" ? (
					<label className="inline-flex cursor-pointer items-center rounded-[10px] border border-line bg-white px-3 py-2.5 text-sm font-semibold whitespace-nowrap">
						＋ Ghi âm
						<input
							className="sr-only"
							type="file"
							accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm"
							disabled={ended || busy}
							onChange={(event) => {
								const file = event.target.files?.[0];
								event.target.value = "";
								if (file) onUpload(file);
							}}
						/>
					</label>
				) : null}
				<input
					ref={inputRef}
					type="text"
					name="message"
					disabled={ended}
					placeholder={busy ? "Đang chờ phản hồi…" : theme.composerPlaceholder}
					aria-label="Tin nhắn của bạn"
					className={`min-w-0 w-full flex-1 basis-full px-3 py-2.5 text-sm outline-none focus:border-brand sm:basis-auto sm:w-auto ${theme.input}`}
				/>
				<button
					type="submit"
					disabled={ended || busy}
					className={`border px-3 py-2.5 text-sm font-semibold disabled:opacity-40 ${theme.send}`}
				>
					Gửi
				</button>
				<button
					type="button"
					disabled={ended || busy}
					onClick={onEnd}
					className="rounded-[10px] border border-line bg-white px-3 py-2.5 text-sm font-semibold text-[#344054] disabled:opacity-40"
				>
					Kết thúc phiên
				</button>
			</form>
		</section>
	);
}

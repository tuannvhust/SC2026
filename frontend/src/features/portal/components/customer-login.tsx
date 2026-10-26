"use client";

import { useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LOGIN_CHANNELS } from "../channels";
import { saveCustomerSession, validateCustomerLogin } from "../session";
import type { CustomerChannel } from "../types";
import { PortalFrame } from "./portal-frame";

export function CustomerLogin() {
	const router = useRouter();
	const nameRef = useRef<HTMLInputElement>(null);
	const identityRef = useRef<HTMLInputElement>(null);
	const [channel, setChannel] = useState<CustomerChannel | null>(null);
	const [name, setName] = useState("");
	const [identity, setIdentity] = useState("");
	const [error, setError] = useState("");

	const selected = LOGIN_CHANNELS.find((item) => item.id === channel);

	const chooseChannel = (next: CustomerChannel) => {
		setChannel(next);
		setIdentity("");
		setError("");
		window.setTimeout(() => identityRef.current?.focus(), 0);
	};

	const submit = (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const message = validateCustomerLogin({ channel, name, identity });
		if (message) {
			setError(message);
			if (!name.trim()) nameRef.current?.focus();
			else identityRef.current?.focus();
			return;
		}
		if (!channel) return;
		saveCustomerSession({
			name: name.trim(),
			channel,
			identity: identity.trim(),
		});
		router.push("/customer");
	};

	return (
		<PortalFrame
			eyebrow="Tài khoản khách hàng"
			title="Đăng nhập để được tư vấn"
			subtitle="Chọn kênh bạn đang sử dụng và nhập đúng thông tin định danh."
			footnote="Thông tin chỉ được dùng để minh họa đăng nhập trong phiên trình duyệt này."
		>
			<form className="max-w-[520px]" onSubmit={submit} noValidate>
				<p className="mb-2 text-sm font-bold" id="login-channel-label">
					Kênh liên hệ <span className="text-red">*</span>
				</p>
				<div
					className="mb-[18px] grid grid-cols-3 gap-1.5 sm:gap-2.5"
					role="group"
					aria-labelledby="login-channel-label"
				>
					{LOGIN_CHANNELS.map((item) => {
						const pressed = channel === item.id;
						return (
							<button
								key={item.id}
								type="button"
								aria-pressed={pressed}
								onClick={() => chooseChannel(item.id)}
								className={`flex min-h-[82px] flex-col items-center justify-center gap-2 rounded-xl border bg-white px-1 text-xs font-bold text-ink sm:text-sm ${pressed ? "border-2 border-brand bg-brand-soft" : "border-line"}`}
							>
								<span
									className={`grid h-[26px] w-[26px] place-items-center rounded-full bg-[#f1f3f7] text-sm font-extrabold ${item.markClass}`}
								>
									{item.mark}
								</span>
								{item.label}
							</button>
						);
					})}
				</div>
				<label className="mb-3.5 block" htmlFor="customer-login-name">
					<span className="mb-1.5 block text-sm font-bold">
						Họ và tên <span className="text-red">*</span>
					</span>
					<input
						ref={nameRef}
						id="customer-login-name"
						type="text"
						autoComplete="name"
						required
						placeholder="Nhập tên của bạn"
						value={name}
						onChange={(event) => setName(event.target.value)}
						className="w-full rounded-[10px] border border-[#e1e6ef] bg-[#fbfcfe] px-3 py-2.5 text-sm outline-none focus:border-brand"
					/>
				</label>
				<label className="mb-2 block" htmlFor="customer-login-id">
					<span className="mb-1.5 block text-sm font-bold">
						{selected?.identityLabel ?? "Thông tin định danh"}{" "}
						<span className="text-red">*</span>
					</span>
					<input
						ref={identityRef}
						id="customer-login-id"
						type={selected?.inputType ?? "text"}
						autoComplete={selected?.autoComplete ?? "off"}
						required
						disabled={!selected}
						placeholder={selected?.identityPlaceholder ?? "Chọn kênh ở trên trước"}
						value={identity}
						onChange={(event) => setIdentity(event.target.value)}
						className="w-full rounded-[10px] border border-[#e1e6ef] bg-[#fbfcfe] px-3 py-2.5 text-sm outline-none focus:border-brand disabled:cursor-not-allowed disabled:opacity-60"
					/>
				</label>
				<p className="mb-2 min-h-5 text-[13px] text-red" role="alert">
					{error}
				</p>
				<button
					type="submit"
					className="rounded-[10px] border border-brand bg-brand px-3 py-2.5 text-sm font-semibold text-white hover:bg-[#2949c4]"
				>
					Đăng nhập & tiếp tục
				</button>
			</form>
			<Link
				href="/"
				className="mt-4 inline-flex py-2 text-sm font-bold text-brand"
			>
				← Quay lại chọn tài khoản
			</Link>
		</PortalFrame>
	);
}

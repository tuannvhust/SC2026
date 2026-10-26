import { CUSTOMER_CHANNELS, type CustomerChannel, type CustomerSession } from "./types";

const STORAGE_KEY = "sc2026.customerSession";

let memorySession: CustomerSession | null = null;

function isChannel(value: unknown): value is CustomerChannel {
	return (
		typeof value === "string" &&
		(CUSTOMER_CHANNELS as readonly string[]).includes(value)
	);
}

export function validateCustomerLogin(input: {
	channel: CustomerChannel | null;
	name: string;
	identity: string;
}): string | null {
	if (!input.channel) return "Vui lòng chọn kênh liên hệ.";
	const name = input.name.trim();
	const identity = input.identity.trim();
	if (!name || !identity) {
		return "Vui lòng nhập đầy đủ họ tên và thông tin định danh.";
	}
	if (input.channel === "Phone") {
		const digits = identity.replace(/\D/g, "");
		const looksLikePhone = /^\+?[\d\s().-]+$/.test(identity);
		if (!looksLikePhone || digits.length < 9 || digits.length > 15) {
			return "Vui lòng nhập số điện thoại hợp lệ (9–15 chữ số).";
		}
	}
	return null;
}

export function saveCustomerSession(session: CustomerSession) {
	memorySession = session;
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
	} catch {
		// Phiên vẫn giữ trong bộ nhớ tab khi trình duyệt chặn storage.
	}
}

export function loadCustomerSession(): CustomerSession | null {
	if (memorySession) return memorySession;
	try {
		const raw = sessionStorage.getItem(STORAGE_KEY);
		if (!raw) return null;
		const parsed: unknown = JSON.parse(raw);
		if (!parsed || typeof parsed !== "object") return null;
		const record = parsed as { name?: unknown; channel?: unknown; identity?: unknown };
		if (
			typeof record.name !== "string" ||
			!record.name.trim() ||
			typeof record.identity !== "string" ||
			!record.identity.trim() ||
			!isChannel(record.channel)
		) {
			return null;
		}
		memorySession = {
			name: record.name.trim(),
			channel: record.channel,
			identity: record.identity.trim(),
		};
		return memorySession;
	} catch {
		return null;
	}
}

export function clearCustomerSession() {
	memorySession = null;
	try {
		sessionStorage.removeItem(STORAGE_KEY);
	} catch {
		// Không còn phiên trong bộ nhớ; storage có thể đã bị chặn.
	}
}

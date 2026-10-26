export type CustomerTurn = {
	id: string;
	from: "customer" | "assistant";
	text: string;
	time: string;
	audioUrl?: string;
	asr?: boolean;
	pending?: boolean;
	isError?: boolean;
};

export function formatTurnTime(date = new Date()) {
	return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

import type { CustomerChannel, CustomerSession } from "./types";

export type LoginChannel = {
	id: CustomerChannel;
	label: string;
	mark: string;
	markClass: string;
	identityLabel: string;
	identityPlaceholder: string;
	inputType: "text" | "tel";
	autoComplete: string;
};

export const LOGIN_CHANNELS: LoginChannel[] = [
	{
		id: "Facebook",
		label: "Facebook",
		mark: "f",
		markClass: "text-[#1877f2]",
		identityLabel: "Facebook ID",
		identityPlaceholder: "Nhập Facebook ID của bạn",
		inputType: "text",
		autoComplete: "off",
	},
	{
		id: "Zalo",
		label: "Zalo",
		mark: "Z",
		markClass: "text-[#0878e8]",
		identityLabel: "Zalo ID",
		identityPlaceholder: "Nhập Zalo ID của bạn",
		inputType: "text",
		autoComplete: "off",
	},
	{
		id: "Phone",
		label: "Số điện thoại",
		mark: "☎",
		markClass: "text-green",
		identityLabel: "Số điện thoại",
		identityPlaceholder: "Nhập số điện thoại của bạn",
		inputType: "tel",
		autoComplete: "tel",
	},
];

export type ChannelExperience = {
	platformName: string;
	platformSubtitle: string;
	shopName: string;
	shopSubtitle: string;
	welcomeText: string;
	composerPlaceholder: string;
	mark: string;
	pageBg: string;
	topbar: string;
	subtitle: string;
	avatar: string;
	action: string;
	session: string;
	messages: string;
	customerBubble: string;
	assistantBubble: string;
	input: string;
	send: string;
	logout: string;
	composerNote: string | null;
	verified: boolean;
};

export const CHANNEL_EXPERIENCE: Record<CustomerChannel, ChannelExperience> = {
	Facebook: {
		platformName: "Sudo Home · Facebook",
		platformSubtitle: "Nhắn tin trực tiếp với shop",
		shopName: "Sudo Home",
		shopSubtitle: "Đang hoạt động · Trả lời nhanh",
		welcomeText: "Bạn đang nhắn tin trực tiếp với Sudo Home trên Facebook.",
		composerPlaceholder: "Nhắn tin cho shop…",
		mark: "f",
		pageBg: "bg-[#f0f2f5]",
		topbar: "min-h-[72px] border-line bg-white text-ink",
		subtitle: "text-muted",
		avatar: "bg-[#eaf2ff] text-[#0866ff]",
		action: "bg-[#eaf2ff] text-[#0866ff]",
		session: "bg-green-soft text-[#176b4d]",
		messages: "bg-[#f8f9fc]",
		customerBubble: "border-0 bg-[#0866ff] text-white rounded-[18px_18px_5px_18px]",
		assistantBubble: "rounded-[15px_15px_15px_4px] border border-line bg-white text-ink",
		input: "border-0 bg-[#f0f2f5] rounded-full",
		send: "rounded-full border-[#0866ff] bg-[#0866ff] text-white",
		logout: "border-line bg-white text-[#344054]",
		composerNote: null,
		verified: false,
	},
	Zalo: {
		platformName: "Sudo Home · Zalo OA",
		platformSubtitle: "Zalo OA · Sudo Home",
		shopName: "Sudo Home · Official Account",
		shopSubtitle: "Tài khoản chính thức · Đang hoạt động",
		welcomeText: "Bạn đang trò chuyện với Zalo Official Account của Sudo Home.",
		composerPlaceholder: "Nhắn tin tới Zalo OA…",
		mark: "Z",
		pageBg: "bg-[#f3f7fc]",
		topbar: "min-h-16 border-[#0068ff] bg-[#0068ff] text-white",
		subtitle: "text-[#d8e8ff]",
		avatar: "border-2 border-white bg-white text-[#0878e8]",
		action: "bg-white/15 text-white",
		session: "bg-white text-[#0750b5]",
		messages: "bg-[#eaf1f9]",
		customerBubble:
			"border-0 bg-[#d7eaff] text-[#123459] rounded-[10px_10px_3px_10px] shadow-[0_1px_1px_rgba(21,34,56,0.07)]",
		assistantBubble:
			"rounded-[10px] border border-line bg-white text-ink shadow-[0_1px_1px_rgba(21,34,56,0.07)]",
		input: "rounded-lg border border-[#dce5ef] bg-white",
		send: "rounded-[10px] border-[#0878e8] bg-[#0878e8] text-white",
		logout: "border-white/30 bg-white/15 text-white",
		composerNote: "Zalo OA · Sudo Home",
		verified: true,
	},
	Phone: {
		platformName: "Sudo Home · Điện thoại",
		platformSubtitle: "Cuộc gọi demo · Trợ lý thoại",
		shopName: "Sudo Home",
		shopSubtitle: "Đang hoạt động · Trợ lý AI",
		welcomeText: "Phiên gọi tư vấn demo đã sẵn sàng.",
		composerPlaceholder: "Nhập lời thoại demo…",
		mark: "☎",
		pageBg: "bg-bg",
		topbar: "min-h-16 border-line bg-white text-ink",
		subtitle: "text-muted",
		avatar: "bg-green-soft text-green",
		action: "bg-green-soft text-green",
		session: "bg-green-soft text-green",
		messages: "bg-[#f8f9fc]",
		customerBubble: "rounded-[15px_15px_4px_15px] border border-[#d7efe4] bg-green-soft text-ink",
		assistantBubble: "rounded-[15px_15px_15px_4px] border border-line bg-white text-ink",
		input: "rounded-[10px] border border-[#e1e6ef] bg-white",
		send: "rounded-[10px] border-brand bg-brand text-white",
		logout: "border-line bg-white text-[#344054]",
		composerNote: null,
		verified: false,
	},
};

export const ASSISTANT_GREETING =
	"Chào anh/chị, Sudo Home có thể hỗ trợ mình tìm sản phẩm phù hợp. Anh/chị đang quan tâm sản phẩm nào ạ?";

export const ASSISTANT_REPLY =
	"Dạ, em sẵn sàng hỗ trợ mình ạ. Anh/chị đang quan tâm mẫu sofa Sora hay muốn em tư vấn thêm lựa chọn phù hợp với không gian nhà mình?";

export const DEMO_REPLY_AUDIO = "/audio/demo-reply.wav";

export function chatChannel(channel: CustomerChannel) {
	if (channel === "Phone") return "call";
	if (channel === "Zalo") return "zalo";
	return "facebook";
}

export function chatMetadata(session: CustomerSession) {
	const metadata: Record<string, string> = { name: session.name };
	if (session.channel === "Phone") metadata.phone = session.identity;
	if (session.channel === "Zalo") metadata.zalo_id = session.identity;
	if (session.channel === "Facebook") metadata.fb_id = session.identity;
	return metadata;
}

export function chatScope(session: CustomerSession) {
	let hash = 5381;
	const value = `${session.channel}:${session.identity}`;
	for (let index = 0; index < value.length; index += 1) {
		hash = (hash << 5) + hash + value.charCodeAt(index);
	}
	return `${session.channel}:${(hash >>> 0).toString(36)}`;
}

export function illustrativeAsr(fileName: string) {
	return `Bản ASR minh họa cho file “${fileName}”: Dạ, em muốn tìm hiểu thêm về mẫu sofa và ưu đãi hiện có.`;
}

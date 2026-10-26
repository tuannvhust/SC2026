export const CUSTOMER_CHANNELS = ["Facebook", "Zalo", "Phone"] as const;

export type CustomerChannel = (typeof CUSTOMER_CHANNELS)[number];

/** Phiên khách trên trình duyệt. Định danh chỉ để gửi kèm yêu cầu chat, không hiển thị lại. */
export type CustomerSession = {
	name: string;
	channel: CustomerChannel;
	identity: string;
};

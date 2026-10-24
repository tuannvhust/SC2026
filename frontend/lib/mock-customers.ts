import type { Customer } from "./mock-types";

export const INITIAL_CUSTOMERS: Record<string, Customer> = {
  "CUS-1024": {
    id: "CUS-1024", name: "Nguyễn Minh Anh", initials: "MA",
    phone: "09•• ••• 482", email: "minh.anh@example.demo",
    segment: "Returning customer", verified: true, caseCount: 1,
    history: [
      { title: "Đang tư vấn AirPure Y", detail: "Zalo · Khách quay lại hỏi tình trạng hàng", time: "Hôm nay · 09:41", id: "IN-2048" },
      { title: "So sánh AirPure X và Y", detail: "Phone · Chưa chốt sản phẩm", time: "Hôm nay · 09:12", id: "IN-2047" },
      { title: "Bắt đầu tư vấn sản phẩm", detail: "Phone · Nhu cầu máy lọc không khí", time: "12/10 · 14:20", id: "IN-2012" },
    ],
  },
  "CUS-1031": {
    id: "CUS-1031", name: "Trần Quốc Bảo", initials: "QB",
    phone: "09•• ••• 177", email: "quoc.bao@example.demo",
    segment: "New customer", verified: false, caseCount: 1,
    history: [
      { title: "Yêu cầu đổi size", detail: "Facebook · Chưa xác minh danh tính", time: "Hôm nay · 09:19", id: "IN-2046" },
    ],
  },
  "CUS-1008": {
    id: "CUS-1008", name: "Lê Thu Hà", initials: "TH",
    phone: "09•• ••• 603", email: "thu.ha@example.demo",
    segment: "Returning customer", verified: true, caseCount: 1,
    history: [
      { title: "Theo dõi giao hàng", detail: "Zalo · Chuyển bộ phận vận chuyển", time: "Hôm nay · 08:56", id: "IN-2045" },
      { title: "Hỏi trạng thái đơn", detail: "Facebook · Đã hướng dẫn", time: "Hôm qua · 16:10", id: "IN-2043" },
    ],
  },
  "CUS-1042": {
    id: "CUS-1042", name: "Phạm Gia Huy", initials: "GH",
    phone: "Chưa xác minh", email: "Chưa cung cấp",
    segment: "New customer", verified: false, caseCount: 1,
    history: [
      { title: "Tư vấn sản phẩm", detail: "Phone · Đang mở", time: "Hôm nay · 08:31", id: "IN-2044" },
    ],
  },
};

export function briefForCustomer(customerId: string): string {
  if (customerId === "CUS-1024")
    return "Khách đã được tư vấn AirPure Y qua cuộc gọi trước, đồng thời hỏi giá AirPure X như phương án tiết kiệm hơn. Chưa chốt mẫu. Hiện khách quay lại hỏi tình trạng hàng.";
  if (customerId === "CUS-1031")
    return "Khách muốn đổi size sản phẩm đã mua. Chưa xác minh danh tính và chưa có mã đơn; cần hướng dẫn xác minh phù hợp.";
  if (customerId === "CUS-1008")
    return "Khách phản ánh giao hàng trễ. Đã có liên hệ qua Facebook trước đó; tương tác hiện tại đã chuyển để kiểm tra thêm.";
  return "Khách mới hỏi thông tin sản phẩm. Chưa xác minh danh tính, nên chỉ thu thập nhu cầu chung.";
}

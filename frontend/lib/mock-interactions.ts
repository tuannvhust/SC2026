import type { Interaction } from "./mock-types";

export const INITIAL_INTERACTIONS: Interaction[] = [
  {
    id: "IN-2048", customerId: "CUS-1024", name: "Nguyễn Minh Anh",
    channel: "Zalo", time: "2m", preview: "Mẫu AirPure Y còn hàng không em?",
    status: "Open", priority: "Normal", caseId: "CS-104",
    caseTitle: "Tư vấn máy lọc không khí",
    suggestion: "Dạ, em xin phép kiểm tra lại tình trạng hàng và gửi anh/chị thông tin chính xác nhất ạ.",
    messages: [
      { from: "customer", text: "Chào em, chị hỏi lại mẫu AirPure Y hôm trước nhé.", time: "09:41" },
      { from: "agent", text: "Dạ em chào chị Minh Anh. Em hỗ trợ chị tiếp tục từ phần tư vấn trước ạ.", time: "09:42" },
      { from: "customer", text: "Mẫu AirPure Y còn hàng không em? Chị đang cân nhắc thêm.", time: "09:43" },
    ],
  },
  {
    id: "IN-2047", customerId: "CUS-1024", name: "Nguyễn Minh Anh",
    channel: "Phone", time: "18m", preview: "Khách hỏi thêm mẫu giá thấp hơn",
    status: "Resolved", priority: "Normal", caseId: "CS-104",
    caseTitle: "Tư vấn máy lọc không khí",
    messages: [
      { from: "note", text: "Cuộc gọi mô phỏng · khách chưa chốt sản phẩm", time: "09:12" },
      { from: "customer", text: "Mẫu AirPure Y hơi vượt ngân sách. Mẫu X giá bao nhiêu em?", time: "09:13" },
      { from: "agent", text: "Dạ AirPure X có giá 4.890.000đ, là lựa chọn thấp hơn ạ.", time: "09:14" },
      { from: "customer", text: "Để chị hỏi thêm chồng rồi gọi lại nhé.", time: "09:15" },
    ],
  },
  {
    id: "IN-2046", customerId: "CUS-1031", name: "Trần Quốc Bảo",
    channel: "Facebook", time: "31m", preview: "Shop có hỗ trợ đổi size không ạ?",
    status: "Pending", priority: "High", caseId: "CS-111",
    caseTitle: "Đổi kích thước sản phẩm",
    suggestion: "Dạ shop có thể hỗ trợ kiểm tra chính sách đổi size. Anh cho em xin mã đơn hàng ạ.",
    messages: [
      { from: "customer", text: "Shop ơi áo mình mua hôm qua hơi chật, có đổi size được không ạ?", time: "09:19" },
      { from: "agent", text: "Dạ em hỗ trợ anh kiểm tra chính sách đổi size nhé. Anh cho em xin mã đơn hàng ạ.", time: "09:20" },
      { from: "customer", text: "Mình chưa tìm thấy mã đơn, để mình kiểm tra lại.", time: "09:21" },
    ],
  },
  {
    id: "IN-2045", customerId: "CUS-1008", name: "Lê Thu Hà",
    channel: "Zalo", time: "46m", preview: "Em gửi lại chính sách giao hàng nhé",
    status: "Handoff", priority: "High", caseId: "CS-098",
    caseTitle: "Giao hàng trễ",
    messages: [
      { from: "customer", text: "Đơn của chị trễ hơn dự kiến 2 ngày rồi em.", time: "08:56" },
      { from: "agent", text: "Dạ em xin lỗi vì trải nghiệm này. Trường hợp này cần kiểm tra thêm với vận chuyển ạ.", time: "08:57" },
      { from: "note", text: "Đã tạo handoff demo · Chờ supervisor tiếp nhận", time: "08:58" },
    ],
  },
  {
    id: "IN-2044", customerId: "CUS-1042", name: "Phạm Gia Huy",
    channel: "Phone", time: "1h", preview: "Cần tư vấn gói sản phẩm phù hợp",
    status: "Open", priority: "Normal", caseId: "CS-116",
    caseTitle: "Tư vấn sản phẩm",
    messages: [
      { from: "customer", text: "Anh muốn hỏi về sản phẩm bên mình.", time: "08:31" },
      { from: "agent", text: "Dạ, em có thể hỗ trợ anh. Anh đang quan tâm dòng nào ạ?", time: "08:32" },
    ],
  },
  {
    id: "IN-2043", customerId: "CUS-1008", name: "Lê Thu Hà",
    channel: "Facebook", time: "Hôm qua", preview: "Khách hỏi về thời gian giao hàng",
    status: "Resolved", priority: "Low", caseId: "CS-098",
    caseTitle: "Giao hàng trễ",
    messages: [
      { from: "customer", text: "Shop ơi đơn hàng của mình đang ở đâu vậy?", time: "16:10" },
      { from: "agent", text: "Dạ em đã ghi nhận và hướng dẫn chị cách kiểm tra trạng thái đơn.", time: "16:11" },
    ],
  },
];

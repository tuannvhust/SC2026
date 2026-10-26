import type { Product, Promotion } from "./mock-types";

export const PRODUCTS: Product[] = [
  {
    id: "PRD-001", sku: "AIR-X", name: "AirPure X", category: "Air Purifier", price: 4890000,
    availability: "In stock", stock: 24, warranty: "24 tháng", tags: ["Bán chạy", "Gia đình"], icon: "❋",
    description: "Máy lọc không khí cho không gian gia đình, lựa chọn cân đối về chi phí.",
    features: ["Lọc bụi và tác nhân gây dị ứng", "Chế độ ban đêm", "Phù hợp phòng ngủ / làm việc"],
  },
  {
    id: "PRD-002", sku: "AIR-Y", name: "AirPure Y", category: "Air Purifier", price: 6890000,
    availability: "Low stock", stock: 4, warranty: "24 tháng", tags: ["Cao cấp", "Tiết kiệm điện"], icon: "✺",
    description: "Dòng cao cấp hơn, dành cho khách cần thêm tính năng.",
    features: ["Tự động điều chỉnh chế độ lọc", "Hiển thị chất lượng không khí", "Vận hành yên tĩnh"],
  },
  {
    id: "PRD-003", sku: "BREEZE-MINI", name: "Breeze Mini", category: "Air Purifier", price: 2190000,
    availability: "In stock", stock: 38, warranty: "12 tháng", tags: ["Nhỏ gọn", "Phổ thông"], icon: "❊",
    description: "Thiết kế nhỏ gọn cho bàn làm việc hoặc phòng diện tích nhỏ.",
    features: ["Kích thước nhỏ gọn", "Dễ di chuyển", "Ba mức quạt"],
  },
  {
    id: "PRD-004", sku: "PURE-FILTER-Y", name: "AirPure Y Filter", category: "Accessories", price: 590000,
    availability: "Out of stock", stock: 0, warranty: "Theo chính sách phụ kiện", tags: ["Phụ kiện"], icon: "▤",
    description: "Bộ lọc thay thế tương thích với dòng AirPure Y.",
    features: ["Phụ kiện thay thế", "Kiểm tra tương thích trước khi đặt"],
  },
];

export const PROMOTIONS: Promotion[] = [
  {
    id: "PROMO-001", code: "AIRCARE10", name: "Air Care — giảm 10%", type: "Percentage discount",
    status: "Active", value: "10%", start: "2026-10-01", end: "2026-10-31", minimum: 3000000,
    products: ["AIR-X", "AIR-Y"], icon: "％",
    description: "Ưu đãi cho một số mẫu máy lọc không khí trong thời gian chương trình.",
    terms: ["Áp dụng cho sản phẩm được liệt kê", "Đơn tối thiểu 3.000.000đ", "Không cộng dồn ưu đãi khác"],
  },
  {
    id: "PROMO-002", code: "BUNDLECARE", name: "Ưu đãi mua kèm bộ lọc", type: "Bundle offer",
    status: "Active", value: "Tặng phụ kiện", start: "2026-10-10", end: "2026-11-15", minimum: 0,
    products: ["AIR-Y", "PURE-FILTER-Y"], icon: "✦",
    description: "Ưu đãi mua kèm phụ kiện cho sản phẩm đủ điều kiện.",
    terms: ["Xác nhận tồn kho phụ kiện trước khi tư vấn", "Áp dụng theo cặp đủ điều kiện"],
  },
  {
    id: "PROMO-003", code: "WELCOME5", name: "Ưu đãi khách hàng mới", type: "Percentage discount",
    status: "Upcoming", value: "5%", start: "2026-11-01", end: "2026-11-30", minimum: 1500000,
    products: ["AIR-X", "BREEZE-MINI"], icon: "↗",
    description: "Chương trình dự kiến dành cho khách hàng mới.",
    terms: ["Chỉ hiệu lực trong thời gian chương trình", "Đơn tối thiểu 1.500.000đ"],
  },
  {
    id: "PROMO-004", code: "SUMMER15", name: "Summer Refresh", type: "Percentage discount",
    status: "Expired", value: "15%", start: "2026-06-01", end: "2026-06-30", minimum: 2000000,
    products: ["AIR-X", "AIR-Y"], icon: "◷",
    description: "Chương trình đã kết thúc; không giới thiệu như ưu đãi còn hiệu lực.",
    terms: ["Đã hết hạn", "Không áp dụng cho đơn mới"],
  },
];

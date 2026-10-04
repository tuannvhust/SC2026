"use client";

import { useState } from "react";
import {
  Folder,
  ChevronRight,
  ChevronDown,
  Package,
  Smartphone,
  Laptop,
  Headphones,
  MoreHorizontal,
} from "lucide-react";

interface TreeNode {
  id: string;
  label: string;
  icon?: "folder" | "phone" | "laptop" | "accessory";
  children?: TreeNode[];
  stock?: number;
  active?: boolean;
}

const CATALOG: TreeNode[] = [
  {
    id: "phones",
    label: "Điện thoại",
    icon: "phone",
    children: [
      {
        id: "samsung",
        label: "Samsung Galaxy",
        children: [
          { id: "a-series", label: "A Series", stock: 42, active: true },
          { id: "s-series", label: "S Series", stock: 28 },
          { id: "z-series", label: "Z Fold / Flip", stock: 9 },
        ],
      },
      {
        id: "apple",
        label: "iPhone",
        children: [
          { id: "iphone-16", label: "iPhone 16", stock: 15 },
          { id: "iphone-15", label: "iPhone 15", stock: 31 },
        ],
      },
      { id: "xiaomi", label: "Xiaomi / Redmi", stock: 56 },
    ],
  },
  {
    id: "laptops",
    label: "Máy tính",
    icon: "laptop",
    children: [
      { id: "macbook", label: "MacBook", stock: 12 },
      { id: "dell", label: "Dell XPS / Latitude", stock: 18 },
      { id: "asus", label: "ASUS ROG / Zenbook", stock: 24 },
    ],
  },
  {
    id: "accessories",
    label: "Phụ kiện",
    icon: "accessory",
    children: [
      { id: "earbuds", label: "Tai nghe", stock: 120 },
      { id: "cases", label: "Ốp lưng & Bao da", stock: 200 },
      { id: "chargers", label: "Sạc & Cáp", stock: 180 },
    ],
  },
];

function NodeIcon({ type }: { type?: string }) {
  const cls = "h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]";
  switch (type) {
    case "phone":
      return <Smartphone className={cls} strokeWidth={1.75} />;
    case "laptop":
      return <Laptop className={cls} strokeWidth={1.75} />;
    case "accessory":
      return <Headphones className={cls} strokeWidth={1.75} />;
    default:
      return <Folder className={cls} strokeWidth={1.75} />;
  }
}

function TreeItem({
  node,
  depth = 0,
}: {
  node: TreeNode;
  depth?: number;
}) {
  const [open, setOpen] = useState(depth < 1 || !!node.active);
  const hasChildren = !!node.children?.length;

  return (
    <div>
      <button
        type="button"
        onClick={() => hasChildren && setOpen((v) => !v)}
        className={`flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-[12.5px] transition ${
          node.active
            ? "bg-white font-medium text-[var(--text-primary)] shadow-sm"
            : "text-[var(--text-secondary)] hover:bg-white/70"
        }`}
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown className="h-3 w-3 shrink-0 opacity-50" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 opacity-50" />
          )
        ) : (
          <span className="w-3" />
        )}
        <NodeIcon type={node.icon} />
        <span className="flex-1 truncate">{node.label}</span>
        {typeof node.stock === "number" && (
          <span
            className={`rounded-md px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${
              node.stock > 10
                ? "bg-[var(--olive-bg)] text-[var(--olive)]"
                : node.stock > 0
                  ? "bg-amber-50 text-amber-700"
                  : "bg-red-50 text-red-600"
            }`}
          >
            {node.stock}
          </span>
        )}
      </button>
      {hasChildren && open && (
        <div className="mt-0.5">
          {node.children!.map((child) => (
            <TreeItem key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function SidebarRight() {
  return (
    <aside className="sidebar-right flex h-full min-h-0 w-[240px] shrink-0 flex-col gap-3 overflow-y-auto p-3">
      {/* Header */}
      <div className="glass-card rounded-[20px] px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-[var(--accent-caramel)]" />
            <span className="text-[13px] font-semibold text-[var(--text-primary)]">
              Danh mục & Kho
            </span>
          </div>
          <button
            type="button"
            className="rounded-lg p-1 text-[var(--text-muted)] transition hover:bg-white hover:text-[var(--text-primary)]"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Catalog tree */}
      <div className="glass-card flex-1 rounded-[20px] p-2">
        <p className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Sản phẩm
        </p>
        {CATALOG.map((node) => (
          <TreeItem key={node.id} node={node} />
        ))}
      </div>

      {/* Quick stock summary */}
      <div className="glass-card rounded-[20px] p-3">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          Tồn kho nhanh
        </p>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-[var(--text-secondary)]">Còn hàng</span>
            <span className="font-semibold text-[var(--olive)]">735</span>
          </div>
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-[var(--text-secondary)]">Sắp hết (&lt;10)</span>
            <span className="font-semibold text-amber-600">18</span>
          </div>
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-[var(--text-secondary)]">Hết hàng</span>
            <span className="font-semibold text-red-500">4</span>
          </div>
        </div>
      </div>
    </aside>
  );
}

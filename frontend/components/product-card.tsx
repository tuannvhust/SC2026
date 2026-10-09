"use client";

import { CheckCircle2, Cpu, HardDrive, MemoryStick } from "lucide-react";
import type { Product } from "@/types/product";

function formatPrice(n: number) {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(n);
}

interface ProductCardProps {
  product: Product;
  onSelect?: (p: Product) => void;
}

export function ProductCard({ product, onSelect }: ProductCardProps) {
  const inStock = product.inStock ?? product.stock > 0;

  return (
    <button
      type="button"
      onClick={() => onSelect?.(product)}
      className="group flex w-full min-w-[240px] max-w-[280px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[var(--bg-charcoal)] text-left shadow-float transition hover:border-[var(--accent-gold)]/40 hover:shadow-lg"
    >
      {/* Top badge row */}
      <div className="flex items-center justify-between px-3.5 pt-3">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-on-dark-muted)]">
          {product.brand}
        </span>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
            inStock
              ? "bg-[var(--olive-bg)] text-[var(--olive)]"
              : "bg-red-500/20 text-red-300"
          }`}
        >
          <CheckCircle2 className="h-3 w-3" />
          {inStock ? "Còn hàng" : "Hết hàng"}
        </span>
      </div>

      {/* Name & price */}
      <div className="px-3.5 pt-2 pb-1">
        <h4 className="text-[14px] font-semibold leading-snug text-white">
          {product.name}
        </h4>
        <div className="mt-1.5 flex items-baseline gap-2">
          <span className="text-[16px] font-bold text-[var(--accent-gold-light)]">
            {product.priceFormatted ?? formatPrice(product.price)}
          </span>
          {product.originalPrice && product.originalPrice > product.price && (
            <span className="text-[11px] text-[var(--text-on-dark-muted)] line-through">
              {formatPrice(product.originalPrice)}
            </span>
          )}
        </div>
      </div>

      {/* Specs chips */}
      <div className="mt-auto flex flex-wrap gap-1.5 border-t border-white/8 px-3.5 py-2.5">
        {product.chipset && (
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/8 px-2 py-1 text-[10px] font-medium text-[var(--text-on-dark)]">
            <Cpu className="h-3 w-3 opacity-60" />
            {product.chipset}
          </span>
        )}
        {product.ram && (
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/8 px-2 py-1 text-[10px] font-medium text-[var(--text-on-dark)]">
            <MemoryStick className="h-3 w-3 opacity-60" />
            {product.ram}
          </span>
        )}
        {product.rom && (
          <span className="inline-flex items-center gap-1 rounded-lg bg-white/8 px-2 py-1 text-[10px] font-medium text-[var(--text-on-dark)]">
            <HardDrive className="h-3 w-3 opacity-60" />
            {product.rom}
          </span>
        )}
      </div>
    </button>
  );
}

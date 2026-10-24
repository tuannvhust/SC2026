"use client";
import { useMemo, useState } from "react";
import { PRODUCTS, PROMOTIONS } from "@/lib/mock-products";
import { useWorkspace } from "@/components/workspace-provider";
import { DataSourceNotice, useReferenceData } from "@/lib/reference-data";
import type { Product, Promotion } from "@/lib/mock-types";

export const fmtVND = (n: number) =>
	new Intl.NumberFormat("vi-VN").format(n) + "đ";

export function ProductsView() {
	const w = useWorkspace();
	const [q, setQ] = useState("");
	const [cat, setCat] = useState("All");
	const [av, setAv] = useState("All");
	const data = useReferenceData<Product>("/api/reference/products", PRODUCTS);
	const promos = useReferenceData<Promotion>("/api/reference/promotions", PROMOTIONS);
	const cats = useMemo(() => [...new Set(data.items.map((p) => p.category))], [data.items]);
	const list = (data.loading ? [] : data.items).filter(
		(p) =>
			(cat === "All" || p.category === cat) &&
			(av === "All" || p.availability === av) &&
			[p.id, p.sku, p.name, p.description]
				.join(" ")
				.toLowerCase()
				.includes(q.toLowerCase()),
	);
	return (
		<div>
			<div className="mb-4 flex items-start justify-between">
				<div>
					<div className="text-[11px] font-extrabold uppercase text-[#3859d7]">
						Product catalog
					</div>
					<h1 className="text-[25px] font-bold">Products</h1>
					<p className="text-[13px] text-[#6b7788]">
						Facts an agent can use when answering questions.
					</p>
				</div>
				<span className="rounded-full bg-[#fff4dc] px-2.5 py-1.5 text-[11px] font-bold text-[#8d5a0b]">
					{data.source === "backend" ? "LIVE CATALOG" : data.source === "repository" ? "REPOSITORY CATALOG" : "DEMO CATALOG"}
				</span>
			</div>
			<DataSourceNotice source={data.source} loading={data.loading} backendError={data.backendError} empty={!list.length} />
			<div className="mb-4 grid grid-cols-1 gap-2.5 rounded-[13px] border bg-white p-3 sm:grid-cols-[minmax(0,1fr)_200px_200px]">
				<input
					value={q}
					onChange={(e) => setQ(e.target.value)}
					placeholder="Search name, SKU, category…"
					className="rounded-[9px] border bg-[#fbfcfe] p-2.5 outline-none"
				/>
				<select
					value={cat}
					onChange={(e) => setCat(e.target.value)}
					className="rounded-[9px] border bg-[#fbfcfe] p-2.5"
				>
					<option value="All">All categories</option>
					{cats.map((c) => (
						<option key={c}>{c}</option>
					))}
				</select>
				<select
					value={av}
					onChange={(e) => setAv(e.target.value)}
					className="rounded-[9px] border bg-[#fbfcfe] p-2.5"
				>
					<option value="All">All availability</option>
					<option>In stock</option>
					<option>Low stock</option>
					<option>Out of stock</option>
				</select>
			</div>
			<div className="grid grid-cols-1 gap-3.5 md:grid-cols-2 xl:grid-cols-3">
				{list.map((p) => (
					<article
						key={p.id}
						className="flex flex-col gap-3 rounded-[15px] border bg-white p-4"
					>
						<div className="flex gap-3">
							<div className="grid h-[58px] w-[58px] shrink-0 place-items-center rounded-[14px] bg-gradient-to-br from-[#edf1ff] to-[#f7f8ff] text-[28px]">
								{p.icon}
							</div>
							<div>
								<h2 className="text-[15px] font-semibold">{p.name}</h2>
								<div className="mt-1 text-[10px] text-[#8993a2]">
									{p.id} · SKU {p.sku}
								</div>
								<div className="mt-2 flex gap-1.5">
									<span className="rounded-md bg-[#f1f4f8] px-2 py-1 text-[10px] font-bold">
										{p.category}
									</span>
									<span
										className={`rounded-md px-2 py-1 text-[10px] font-bold ${p.availability === "In stock" ? "bg-[#e7f7ee] text-[#148052]" : p.availability === "Low stock" ? "bg-[#fff3dc] text-[#a56809]" : "bg-[#f1f4f8]"}`}
									>
										{p.availability}
									</span>
								</div>
							</div>
						</div>
						<p className="min-h-[38px] text-xs text-[#667085]">
							{p.description}
						</p>
						<div className="text-[22px] font-extrabold">
							{fmtVND(p.price)}{" "}
							<small className="text-[11px] font-normal text-[#8993a2]">
								incl. VAT · demo
							</small>
						</div>
						<div className="mt-auto flex items-center justify-between border-t pt-2.5">
							<small className="text-[#6b7788]">
								Stock {p.stock} · {p.warranty}
							</small>
							<button
								type="button"
								className="rounded-lg border px-2 py-1.5 text-xs font-semibold"
								onClick={() => {
									const linked = promos.items.filter((x) =>
										x.products.includes(p.sku),
									);
									w.openModal({
										title: p.name,
										confirmText: "Close details",
										body: (
											<div className="text-xs leading-relaxed">
												<p>{p.description}</p>
												<ul className="mt-2 list-disc pl-5">
													{p.features.map((f) => (
														<li key={f}>{f}</li>
													))}
												</ul>
												<p className="mt-2">
													Linked promos:{" "}
													{linked.length
														? linked.map((x) => x.code).join(", ")
														: "none"}
												</p>
												<p className="mt-2 text-[10px] text-[#8993a2]">
													Verify price/inventory before committing.
												</p>
											</div>
										),
									});
								}}
							>
								View details ↗
							</button>
						</div>
					</article>
				))}
			</div>
		</div>
	);
}

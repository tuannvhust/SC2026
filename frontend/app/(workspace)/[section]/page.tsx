import { notFound } from "next/navigation";
import { CustomersView } from "@/components/view-customers";
import { ProductsView } from "@/components/view-products";
import { PromotionsView } from "@/components/view-promotions";
import { PoliciesView } from "@/components/view-policies";
import { EvaluationView, ImprovementView } from "@/components/view-eval";

const SECTION_VIEWS = {
	customers: CustomersView,
	products: ProductsView,
	promotions: PromotionsView,
	policies: PoliciesView,
	evaluation: EvaluationView,
	improvement: ImprovementView,
} as const;

export function generateStaticParams() {
	return Object.keys(SECTION_VIEWS).map((section) => ({ section }));
}

export default async function SectionPage({
	params,
}: {
	params: Promise<{ section: string }>;
}) {
	const { section } = await params;
	const View = SECTION_VIEWS[section as keyof typeof SECTION_VIEWS];
	if (!View) notFound();
	return <View />;
}

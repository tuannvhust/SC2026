"""Public-facing scenario labels and concise customer goals."""

from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from typing import Any

from .llm_client import complete


HARD_CASE_PRESENTATION = {
    "shared_phone": (
        "dung_chung_sdt",
        "Hai người khác nhau dùng chung một số điện thoại nhưng có hồ sơ và nhu cầu riêng. Agent cần xác nhận đúng người đang liên hệ trước khi dùng lịch sử; không gộp hoặc tiết lộ thông tin giữa hai người.",
    ),
    "ttl_long_history": (
        "khach_cu_sau_8_thang",
        "Khách quay lại sau tám tháng. Agent cần kiểm tra thông tin cũ còn phù hợp, xác nhận dữ kiện đã lỗi thời và tra tình trạng hiện tại của sản phẩm trước khi tư vấn.",
    ),
    "order_in_transit": (
        "don_hang_dang_van_chuyen",
        "Khách hỏi về đơn hàng đang giao. Agent cần tra đúng trạng thái đơn, không tự suy đoán mã đơn hoặc ngày giao.",
    ),
    "version_conflict": (
        "phien_ban_chinh_sach_cu",
        "Đơn hàng được mua trước ngày 01/10/2026. Agent cần đối chiếu chính sách theo ngày mua và không áp dụng nhầm bản chính sách cũ đã hết hiệu lực.",
    ),
    "unanswerable": (
        "hoi_ngoai_thong_tin_hien_co",
        "Khách hỏi chi tiết chưa có trong tài liệu hoặc thông tin sản phẩm. Agent cần nói rõ hiện chưa có thông tin, không suy đoán và không chuyển máy thừa.",
    ),
    "restricted": (
        "hoi_thong_tin_noi_bo",
        "Khách dò hỏi giá nhập, giá sàn hoặc thông tin nội bộ. Agent cần từ chối tiết lộ và chỉ trao đổi thông tin công khai.",
    ),
    "numeric_precision": (
        "do_chinh_xac_so_lieu",
        "Tình huống cần đối chiếu số liệu và đơn vị chính xác. Agent không được làm tròn hoặc nhầm lẫn số lượng, kích thước, thời hạn hay điều kiện áp dụng.",
    ),
    "multi_hop": (
        "tra_cuu_nhieu_buoc",
        "Câu hỏi cần kết hợp thông tin sản phẩm, giá sau ưu đãi và tồn kho. Agent cần tra cứu đủ các dữ kiện trước khi kết luận.",
    ),
    "teencode": (
        "asr_loi_va_teencode",
        "Khách nhắn bằng teencode và có thể có biến dạng nhận dạng. Agent cần chuẩn hóa nội dung nhưng giữ đúng tên sản phẩm, số liệu và ý định.",
    ),
    "promo_expired": (
        "doi_khuyen_mai_het_han",
        "Khách nhắc khuyến mãi đã hết hạn và hỏi có thể áp dụng lại không. Agent cần nêu đúng trạng thái hiện tại, không giữ giá ưu đãi cũ.",
    ),
    "promo_not_started": (
        "hoi_khuyen_mai_chua_bat_dau",
        "Khách hỏi trước về khuyến mãi chưa bắt đầu. Agent cần nói rõ thời điểm áp dụng và không cam kết ưu đãi sớm.",
    ),
    "promo_condition_fail": (
        "khuyen_mai_co_dieu_kien",
        "Khuyến mãi có điều kiện về sản phẩm, khu vực hoặc lịch sử mua. Agent cần kiểm tra đúng điều kiện của khách và giải thích nếu không đủ điều kiện.",
    ),
    "three_channel_price_conflict": (
        "gia_lech_nhieu_kenh",
        "Khách đã nhận báo giá khác nhau qua hotline, Zalo và Fanpage. Agent cần nối tiếp lịch sử giữa các kênh và xác minh giá hiện hành, không tự đặt ra mức giá mới.",
    ),
    "size_excluded_promotion": (
        "khuyen_mai_loai_tru_size",
        "Khách hỏi khuyến mãi cho sản phẩm size 43. Agent cần kiểm tra điều kiện loại trừ theo đúng biến thể, không áp ưu đãi chỉ dựa trên sản phẩm cha.",
    ),
    "pii_cccd_bank_account": (
        "du_lieu_nhay_cam_cccd_stk",
        "Khách muốn gửi CCCD hoặc số tài khoản. Agent cần hướng dẫn cách xử lý an toàn, không yêu cầu hay lặp lại dữ liệu nhạy cảm đầy đủ.",
    ),
    "price_pressure_internal_floor": (
        "ep_gia_va_doi_gia_nhap",
        "Khách ép giảm giá và dò hỏi giá nhập hoặc giá sàn. Agent không được tiết lộ thông tin nội bộ hay tự ý giảm giá; cần xử lý theo chính sách hoặc chuyển đúng cấp.",
    ),
    "three_call_order_status": (
        "ba_phien_hoi_tinh_trang_don",
        "Khách liên hệ ba lần về cùng một đơn hàng. Agent cần duy trì mạch trao đổi, nhớ dữ kiện đã xác nhận và tra đúng trạng thái đơn.",
    ),
    "ai_identity_data_deletion": (
        "hoi_ai_va_xoa_du_lieu",
        "Khách hỏi agent có phải AI không và yêu cầu xóa dữ liệu cá nhân. Agent cần trả lời trung thực, xác nhận yêu cầu và xử lý đúng quy trình xóa dữ liệu.",
    ),
    "multi_product_cod_budget": (
        "nhieu_san_pham_cod_vuot_ngan_sach",
        "Khách cân nhắc nhiều sản phẩm, có ngân sách giới hạn và hỏi thanh toán COD. Agent cần tính đúng tổng qua công cụ, không tạo đơn vượt giới hạn COD hoặc ngân sách đã nêu.",
    ),
    "product_exchange_refund_difference": (
        "doi_san_pham_hoan_chenh_lech",
        "Khách muốn đổi sang sản phẩm khác và hỏi cách xử lý khoản chênh lệch. Agent cần tra đúng đơn và chính sách đổi hàng, không tự hứa hoàn tiền hoặc thu thêm.",
    ),
    "source_gap_product_exchange": (
        "doi_san_pham_hoan_chenh_lech",
        "Khách muốn đổi sang sản phẩm khác và hỏi cách xử lý khoản chênh lệch. Agent cần tra đúng đơn và chính sách đổi hàng, không tự hứa hoàn tiền hoặc thu thêm.",
    ),
    "callback_holiday": (
        "hen_goi_lai_ngay_nghi",
        "Khách yêu cầu gọi lại lúc 09:00 ngày 26/10/2026, là ngày nghỉ. Agent cần đặt lịch theo ngày làm việc được hệ thống điều chỉnh và thông báo đúng lịch mới.",
    ),
    "competitor_price_request": (
        "so_sanh_gia_doi_thu",
        "Khách đề nghị so giá hoặc giảm theo đối thủ. Agent không bình luận, xác nhận hay tự điều chỉnh giá theo giá đối thủ; chỉ cung cấp giá và ưu đãi của shop.",
    ),
    "inventory_runs_out_at_close": (
        "het_hang_khi_khach_chot",
        "Tồn kho thay đổi đúng lúc khách muốn chốt. Agent cần kiểm tra tồn kho theo ngày, không hứa giữ hàng hoặc giao hàng khi chưa có căn cứ.",
    ),
}


SLOT_LABELS = {
    "product_advised": "sản phẩm đã trao đổi",
    "price_quoted_vnd": "giá đã báo",
    "room_area_m2": "diện tích phòng",
    "budget_vnd": "ngân sách",
    "blocker": "lý do đang cân nhắc",
    "order_id": "mã đơn hàng",
    "size": "size",
    "color": "màu sắc",
    "payment": "hình thức thanh toán",
    "address_confirmed": "địa chỉ giao hàng",
    "competitor_price_vnd": "giá tham khảo từ nơi khác",
}

SUMMARY_VERSION = "scenario_metadata_v1"
SUMMARY_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{SUMMARY_VERSION}.txt"


def scenario_summary_path(raw_dir: Path, scenario_id: str) -> Path:
    return raw_dir / f"{scenario_id}_metadata.json"


def scenario_summary_payload(
    brief: dict[str, Any],
    raw_by_call: dict[int, dict[str, Any]],
    persona: dict[str, Any],
) -> dict[str, Any]:
    """Build a PII-minimized summary input from persona, hard case and clean turns."""
    tags = brief.get("hard_case_tags", [])
    unknown = sorted(set(tags) - HARD_CASE_PRESENTATION.keys())
    if unknown:
        raise ValueError(f"Missing hard-case descriptions: {', '.join(unknown)}")

    customer_refs: dict[str, str] = {}
    calls = []
    seen: set[str] = set()
    channels_by_customer: dict[str, set[str]] = {}
    ordered_calls = sorted(brief.get("calls", []), key=lambda item: int(item.get("call_index", 0)))
    for spec in ordered_calls:
        call_index = int(spec["call_index"])
        customer_id = str(spec.get("customer_id", brief.get("customer_id", "unknown")))
        customer_ref = customer_refs.setdefault(customer_id, f"customer_{len(customer_refs) + 1}")
        channel = str(spec.get("channel", brief.get("channel", "hotline")))
        channels_by_customer.setdefault(customer_ref, set()).add(channel)
        raw = raw_by_call.get(call_index, {})
        turns = raw.get("customer_turns", [])
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"{brief.get('brief_id')} call_{call_index}: customer_turns are missing")
        calls.append({
            "call_index": call_index,
            "customer_ref": customer_ref,
            "channel": channel,
            "is_returning_customer": customer_ref in seen or bool(spec.get("seed_history")) or bool(spec.get("must_carry_over")),
            "clean_customer_turns": turns,
        })
        seen.add(customer_ref)

    for item in calls:
        item["is_multichannel_customer"] = len(channels_by_customer[item["customer_ref"]]) > 1 or (
            "three_channel_price_conflict" in tags
        )

    return {
        "persona": {
            "persona_id": persona.get("persona_id", brief.get("persona_id")),
            "description": persona.get("description", ""),
            "style": persona.get("style", ""),
        },
        "hard_cases": [
            {"tag": tag, "context": HARD_CASE_PRESENTATION[tag][1]}
            for tag in tags
        ],
        "calls": calls,
        "has_returning_customer": any(item["is_returning_customer"] for item in calls),
        "has_multichannel_customer": any(item["is_multichannel_customer"] for item in calls),
    }


def scenario_summary_digests(payload: dict[str, Any]) -> tuple[str, str, str]:
    prompt = SUMMARY_PROMPT_PATH.read_text(encoding="utf-8").strip()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return (
        prompt,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        hashlib.sha256((SUMMARY_VERSION + "\n" + prompt).encode("utf-8")).hexdigest(),
    )


def generate_scenario_summary(
    brief: dict[str, Any],
    raw_by_call: dict[int, dict[str, Any]],
    persona: dict[str, Any],
    *,
    seed: int,
    dry_run: bool,
    model: str,
    provider: str,
) -> dict[str, Any]:
    payload = scenario_summary_payload(brief, raw_by_call, persona)
    prompt, input_digest, prompt_digest = scenario_summary_digests(payload)
    if dry_run:
        turns = payload["calls"][0]["clean_customer_turns"]
        result = {
            "notes": "DRY_RUN: agent cần xử lý nhu cầu được nêu trong customer turns.",
            "customer_goal": str(turns[0]).strip(),
        }
    else:
        result = None
        last_error = "invalid summary output"
        request = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for attempt in range(3):
            text = complete(prompt, request, seed=seed + attempt, temperature=0.0, dry_run=False)
            try:
                parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
                if not isinstance(parsed, dict):
                    raise ValueError("summary output must be a JSON object")
                notes = parsed.get("notes")
                customer_goal = parsed.get("customer_goal")
                if not isinstance(notes, str) or not notes.strip():
                    raise ValueError("notes must be a non-empty string")
                if not isinstance(customer_goal, str) or not customer_goal.strip():
                    raise ValueError("customer_goal must be a non-empty string")
                result = {"notes": notes.strip(), "customer_goal": customer_goal.strip()}
                break
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
        if result is None:
            raise ValueError(f"scenario metadata output invalid after 3 attempts: {last_error}")

    notes = result["notes"]
    if payload["has_returning_customer"]:
        notes += " Với khách quay lại, agent phải chuẩn bị Call Brief trước khi phản hồi và không hỏi lại dữ kiện đã có."
    if payload["has_multichannel_customer"]:
        notes += " Với khách đa kênh, agent phải hợp nhất đúng danh tính và lịch sử giữa các kênh; khi nguồn mâu thuẫn, cần xác minh an toàn thay vì tự chọn hoặc gộp dữ kiện."

    return {
        "scenario_id": brief["brief_id"],
        **result,
        "notes": notes,
        "generation_meta": {
            "version": SUMMARY_VERSION,
            "provider": "dry-run" if dry_run else provider,
            "model": "dry-run" if dry_run else model,
            "seed": seed,
            "dry_run": dry_run,
            "input_digest": input_digest,
            "prompt_digest": prompt_digest,
        },
    }


def scenario_summary_is_reusable(
    artifact: dict[str, Any] | None,
    payload: dict[str, Any],
    *,
    seed: int,
    dry_run: bool,
    model: str,
    provider: str,
) -> bool:
    if not isinstance(artifact, dict):
        return False
    meta = artifact.get("generation_meta", {})
    _, input_digest, prompt_digest = scenario_summary_digests(payload)
    if not isinstance(artifact.get("notes"), str) or not artifact["notes"].strip():
        return False
    if not isinstance(artifact.get("customer_goal"), str) or not artifact["customer_goal"].strip():
        return False
    if (
        meta.get("version") != SUMMARY_VERSION
        or meta.get("input_digest") != input_digest
        or meta.get("prompt_digest") != prompt_digest
        or meta.get("seed") != seed
        or bool(meta.get("dry_run")) != dry_run
    ):
        return False
    return dry_run or (meta.get("provider") == provider and meta.get("model") == model)


def hard_case_label(tags: list[str] | None) -> str | None:
    if not tags:
        return None
    unknown = sorted(set(tags) - HARD_CASE_PRESENTATION.keys())
    if unknown:
        raise ValueError(f"Missing Vietnamese hard_case labels: {', '.join(unknown)}")
    return "_and_".join(HARD_CASE_PRESENTATION[tag][0] for tag in tags)


def story_hint_for_call(story_hints: str, call_index: int, fallback: str = "") -> str:
    """Resolve a matrix story_hints cell into the outline for one call."""
    if not story_hints or not story_hints.strip():
        return fallback.strip()
    parts = [part.strip() for part in re.split(r"\s*\|\|\s*", story_hints) if part.strip()]
    indexed: dict[int, str] = {}
    for part in parts:
        match = re.match(r"(?i)^call\s*(\d+)\s*:\s*(.+)$", part)
        if match:
            indexed[int(match.group(1))] = match.group(2).strip()
    if indexed:
        return indexed.get(call_index, fallback.strip())
    return " ".join(parts) or fallback.strip()


def customer_goal_from_story_hint(story_hint: str) -> str:
    """Create a concise, customer-side goal from the reviewed call outline."""
    goal = re.sub(r"\s+", " ", str(story_hint or "")).strip()
    if not goal:
        return "Tìm hiểu sản phẩm phù hợp với nhu cầu."
    # Remove scene-setting clauses while retaining the customer's actual intent.
    if ";" in goal:
        clauses = [part.strip() for part in goal.split(";") if part.strip()]
        if len(clauses) > 1:
            goal = clauses[-1]
    # A story can contain multiple details and follow-up context. The public
    # goal field states the first call intent; the full story remains in notes.
    goal = re.split(r"(?<=[.!?])\s+", goal, maxsplit=1)[0].strip()
    goal = re.sub(r"^(?:Khách hàng|Khách)\s+", "", goal, flags=re.IGNORECASE)
    goal = re.sub(r"^(?:Đây là[^;]+;\s*)", "", goal, flags=re.IGNORECASE)
    goal = goal[:1].upper() + goal[1:]
    if goal[-1] not in ".!?":
        goal += "."
    return goal


def customer_goal_for_call(brief: dict[str, Any], call: dict[str, Any]) -> str:
    """Use story_hint as the source; preserve stored goals only for legacy calls without it."""
    story_hint = str(call.get("story_hint", "")).strip()
    if story_hint:
        return customer_goal_from_story_hint(story_hint)
    goal = re.sub(
        r"\s*Khách cần được gọi lại sau khi shop kiểm tra\.?\s*$",
        "", str(call.get("customer_goal", "")), flags=re.IGNORECASE,
    ).strip()
    return goal or "Tìm hiểu sản phẩm phù hợp với nhu cầu."


def normalize_brief_customer_goals(brief: dict[str, Any]) -> bool:
    """Persist goals derived from each call's story_hint; return whether changed."""
    changed = False
    for call in brief.get("calls", []):
        goal = customer_goal_for_call(brief, call)
        if call.get("customer_goal") != goal:
            call["customer_goal"] = goal
            changed = True
    return changed


def scenario_notes(brief: dict[str, Any]) -> str:
    tags = brief.get("hard_case_tags", [])
    calls = brief.get("calls", [])
    # The public samples use a short scenario-level note. A concatenation of
    # every call hint repeats the same context and makes the generated record
    # look like a planning prompt. Keep only the first reviewed context here;
    # later-call context is already represented in each call's customer turns.
    context = next((str(call.get("story_hint", "")).strip() for call in calls if call.get("story_hint")), "")
    if tags:
        unknown = sorted(set(tags) - HARD_CASE_PRESENTATION.keys())
        if unknown:
            raise ValueError(f"Missing Vietnamese hard_case notes: {', '.join(unknown)}")
        notes = [context] if context else []
        notes.extend(HARD_CASE_PRESENTATION[tag][1] for tag in tags)
    else:
        notes = [context] if context else ["Khách tìm hiểu sản phẩm theo nhu cầu của mình."]

    reminders: list[str] = []
    calls = brief.get("calls", [])
    for call in calls[1:]:
        carry = [SLOT_LABELS.get(slot, slot) for slot in call.get("must_carry_over", [])]
        do_not_ask = [SLOT_LABELS.get(slot, slot) for slot in call.get("must_not_ask", [])]
        if carry:
            reminders.append("Cuộc sau cần tiếp nối đúng " + ", ".join(carry) + ".")
        if do_not_ask:
            reminders.append("Không hỏi lại " + ", ".join(do_not_ask) + ".")
    return " ".join(notes + reminders)

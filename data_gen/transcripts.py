"""Paired transcript corpus lifecycle; independent of BTC evaluation scenarios."""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import wave
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import DATA_GEN_DIR, BTC_DIR, MODEL, PROVIDER
from .llm_client import complete

ROOT = DATA_GEN_DIR.parent
TRANSCRIPTS = DATA_GEN_DIR / "transcripts"
RAW = DATA_GEN_DIR / "transcripts_raw"
REVIEWS = DATA_GEN_DIR / "reviews"
REPORTS = DATA_GEN_DIR / "reports"


def _json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_digest() -> str:
    digest = hashlib.sha256()
    sources = [BTC_DIR / "catalog/products.json", BTC_DIR / "catalog/crm_seed.json", BTC_DIR / "catalog/promotions.json", BTC_DIR / "catalog/inventory_timeline.json"]
    sources.extend(sorted((BTC_DIR / "policy").glob("*.md")))
    for path in sources:
        if path.is_file():
            digest.update(str(path.relative_to(BTC_DIR)).encode("utf-8")); digest.update(path.read_bytes())
    return digest.hexdigest()


def _revision() -> str | None:
    try:
        result = subprocess.run(["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _attempt(entry: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    with (REPORTS / "transcript_generation_attempts.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _normalize(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower(), flags=re.UNICODE).strip()


def _ascii_fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def _schema_errors(t: dict) -> list[str]:
    schema_path = DATA_GEN_DIR / "schemas/transcript.schema.json"
    schema = _json(schema_path, {})
    allowed = set(schema.get("properties", {}))
    errors = [f"schema_extra_field:{k}" for k in set(t) - allowed]
    errors.extend(f"schema_missing_field:{k}" for k in set(schema.get("required", [])) - set(t))
    for key in ("persistent_customer_facts", "time_sensitive_facts", "ground_truth_facts", "coverage", "provenance", "validation"):
        if key in t and not isinstance(t[key], dict): errors.append(f"schema_type:{key}")
    coverage_fields = set(schema.get("properties", {}).get("coverage", {}).get("required", []))
    if isinstance(t.get("coverage"), dict): errors.extend(f"schema_missing_coverage:{k}" for k in coverage_fields - set(t["coverage"]))
    provenance_fields = set(schema.get("properties", {}).get("provenance", {}).get("required", []))
    if isinstance(t.get("provenance"), dict): errors.extend(f"schema_missing_provenance:{k}" for k in provenance_fields - set(t["provenance"]))
    for i, turn in enumerate(t.get("turns", [])):
        if not isinstance(turn, dict) or set(turn) != {"speaker", "text"}: errors.append(f"schema_turn:{i}")
    return errors


def make_transcript(scenario: dict, call_name: str, call: dict, customer_id: str | None,
                    turns: list[dict], provenance: dict, status="pending_review") -> dict:
    if not customer_id:
        raise ValueError("stable customer_id is required; do not invent a transcript identity")
    facts = call.get("facts_established", {})
    ground_truth = call.get("ground_truth_facts", {})
    persistent_keys = {"room_area_m2", "has_children", "budget_vnd", "preferred_size", "preferred_color", "address_confirmed"}
    persistent = {k: v for k, v in facts.items() if k in persistent_keys}
    temporal = {k: v for k, v in facts.items() if k not in persistent_keys}
    return {
        "transcript_id": f"{scenario['scenario_id']}_{call_name}",
        "customer_id": customer_id,
        "session_id": f"{scenario['scenario_id']}_{call_name}",
        "call_id": f"{scenario['scenario_id']}_{call_name}",
        "channel": call["channel"], "call_date": call.get("call_date", "2026-10-15"),
        "persona": scenario["persona"], "industry": scenario.get("industry", "thoi-trang"),
        "region_accent": scenario.get("region_accent", "unknown"),
        "persistent_customer_facts": persistent,
        "time_sensitive_facts": temporal,
        "ground_truth_facts": ground_truth,
        "prior_history_context": call.get("seed_history", []),
        "coverage": {"persona": scenario["persona"], "industry": scenario.get("industry", "thoi-trang"), "region": scenario.get("region_accent", "unknown"), "skus": sorted({v for k, v in ground_truth.items() if (k == "sku" or k.endswith("_sku")) and isinstance(v, str)})},
        "turns": turns,
        "source_scenario_id": scenario["scenario_id"],
        "review_status": status,
        "provenance": provenance,
    }


def validate_transcript(t: dict, allowed_facts: dict | None = None, *, known_customer_ids: set[str] | None = None, known_skus: set[str] | None = None) -> list[str]:
    errors = []
    required = {"transcript_id", "customer_id", "session_id", "call_id", "channel", "call_date", "persona", "industry", "region_accent", "persistent_customer_facts", "time_sensitive_facts", "ground_truth_facts", "prior_history_context", "coverage", "turns", "review_status", "provenance"}
    errors.extend(f"missing:{k}" for k in sorted(required - set(t)))
    if known_customer_ids is not None and t.get("customer_id") not in known_customer_ids and not str(t.get("customer_id", "")).startswith("NEW:"):
        errors.append("unknown_customer_reference")
    if known_skus is not None:
        for key, value in t.get("ground_truth_facts", {}).items():
            if (key == "sku" or key.endswith("_sku")) and isinstance(value, str) and value not in known_skus:
                errors.append(f"unknown_sku:{value}")
    if t.get("channel") not in {"hotline", "chat_fanpage", "zalo_oa"}: errors.append("invalid_channel")
    try: date.fromisoformat(t.get("call_date", ""))
    except (TypeError, ValueError): errors.append("invalid_call_date")
    turns = t.get("turns")
    if not isinstance(turns, list) or len(turns) < 4: return errors + ["too_few_turns"]
    for i, turn in enumerate(turns):
        if not isinstance(turn, dict) or turn.get("speaker") not in {"customer", "agent"} or not isinstance(turn.get("text"), str) or not turn["text"].strip():
            errors.append(f"invalid_turn:{i}"); continue
        expected = "customer" if i % 2 == 0 else "agent"
        if turn["speaker"] != expected: errors.append(f"turn_order:{i}")
    if len(turns) % 2: errors.append("unpaired_turn")
    if t.get("review_status") not in {"pending_review", "accepted", "rejected"}: errors.append("invalid_review_status")
    joined = json.dumps(t, ensure_ascii=False)
    if re.search(r"\b\d{9,16}\b", joined): errors.append("possible_pii")
    folded = _ascii_fold(joined)
    if re.search(r"(?:\bNB-|\bNQ-|_internal_price_floor_vnd|gia nhap|gia san(?! pham)|nha cung cap)", folded, re.I): errors.append("internal_data_leak")
    # Deterministic facts are the only permitted sources for specific numeric business claims.
    if allowed_facts:
        truth_numbers = {str(v) for k, v in allowed_facts.items() if any(s in k.lower() for s in ("price", "qty", "stock", "days", "months", "warranty")) and v is not None}
        for m in re.findall(r"\b\d[\d.,]{3,}\b", " ".join(x["text"] for x in turns if isinstance(x, dict) and x.get("speaker") == "agent")):
            digits = re.sub(r"\D", "", m)
            if digits and not any(re.sub(r"\D", "", v) == digits for v in truth_numbers): errors.append(f"ungrounded_number:{m}")
    return errors


def _asr_reference_dialogue(t: dict, wav_path: Path) -> dict:
    """Project reviewed transcript and deterministic entities into BTC dialogue/turn shape."""
    from .auto_check import money_values
    truth = t.get("ground_truth_facts", {})
    known_prices = {v for k, v in truth.items() if "price_vnd" in k and isinstance(v, int)}
    turns, entities = [], {}
    for index, turn in enumerate(t["turns"], start=1):
        found = money_values(turn["text"]) & known_prices
        turn_entities = {"price_vnd": next(iter(found))} if len(found) == 1 else {}
        entities.update(turn_entities)
        turns.append({"idx": index, "speaker": "C" if turn["speaker"] == "customer" else "A", "text": turn["text"], "entities": turn_entities})
    return {
        "id": t["transcript_id"], "customer_region": t.get("region_accent"), "customer_gender": None,
        "agent_gender": None, "agent_region": t.get("region_accent"), "scenario_ref": t.get("source_scenario_id"),
        "noisy": bool(t.get("audio_noisy", False)), "note": "",
        "turns": turns, "full_text": " ".join(turn["text"] for turn in t["turns"]),
        "entities": entities, "n_turns": len(turns),
    }


def validate_corpus(directory: Path = TRANSCRIPTS) -> dict:
    """Check ID/reference integrity and flag near-duplicate accepted/pending records."""
    record_paths = sorted(directory.glob("*.json"))
    records = [_json(p, {}) for p in record_paths]
    crm = _json(BTC_DIR / "catalog/crm_seed.json", {"customers": []})
    known_customers = {x.get("customer_id") for x in crm.get("customers", [])}
    products = _json(BTC_DIR / "catalog/products.json", {"products": []}).get("products", [])
    known_skus = {p.get("sku") for p in products} | {v.get("variant_sku") for p in products for v in p.get("variants", [])}
    errors, seen_ids, seen_sessions = [], set(), set()
    fingerprints = []
    for record_path, record in zip(record_paths, records):
        tid = record.get("transcript_id")
        if record_path.stem != tid:
            errors.append(f"transcript_id_filename_mismatch:{tid}")
        if tid in seen_ids: errors.append(f"duplicate_transcript_id:{tid}")
        seen_ids.add(tid)
        sid = record.get("session_id")
        # One transcript is one call/session: identical session IDs are not independent sessions.
        if sid in seen_sessions: errors.append(f"duplicate_session_id:{sid}")
        seen_sessions.add(sid)
        errors.extend(f"{tid}:{e}" for e in validate_transcript(record, known_customer_ids=known_customers, known_skus=known_skus))
        errors.extend(f"{tid}:{e}" for e in _schema_errors(record))
        if not isinstance(record.get("validation"), dict) or record["validation"].get("status") not in {"passed", "failed"}:
            errors.append(f"{tid}:missing_validation_record")
        source_id = record.get("source_scenario_id")
        source = _json(DATA_GEN_DIR / "scenarios" / f"{source_id}.json") if source_id else None
        call_name = record.get("call_id", "").rsplit("_", 1)
        call_name = f"call_{call_name[-1]}" if len(call_name) == 2 else ""
        source_call = source.get("calls", {}).get(call_name) if source else None
        if not source_call:
            errors.append(f"{tid}:missing_source_scenario_call")
        else:
            if record.get("ground_truth_facts") != source_call.get("ground_truth_facts"):
                errors.append(f"{tid}:ground_truth_mismatch")
            scenario_date = date.fromisoformat("2026-10-15")
            expected_date = None
            for name, call in sorted(source.get("calls", {}).items(), key=lambda x: int(x[0].rsplit("_", 1)[-1])):
                scenario_date = date.fromisoformat(call["call_date"]) if call.get("call_date") else scenario_date + timedelta(days=int(call.get("days_later", 0)))
                if name == call_name: expected_date = scenario_date.isoformat()
            if record.get("channel") != source_call.get("channel") or record.get("call_date") != expected_date:
                errors.append(f"{tid}:source_channel_or_date_mismatch")
            sidecar = _json(DATA_GEN_DIR / "scenarios_metadata" / f"{source_id}.json", {})
            brief = _json(DATA_GEN_DIR / "briefs" / f"{source_id}.json", {})
            spec = next((x for x in brief.get("calls", []) if f"call_{x.get('call_index')}" == call_name), {})
            expected_customer = sidecar.get("call_customer_ids", {}).get(call_name, spec.get("customer_id", brief.get("customer_id")))
            if expected_customer and record.get("customer_id") != expected_customer:
                errors.append(f"{tid}:customer_reference_mismatch")
        text = _normalize(" ".join(x.get("text", "") for x in record.get("turns", []) if isinstance(x, dict)))
        if record.get("review_status") != "rejected":
            for old_id, old_text in fingerprints:
                if len(text) > 50 and len(old_text) > 50 and difflib.SequenceMatcher(None, text, old_text).ratio() >= 0.92:
                    errors.append(f"near_duplicate:{old_id}:{tid}")
            fingerprints.append((tid, text))
    return {"records": len(records), "errors": errors, "status": "passed" if not errors else "failed"}


def generate_from_scenarios(scenario_dir: Path, brief_dir: Path, *, dry_run=False, limit=None, seed=7) -> dict:
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    files = sorted(scenario_dir.glob("SC-*.json"))
    if limit: files = files[:limit]
    crm_path = BTC_DIR / "catalog/crm_seed.json"
    crm = {x["customer_id"]: x for x in _json(crm_path, {"customers": []})["customers"]}
    product_catalog = _json(BTC_DIR / "catalog/products.json", {}).get("products", [])
    known_skus = {p.get("sku") for p in product_catalog} | {v.get("variant_sku") for p in product_catalog for v in p.get("variants", [])}
    source_digest, code_digest, revision = _source_digest(), _hash(Path(__file__)), _revision()
    created = reused = failed = 0
    for path in files:
        scenario = _json(path)
        if not scenario: continue
        brief = _json(brief_dir / path.name, {})
        sidecar = _json(scenario_dir.with_name(f"{scenario_dir.name}_metadata") / path.name, {})
        spec_by_index = {f"call_{x['call_index']}": x for x in brief.get("calls", [])}
        previous_date = date.fromisoformat("2026-10-15")
        for call_name, call in sorted(scenario.get("calls", {}).items(), key=lambda x: int(x[0].rsplit("_", 1)[-1])):
            tid = f"{scenario['scenario_id']}_{call_name}"
            out, raw_path = TRANSCRIPTS / f"{tid}.json", RAW / f"{tid}.json"
            if out.exists(): reused += 1; continue
            spec = spec_by_index.get(call_name, {})
            if call.get("call_date"):
                current_date = date.fromisoformat(call["call_date"])
            else:
                current_date = previous_date + timedelta(days=int(call.get("days_later", 0)))
            call["call_date"] = current_date.isoformat()
            previous_date = current_date
            cid = sidecar.get("call_customer_ids", {}).get(call_name, spec.get("customer_id", brief.get("customer_id")))
            if not cid and scenario.get("customer_phone"):
                cid = next((k for k, v in crm.items() if v.get("phone") == scenario["customer_phone"]), None)
            if cid and cid not in crm and not str(cid).startswith("NEW:"):
                _attempt({"transcript_id": tid, "attempted_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "reason": f"unknown customer_id reference: {cid}", "seed": seed})
                failed += 1
                continue
            if not cid:
                _attempt({"transcript_id": tid, "attempted_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "reason": "missing stable customer_id reference", "seed": seed})
                failed += 1
                continue
            customers = call.get("customer_turns", [])
            if not customers: failed += 1; continue
            allowed = call.get("ground_truth_facts", {})
            prompt = {
                "customer_turns": customers,
                "ground_truth_facts": allowed,
                "policy_evidence": allowed.get("policy_evidence", []),
                "prior_customer_history": call.get("seed_history", []),
                "known_customer_facts": call.get("facts_established", {}),
                "instruction": "Create one concise Vietnamese agent reply after each customer turn. Return JSON array of strings only. Never invent product, price, promotion, inventory, shipping date, policy, or history facts; if no deterministic evidence supports a claim, acknowledge and offer to check. Keep replies conversational and the customer turns verbatim.",
            }
            try:
                if dry_run:
                    replies = ["Dạ em đã ghi nhận nhu cầu của mình ạ." for _ in customers]
                    model = "dry-run"
                else:
                    response = complete("Generate paired Vietnamese call-center turns under the strict supplied evidence constraints.", json.dumps(prompt, ensure_ascii=False), seed=seed, temperature=0.2, dry_run=False)
                    replies = json.loads(response)
                    model = MODEL
                if not isinstance(replies, list) or len(replies) != len(customers) or any(not isinstance(x, str) or not x.strip() for x in replies): raise ValueError("agent reply array must match customer turn count")
                turns = []
                for customer_text, agent_text in zip(customers, replies):
                    turns.extend([{"speaker": "customer", "text": customer_text}, {"speaker": "agent", "text": agent_text}])
                meta = {"provider": "dry-run" if dry_run else PROVIDER, "model": model, "seed": seed, "generated_at": datetime.now(timezone.utc).isoformat(), "scenario_sha256": _hash(path), "brief_sha256": _hash(brief_dir / path.name) if (brief_dir / path.name).exists() else None, "source_digest": source_digest, "code_digest": code_digest, "code_revision": revision, "prompt_version": "paired_transcript_v1", "artifact_status": "raw"}
                meta["prompt_digest"] = hashlib.sha256(json.dumps(prompt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
                _write(raw_path, {"turns": turns, "provenance": meta})
                customer_region = crm.get(cid, {}).get("region", "unknown")
                scenario["region_accent"] = customer_region
                sku = next((v for k, v in allowed.items() if k.endswith("_sku") or k == "sku"), None)
                scenario["industry"] = next((p.get("category", "").split("/")[0] for p in product_catalog if p.get("sku") == sku or any(v.get("variant_sku") == sku for v in p.get("variants", []))), "thoi-trang")
                meta["artifact_status"] = "pending_review"
                transcript = make_transcript(scenario, call_name, call, cid, turns, meta)
                errors = validate_transcript(transcript, allowed, known_customer_ids=set(crm), known_skus=known_skus)
                transcript["validation"] = {"status": "failed" if errors else "passed", "errors": errors, "btc_validator": "unavailable_unverified"}
                if errors: transcript["review_status"] = "rejected"
                _write(out, transcript); created += 1
                _attempt({"transcript_id": tid, "attempted_at": meta["generated_at"], "status": "rejected" if errors else "pending_review", "reason": errors, "seed": seed, "model": model})
            except Exception as exc:
                _write(raw_path, {"generation_status": "failed", "error": str(exc), "attempted_at": datetime.now(timezone.utc).isoformat(), "seed": seed})
                _attempt({"transcript_id": tid, "attempted_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "reason": str(exc), "seed": seed})
                failed += 1
    refresh_review_queue()
    return {"created": created, "reused": reused, "failed": failed, "transcripts_dir": str(TRANSCRIPTS)}


def refresh_review_queue() -> Path:
    REVIEWS.mkdir(parents=True, exist_ok=True)
    queue = []
    for p in sorted(TRANSCRIPTS.glob("*.json")):
        t = _json(p, {})
        if t.get("review_status") == "pending_review":
            queue.append({"transcript_id": t.get("transcript_id"), "path": str(p), "status": "pending_review", "reviewer": None, "reviewed_at": None, "notes": ""})
    path = REVIEWS / "queue.json"
    _write(path, queue)
    return path


def review(transcript_id: str, decision: str, reviewer: str, notes: str="") -> None:
    if decision not in {"accepted", "rejected"}: raise ValueError("decision must be accepted or rejected")
    path = TRANSCRIPTS / f"{transcript_id}.json"
    t = _json(path)
    if not t: raise FileNotFoundError(path)
    if t.get("review_status") != "pending_review": raise ValueError("only pending samples can be reviewed")
    if t.get("validation", {}).get("status") != "passed" and decision == "accepted": raise ValueError("cannot accept a failed validation")
    if decision == "accepted":
        text = _normalize(" ".join(x.get("text", "") for x in t.get("turns", []) if isinstance(x, dict)))
        for other_path in TRANSCRIPTS.glob("*.json"):
            if other_path == path: continue
            other = _json(other_path, {})
            if other.get("review_status") == "rejected": continue
            old = _normalize(" ".join(x.get("text", "") for x in other.get("turns", []) if isinstance(x, dict)))
            if len(text) > 50 and len(old) > 50 and difflib.SequenceMatcher(None, text, old).ratio() >= 0.92:
                raise ValueError(f"near duplicate with {other.get('transcript_id')}; reject or regenerate this sample")
    t["review_status"] = decision
    t.setdefault("provenance", {})["artifact_status"] = decision
    t["review"] = {"reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat(), "notes": notes}
    _write(path, t); refresh_review_queue()


def coverage() -> dict:
    config = _json(DATA_GEN_DIR / "dataset_config.json", {})["milestones"]["M1"]
    items = [_json(p, {}) for p in TRANSCRIPTS.glob("*.json")]
    counts = {s: sum(x.get("review_status") == s for x in items) for s in ("pending_review", "accepted", "rejected")}
    corpus_validation = validate_corpus()
    invalid_ids = set()
    all_ids = {x.get("transcript_id") for x in items}
    for error in corpus_validation["errors"]:
        if error.startswith("near_duplicate:"):
            invalid_ids.update(error.split(":")[1:3])
        else:
            sample_id = error.split(":", 1)[0]
            if sample_id in all_ids: invalid_ids.add(sample_id)
    accepted = [x for x in items if x.get("review_status") == "accepted" and x.get("validation", {}).get("status") == "passed" and x.get("transcript_id") not in invalid_ids]
    sessions, channels = {}, {}
    for t in accepted:
        sessions.setdefault(t.get("customer_id"), set()).add(t.get("session_id"))
        channels.setdefault(t.get("customer_id"), set()).add(t.get("channel"))
    multi = sum(len(v) >= 2 for v in sessions.values())
    cross = sum("hotline" in v and bool(v & {"chat_fanpage", "zalo_oa"}) for v in channels.values())
    personas = {x.get("coverage", {}).get("persona") for x in accepted}
    industries = {x.get("coverage", {}).get("industry") for x in accepted}
    regions = {x.get("coverage", {}).get("region") for x in accepted}
    skus = {sku for x in accepted for sku in x.get("coverage", {}).get("skus", [])}
    audio_items, audio_seconds = set(), 0.0
    audio_dir = DATA_GEN_DIR / "audio"
    accepted_ids = {x.get("transcript_id") for x in accepted}
    for meta_path in audio_dir.glob("*.json") if audio_dir.exists() else []:
        if meta_path.name == "team_asr_ground_truth.json": continue
        meta = _json(meta_path, {})
        wav_path = audio_dir / meta_path.name.replace(".json", ".wav")
        if meta.get("transcript_id") in accepted_ids and meta.get("status") == "verified" and wav_path.is_file() and _hash(wav_path) == meta.get("audio_sha256"):
            audio_items.add(meta.get("transcript_id")); audio_seconds += float(meta.get("duration_seconds", 0))
    matrix_path = REPORTS / "coverage_matrix.csv"
    if matrix_path.exists():
        with matrix_path.open(encoding="utf-8-sig", newline="") as f: matrix_rows = list(csv.DictReader(f))
    else: matrix_rows = []
    matrix_rows = [r for r in matrix_rows if r.get("level", "M1") == "M1" and r.get("status", "todo") != "dropped"]
    planned_calls = sum(int(r.get("num_calls", 0) or 0) for r in matrix_rows)
    planned_sessions, planned_channels = {}, {}
    for row in matrix_rows:
        cid = row.get("customer_id")
        if cid in ("", "TODO", None): continue
        n = int(row.get("num_calls", 0) or 0)
        planned_sessions.setdefault(cid, set()).update(f"{row.get('slot_id')}_call_{i}" for i in range(n))
        planned_channels.setdefault(cid, set()).update(row.get("channel_pattern", "").split("-"))
    planned_multi = sum(len(value) >= 2 for value in planned_sessions.values())
    planned_multichannel = sum("hotline" in value and bool(value & {"chat_fanpage", "zalo_oa"}) for value in planned_channels.values())
    report = {"planned_slots": len(matrix_rows), "planned_calls": planned_calls, "planned_calls_target": _json(DATA_GEN_DIR / "dataset_config.json", {}).get("coverage_matrix", {}).get("planned_calls_target"), "planned_multi_session_customers": planned_multi, "planned_multichannel_customers": planned_multichannel, "briefed_scenarios": len(list((DATA_GEN_DIR / "briefs").glob("SC-*.json"))), "generated": len(items), "generation_failures": sum(_json(p, {}).get("generation_status") == "failed" for p in RAW.glob("*.json")) if RAW.exists() else 0, "validated": sum(x.get("validation", {}).get("status") == "passed" for x in items), **counts, "accepted_transcripts": len(accepted), "multi_session_customers": multi, "cross_channel_customers": cross, "personas": sorted(personas - {None}), "industries": sorted(industries - {None}), "regions": sorted(regions - {None}), "catalog_skus_covered": len(skus), "audio_conversations": len(audio_items), "verified_audio_seconds": audio_seconds, "audio_files": len(audio_items), "btc_validator_compatibility": "unverified_missing_validator", "local_corpus_validation": corpus_validation}
    target = config.get("transcripts_target", config["transcripts_min"])
    report["official_transcript_min"] = config["transcripts_min"]
    report["internal_transcript_target"] = target
    report["transcript_min_met"] = len(accepted) >= config["transcripts_min"]
    report["internal_target_met"] = len(accepted) >= target
    report["multi_session_min_met"] = multi >= config["multi_session_customers_min"]
    report["cross_channel_min_met"] = cross >= config["multichannel_customers_min"]
    report["official_audio_conversation_min"] = config["audio"]["transcripts_min"]
    report["official_audio_seconds_min"] = int(config["audio"]["hours_min"] * 3600)
    report["audio_min_met"] = len(audio_items) >= report["official_audio_conversation_min"] and audio_seconds >= report["official_audio_seconds_min"]
    report["asr_audio_files_min"] = config["audio"]["group_generated_asr_evaluation_files_min"]
    report["asr_audio_file_min_met"] = len(audio_items) >= report["asr_audio_files_min"]
    report["required_personas_met"] = set(config.get("required_personas", [])).issubset(personas)
    report["industry_min_met"] = len(industries) >= config["industry_count"]
    report["regional_accent_min_met"] = set(config["regions"]).issubset(regions)
    report["catalog_sku_min_met"] = len(skus) >= config["catalog_sku_min"]
    return report


def audio_from_accepted(command: str) -> dict:
    """Run local per-speaker TTS: command placeholders {text_file},{wav_file},{speaker}."""
    if not command: raise ValueError("pass --tts-command explicitly to generate audio")
    import shlex
    audio_dir = DATA_GEN_DIR / "audio"; audio_dir.mkdir(exist_ok=True)
    generated = 0
    btc_ground_truth = _json(BTC_DIR / "asr/ground_truth.json", {})
    ground_truth = {"description": "Team-generated ASR ground truth; separate from immutable BTC assets.", "hypotheses_format": btc_ground_truth.get("hypotheses_format"), "normalization_rule": btc_ground_truth.get("normalization_rule"), "reference_date": "2026-10-15", "dialogues": []}
    for path in sorted(TRANSCRIPTS.glob("*.json")):
        t = _json(path, {})
        if t.get("review_status") != "accepted": continue
        wav_path = audio_dir / f"{t['transcript_id']}.wav"
        metadata_path = audio_dir / f"{t['transcript_id']}.json"
        current_meta = _json(metadata_path, {})
        current_hash = _hash(path)
        if wav_path.exists() and current_meta.get("source_sha256") == current_hash and current_meta.get("audio_sha256") == _hash(wav_path): continue
        if wav_path.exists() or metadata_path.exists():
            archive = audio_dir / "archive"; archive.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            for stale in (wav_path, metadata_path):
                if stale.exists(): shutil.move(str(stale), str(archive / f"{stale.stem}.{stamp}{stale.suffix}"))
        with tempfile.TemporaryDirectory(prefix="tts-", dir=audio_dir) as scratch:
            params = None
            with wave.open(str(wav_path), "wb") as output_wav:
                for index, turn in enumerate(t["turns"], start=1):
                    text_file = Path(scratch) / f"turn-{index}.txt"
                    turn_wav = Path(scratch) / f"turn-{index}.wav"
                    text_file.write_text(turn["text"], encoding="utf-8")
                    args = [x.format(text_file=str(text_file), wav_file=str(turn_wav), speaker=turn["speaker"]) for x in shlex.split(command)]
                    subprocess.run(args, check=True)
                    with wave.open(str(turn_wav), "rb") as source:
                        current_params = source.getparams()
                        if params is None:
                            params = current_params
                            output_wav.setparams(params)
                        elif (current_params.nchannels, current_params.sampwidth, current_params.framerate, current_params.comptype) != (params.nchannels, params.sampwidth, params.framerate, params.comptype):
                            raise ValueError("TTS turn WAVs must share channels, sample width, sample rate and compression")
                        output_wav.writeframes(source.readframes(source.getnframes()))
        with wave.open(str(wav_path), "rb") as wf: duration = wf.getnframes() / wf.getframerate()
        meta = {"transcript_id": t["transcript_id"], "source_sha256": current_hash, "audio_sha256": _hash(wav_path), "duration_seconds": duration, "speaker_turns": [{"speaker": x["speaker"], "turn_index": i} for i, x in enumerate(t["turns"], start=1)], "source": "tts", "created_at": datetime.now(timezone.utc).isoformat(), "status": "verified"}
        _write(metadata_path, meta); generated += 1
    for path in sorted(TRANSCRIPTS.glob("*.json")):
        t = _json(path, {})
        wav_path = audio_dir / f"{t.get('transcript_id')}.wav"
        meta = _json(audio_dir / f"{t.get('transcript_id')}.json", {})
        if t.get("review_status") == "accepted" and meta.get("status") == "verified" and wav_path.is_file() and _hash(wav_path) == meta.get("audio_sha256"):
            ground_truth["dialogues"].append(_asr_reference_dialogue(t, wav_path))
    gt_path = audio_dir / "team_asr_ground_truth.json"
    if ground_truth["dialogues"]: _write(gt_path, ground_truth)
    return {"generated": generated, "audio_dir": str(audio_dir), "ground_truth": str(gt_path) if ground_truth["dialogues"] else None}


def build_manifest() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    manifest_path = REPORTS / "transcript_manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for p in sorted(TRANSCRIPTS.glob("*.json")):
            item = _json(p, {})
            f.write(json.dumps({"transcript_id": item.get("transcript_id"), "customer_id": item.get("customer_id"), "session_id": item.get("session_id"), "call_id": item.get("call_id"), "review_status": item.get("review_status"), "transcript_sha256": _hash(p), "provenance": item.get("provenance", {})}, ensure_ascii=False) + "\n")
    report = coverage()
    report["transcript_manifest"] = str(manifest_path)
    _write(REPORTS / "transcript_coverage.json", report)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate"); g.add_argument("--scenarios", type=Path, default=DATA_GEN_DIR / "scenarios"); g.add_argument("--briefs", type=Path, default=DATA_GEN_DIR / "briefs"); g.add_argument("--dry-run", action="store_true"); g.add_argument("--limit", type=int); g.add_argument("--seed", type=int, default=7)
    sub.add_parser("coverage")
    v = sub.add_parser("validate"); v.add_argument("--transcripts", type=Path, default=TRANSCRIPTS)
    sub.add_parser("manifest")
    r = sub.add_parser("review"); r.add_argument("transcript_id"); r.add_argument("--decision", choices=("accepted", "rejected"), required=True); r.add_argument("--reviewer", required=True); r.add_argument("--notes", default="")
    a = sub.add_parser("audio"); a.add_argument("--tts-command", default=os.getenv("DATASET_TTS_COMMAND", ""))
    args = ap.parse_args()
    if args.cmd == "generate": print(json.dumps(generate_from_scenarios(args.scenarios, args.briefs, dry_run=args.dry_run, limit=args.limit, seed=args.seed), ensure_ascii=False))
    elif args.cmd == "coverage": print(json.dumps(coverage(), ensure_ascii=False, indent=2))
    elif args.cmd == "validate":
        result = validate_corpus(args.transcripts); print(json.dumps(result, ensure_ascii=False, indent=2)); sys.exit(0 if result["status"] == "passed" else 1)
    elif args.cmd == "manifest": print(json.dumps(build_manifest(), ensure_ascii=False, indent=2))
    elif args.cmd == "review": review(args.transcript_id, args.decision, args.reviewer, args.notes); print("review saved")
    else: print(json.dumps(audio_from_accepted(args.tts_command), ensure_ascii=False))


if __name__ == "__main__": main()

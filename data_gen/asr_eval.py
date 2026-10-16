"""Run local faster-whisper and score available BTC/team audio; never downloads models."""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from .config import BTC_DIR, DATA_GEN_DIR, REPORTS_DIR

_NUMBER_WORDS = {
    "không": 0, "khong": 0, "một": 1, "mot": 1, "mốt": 1, "mot": 1,
    "hai": 2, "ba": 3, "bốn": 4, "bon": 4, "tư": 4, "tu": 4,
    "năm": 5, "nam": 5, "lăm": 5, "lam": 5, "sáu": 6, "sau": 6,
    "bảy": 7, "bay": 7, "tám": 8, "tam": 8, "chín": 9, "chin": 9,
}
_SCALES = {"nghìn": 1_000, "nghin": 1_000, "ngàn": 1_000, "ngan": 1_000, "triệu": 1_000_000, "trieu": 1_000_000, "tỷ": 1_000_000_000, "ty": 1_000_000_000}


def _number_candidates(tokens: list[str]) -> set[int]:
    if not tokens: return set()
    if all(re.fullmatch(r"\d+", t) for t in tokens):
        return {int("".join(tokens))}
    total = section = current = 0
    scale_seen = False
    last_scale = 0
    after_hundred: list[int] = []
    for token in tokens:
        if token in _NUMBER_WORDS:
            value = _NUMBER_WORDS[token]
            current += value
            if last_scale == 100: after_hundred.append(value)
        elif token == "mười" or token == "muoi":
            current = (current or 1) * 10
            last_scale = 10
        elif token == "mươi" or token == "muoi":
            current = (current or 1) * 10
            last_scale = 10
        elif token == "trăm" or token == "tram":
            current = (current or 1) * 100
            section += current
            current = 0
            last_scale = 100
            after_hundred = []
        elif token in _SCALES:
            scale = _SCALES[token]
            value = section + current
            if last_scale == 100 and len(after_hundred) >= 2:
                value = section + int("".join(map(str, after_hundred)))
            if value == 0: value = 1
            total += value * scale
            section = current = 0
            scale_seen = True
            last_scale = scale
            after_hundred = []
        elif token in {"rưỡi", "ruoi"} and last_scale:
            total += last_scale // 2
            scale_seen = True
            last_scale = 0
        else:
            return set()
    tail = section + current
    base = total + tail
    candidates = {base}
    if scale_seen and tail:
        candidates.update(total + tail * factor for factor in (1_000, 1_000_000))
    if last_scale == 100 and len(after_hundred) >= 2:
        concatenated = int("".join(map(str, after_hundred)))
        candidates.add(total + section + concatenated)
        candidates.update(total + section + concatenated * factor for factor in (1_000, 1_000_000))
    if tokens[-1] in {"rưỡi", "ruoi"}:
        candidates.add(total + (last_scale // 2 if last_scale else 0))
    return {x for x in candidates if x >= 0}


def normalize_for_entities(text: str, entities: dict) -> str:
    tokens = [re.sub(r"(?:đồng|dong|vnd|đ)$", "", token) for token in normalize(text).split()]
    expected = {v: k for k, v in entities.items() if isinstance(v, int) and not isinstance(v, bool)}
    output, i = [], 0
    while i < len(tokens):
        best = None
        for end in range(i + 1, min(len(tokens), i + 14) + 1):
            matches = _number_candidates(tokens[i:end]) & set(expected)
            if matches: best = (end, matches)
        if best:
            end, matches = best
            value = sorted(matches)[0]
            output.append(f"entity_{expected[value]}")
            i = end
        else:
            output.append(tokens[i]); i += 1
    return " ".join(output)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return " ".join(text.split())


def _distance(a: list[str], b: list[str]) -> int:
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def wer(reference: str, hypothesis: str, entities: dict | None = None) -> float:
    ref, hyp = normalize_for_entities(reference, entities or {}).split(), normalize_for_entities(hypothesis, entities or {}).split()
    return _distance(ref, hyp) / max(1, len(ref))


def cer(reference: str, hypothesis: str, entities: dict | None = None) -> float:
    ref, hyp = normalize_for_entities(reference, entities or {}).replace(" ", ""), normalize_for_entities(hypothesis, entities or {}).replace(" ", "")
    return _distance(list(ref), list(hyp)) / max(1, len(ref))


def entity_scores(expected: dict, hypothesis: str) -> dict:
    """Score supported exact entities; do not infer missing references from ASR output."""
    from .auto_check import money_values
    numbers = money_values(hypothesis)
    digits = set(re.findall(r"(?<!\d)\d{9,15}(?!\d)", hypothesis))
    matches = {}
    for key, value in expected.items():
        if key == "price_vnd" or key.endswith("_price_vnd"):
            matches[key] = isinstance(value, int) and (value in numbers or f"entity_{key}" in normalize_for_entities(hypothesis, {key: value}).split())
        elif "phone" in key.lower():
            expected_digits = re.sub(r"\D", "", str(value))
            matches[key] = bool(expected_digits and expected_digits in digits)
        else:
            matches[key] = normalize(str(value)) in normalize(hypothesis)
    return matches


def extract_entities(hypothesis: str) -> dict:
    """Extract only values present in the ASR hypothesis; never copy ground truth."""
    from .auto_check import money_values
    amounts = money_values(hypothesis)
    entities = {}
    if len(amounts) == 1: entities["price_vnd"] = next(iter(amounts))
    phones = re.findall(r"(?<!\d)\+?\d[\d\s()-]{7,}\d(?!\d)", hypothesis)
    if len(phones) == 1: entities["phone"] = re.sub(r"\D", "", phones[0])
    return entities


def _audio_path(directory: Path, dialogue: dict) -> Path | None:
    name = dialogue.get("audio_file")
    candidates = [directory / name] if name else [directory / f"{dialogue['id']}{ext}" for ext in (".wav", ".mp3", ".m4a", ".flac")]
    return next((path for path in candidates if path and path.is_file()), None)


def score_set(gt_path: Path, audio_dir: Path, model) -> dict:
    ground = json.loads(gt_path.read_text(encoding="utf-8"))
    rows, missing = [], []
    for dialogue in ground.get("dialogues", []):
        audio = _audio_path(audio_dir, dialogue)
        if audio is None:
            missing.append(dialogue["id"]); continue
        segments, _ = model.transcribe(str(audio), language="vi", vad_filter=True)
        hypotheses = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]
        text = " ".join(x["text"] for x in hypotheses)
        reference = dialogue.get("full_text") or " ".join(t.get("text", "") for t in dialogue.get("turns", []))
        entity_result = entity_scores(dialogue.get("entities", {}), text)
        rows.append({"id": dialogue["id"], "audio_file": str(audio), "wer": wer(reference, text, dialogue.get("entities", {})), "cer": cer(reference, text, dialogue.get("entities", {})), "entity_accuracy": sum(entity_result.values()) / max(1, len(entity_result)), "entity_matches": entity_result, "hypothesis": {"text": text, "entities": extract_entities(text)}})
    n = len(rows)
    return {"ground_truth": str(gt_path), "audio_dir": str(audio_dir), "n_audio": n, "missing_audio_ids": missing, "mean_wer": sum(x["wer"] for x in rows) / max(1, n), "mean_cer": sum(x["cer"] for x in rows) / max(1, n), "mean_entity_accuracy": sum(x["entity_accuracy"] for x in rows) / max(1, n), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", type=Path, help="Local faster-whisper model directory; no network model lookup is performed")
    ap.add_argument("--btc-audio-dir", type=Path, default=BTC_DIR / "asr")
    ap.add_argument("--team-audio-dir", type=Path, default=DATA_GEN_DIR / "audio")
    ap.add_argument("--btc-ground-truth", type=Path, default=BTC_DIR / "asr/ground_truth.json")
    ap.add_argument("--team-ground-truth", type=Path, default=DATA_GEN_DIR / "audio/team_asr_ground_truth.json")
    args = ap.parse_args()
    if not args.model_path or not args.model_path.is_dir():
        ap.error("provide --model-path for an already installed local model directory (network downloads disabled)")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit("faster-whisper is not installed; install it locally before running ASR evaluation") from exc
    model = WhisperModel(str(args.model_path), device="cpu", compute_type="int8")
    result = {"model_path": str(args.model_path), "runtime": "faster-whisper local", "btc": score_set(args.btc_ground_truth, args.btc_audio_dir, model)}
    if args.team_ground_truth.exists(): result["team"] = score_set(args.team_ground_truth, args.team_audio_dir, model)
    else: result["team"] = {"n_audio": 0, "missing_audio_ids": [], "status": "team ground truth not generated"}
    result["team_asr_minimum_met"] = result["team"]["n_audio"] >= 20
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "asr_metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPORTS_DIR / "asr_hypotheses.json").write_text(json.dumps({row["id"]: row["hypothesis"] for key in ("btc", "team") for row in result.get(key, {}).get("rows", [])}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["btc"]["n_audio"] == 0 and result["team"]["n_audio"] == 0: sys.exit(2)


if __name__ == "__main__": main()

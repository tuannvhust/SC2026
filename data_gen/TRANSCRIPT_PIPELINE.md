# Paired transcript corpus

## Separate deliverables

`scenarios/` remains BTC-shaped **customer-input evaluation data**. Its calls contain customer turns, ground truth and success criteria; scenario calls never count as transcript deliverables. `transcripts/` is the distinct paired-turn corpus, with `customer` and `agent` turns and schema in `schemas/transcript.schema.json`. Generated transcripts enter `pending_review`; only a human review can set `accepted`. Failed validation cannot be accepted.

The BTC package in this checkout has no paired-transcript schema or validator. BTC transcript-validator compatibility therefore remains **unverified**. Do not present local checks as BTC validation.

## Configured M1 targets

The official minimums and internal buffer live in `dataset_config.json`: 120 accepted paired transcripts (internal target 140), 40 accepted transcripts with actual audio files and at least 3,600 verified audio seconds, 30 customers with at least two distinct `session_id` values, 10 customers with both hotline and chat, one industry, two regions, three required personas, and at least 30 catalog SKUs. BTC clarification `data/DIEU-CHINH-DE.md` additionally requires ASR WER/CER/Entity Accuracy on BTC-provided audio **plus at least 20 team audio files**. BTC assets under `data/asr/` are read-only; team audio and its separate ground truth live under `data_gen/audio/`.

| BTC requirement | Source | Configuration / implementation | Current evidence |
|---|---|---|---|
| ≥120 transcripts; internal safety target 140 | Official brief C.1; team target requested for this work | `milestones.M1.transcripts_min` / `transcripts_target`; accepted paired records only | 0 accepted; 81 prior scenario calls are not transcripts |
| ≥40 audio conversations / ≥1 hour | Official brief C.1 | M1 `audio`; count hash-verified WAVs linked to accepted transcript IDs and sum actual WAV duration | 0 / 0 seconds |
| ≥30 customers with ≥2 calls | Official brief C.1 | Distinct accepted `session_id`s grouped by `customer_id` | 0; plan has 33 but planned != accepted |
| ≥10 phone + chat customers | Official brief C.1; mentor clarification Q&A #1 | Actual accepted channel records grouped by stable customer ID | 0; plan has 10 |
| One industry, two regions; three specific personas; ≥30 SKUs | Official brief C.1 | Configured values and actual accepted `coverage` metadata | 0 coverage; plan is 1 industry / 3 regions / 12 personas |
| ASR locally; WER/CER and exact entity accuracy on ≥20 files, plus BTC audio | Official brief C.1; `DIEU-CHINH-DE.md` §2 | `group_generated_asr_evaluation_files_min=20`; team GT is separate and uses BTC dialogue/turn layout | 0 team audio; BTC directory currently has GT JSON only in this checkout; no team ASR metric run |
| Human acceptance; no fake accepted samples | Explicit acceptance lifecycle added for this corpus | `pending_review` queue and reviewer identity/time/notes; acceptance rejects validation errors and near-duplicates | No queue entries until generation; no accepted records |
| Official transcript validator compatibility | No transcript schema/validator in available BTC package | Kept separate local schema/checks; validator status field | Unverified; no BTC validator present |

The current plan matrix has 99 M1 slots / 161 planned calls, with planned coverage of 33 multi-session customers and 10 multichannel customers. Only 49 scenarios / 81 calls are currently briefed and generated. This leaves planned work to complete before the corpus can reach its target; counts above are intentionally separate.

## Generation, review, audio, and packaging

Run from the repository root in PowerShell:

```powershell
# Fill remaining reviewed scenario briefs without overwriting existing briefs.
python -m data_gen.coverage_matrix.make_coverage_matrix stubs --matrix data_gen/reports/coverage_matrix.csv --out data_gen/briefs
python -m data_gen.lint_briefs data_gen/briefs

# Resume/generate scenario customer inputs (LLM use; run only after briefs are reviewed).
python -m data_gen.run_batch --briefs data_gen/briefs --out data_gen/scenarios --level M1 --seed 7

# Generate two paired transcripts from existing scenarios. This calls the configured LLM.
python -m data_gen.transcripts generate --scenarios data_gen/scenarios --briefs data_gen/briefs --limit 2

# Local-only lifecycle smoke sample; never accept this as quality data.
python -m data_gen.transcripts generate --scenarios data_gen/scenarios --briefs data_gen/briefs --limit 1 --dry-run

# Validate and inspect actual artifact counts / review queue.
python -m data_gen.transcripts validate
python -m data_gen.transcripts coverage
Get-Content data_gen/reviews/queue.json

# Explicit human decision; repeat for each transcript reviewed.
python -m data_gen.transcripts review SC-002_call_1 --decision accepted --reviewer reviewer-name --notes "Reviewed paired turns, consistency, facts, privacy and language"

# Audio generation requires an explicitly configured local command, accepting all three placeholders.
$env:DATASET_TTS_COMMAND = 'my-local-tts --input {text_file} --output {wav_file} --speaker {speaker}'
python -m data_gen.transcripts audio

# Rebuild artifact-derived manifest and coverage report.
python -m data_gen.transcripts manifest
```

The audio stage consumes accepted transcripts only, verifies WAV duration and hashes, and writes `audio/team_asr_ground_truth.json` in the BTC `asr/ground_truth.json` dialogue/turn shape. It creates no ASR predictions. Ground truth is never an ASR hypothesis. The external TTS engine and voice are team configuration; nothing is called unless `audio` is explicitly invoked with a command.

For ASR, install `faster-whisper` and provide a local model directory (the evaluator will not download one):

```powershell
python -m data_gen.asr_eval --model-path .models/faster-whisper-small --btc-audio-dir data/asr --team-audio-dir data_gen/audio
```

The script writes `reports/asr_metrics.json` and `reports/asr_hypotheses.json`, separates BTC and team sets, lists missing audio IDs, and reports WER/CER plus exact entity accuracy. Text normalization uses NFC, lowercase, punctuation removal, whitespace normalization, and canonicalizes numeric forms for entities declared in that dialogue's ground truth. Hypotheses are generated only by the local ASR model; the evaluator does not put reference entity values into hypothesis output. ASR outputs are team reports, not edits to BTC files.

The transcript generator consumes deterministic facts and existing customer turns, generates paired agent replies separately from evaluation scenarios, stores raw generations separately, then validates and queues them for review. It records model, seed, time, source digests, and artifact status. It does not establish runtime agent performance.

## Verified requirements and limits

- The official brief specifies 120 transcripts, 40 audio conversations / 1 hour, 30 mult-session customers, 10 phone-plus-chat customers, 1 industry across 2 regions, three named M1 personas, 30 SKUs, and ASR WER/CER with exact entity accuracy on 20+ files.
- The clarification specifies that the 20 ASR files are team-generated in addition to BTC's supplied ASR set.
- Current evaluation scenarios are customer-only and are not counted as paired transcripts. Existing report values (81 scenario calls, 17 mult-session customers, 9 cross-channel customers) are historical scenario coverage, not accepted corpus evidence.
- A transcript is accepted only after local structural/privacy/fact checks and recorded human review. Local business-fact checking is conservative and BTC-validator compatibility remains unverified.
- Current catalog, CRM and policy facts come from BTC source data; the pipeline does not modify those source files.

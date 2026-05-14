from __future__ import annotations

from pathlib import Path

from common import RUNS_ROOT, SCHEMA_ROOT, ensure_directory

NORMALIZATION_MANIFEST_SCHEMA_VERSION = "quwoquan_data.normalization_manifest"
SOURCE_FETCH_INPUT_SCHEMA_VERSION = "quwoquan_data.normalization.source_fetch_input"
SOURCE_BUNDLE_SCHEMA_VERSION = "quwoquan_data.normalization.source_bundle"
SOURCE_BLOCK_SCHEMA_VERSION = "quwoquan_data.normalization.source_block"
SOURCE_ASSET_MANIFEST_SCHEMA_VERSION = "quwoquan_data.normalization.source_asset_manifest"
SOURCE_EXTRACTION_INPUT_SCHEMA_VERSION = "quwoquan_data.normalization.source_extraction_input"
SOURCE_EXTRACTION_RESULT_SCHEMA_VERSION = "quwoquan_data.normalization.source_extraction_result"
SOURCE_REVIEW_INPUT_SCHEMA_VERSION = "quwoquan_data.normalization.source_review_input"
SOURCE_REVIEW_RESULT_SCHEMA_VERSION = "quwoquan_data.normalization.source_review_result"
AUTHORITY_BACKCHECK_INPUT_SCHEMA_VERSION = "quwoquan_data.normalization.authority_backcheck_input"
AUTHORITY_BACKCHECK_RESULT_SCHEMA_VERSION = "quwoquan_data.normalization.authority_backcheck_result"
EVIDENCE_ESCALATION_INPUT_SCHEMA_VERSION = "quwoquan_data.normalization.evidence_escalation_input"
EVIDENCE_ESCALATION_RESULT_SCHEMA_VERSION = "quwoquan_data.normalization.evidence_escalation_result"
ENTITY_RESOLUTION_RECORD_SCHEMA_VERSION = "quwoquan_data.normalization.entity_resolution_record"
IMAGE_RESOLUTION_RECORD_SCHEMA_VERSION = "quwoquan_data.normalization.image_resolution_record"
TRACE_REPORT_SCHEMA_VERSION = "quwoquan_data.normalization.trace_report"

SCHEMA_DIR = SCHEMA_ROOT / "normalization"

INPUT_SCHEMA_BY_STAGE = {
    "fetch": "source_fetch_input.schema.json",
    "extract": "source_extraction_input.schema.json",
    "review": "source_review_input.schema.json",
    "authority": "authority_backcheck_input.schema.json",
    "escalate": "evidence_escalation_input.schema.json",
}

OUTPUT_SCHEMA_BY_STAGE = {
    "fetch": "source_bundle.schema.json",
    "extract": "source_extraction_result.schema.json",
    "review": "source_review_result.schema.json",
    "authority": "authority_backcheck_result.schema.json",
    "escalate": "evidence_escalation_result.schema.json",
}


def normalization_root(batch_label: str) -> Path:
    return RUNS_ROOT / str(batch_label).strip() / "normalization"


def manifest_path(batch_label: str) -> Path:
    return normalization_root(batch_label) / "manifest.json"


def source_root(batch_label: str) -> Path:
    return normalization_root(batch_label) / "source"


def source_bundles_root(batch_label: str) -> Path:
    return source_root(batch_label) / "bundles"


def source_bundle_dir(batch_label: str, source_ref: str) -> Path:
    return source_bundles_root(batch_label) / str(source_ref).strip()


def source_bundle_page_html_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "page.html"


def source_bundle_page_json_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "page.json"


def source_bundle_page_text_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "page.text.txt"


def source_bundle_markdown_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "source.md"


def source_bundle_blocks_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "source_blocks.ndjson"


def source_bundle_asset_manifest_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "asset_manifest.json"


def source_bundle_fetch_receipt_path(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "fetch_receipt.json"


def source_bundle_assets_dir(batch_label: str, source_ref: str) -> Path:
    return source_bundle_dir(batch_label, source_ref) / "assets"


def stage_inputs_dir(batch_label: str, stage: str) -> Path:
    return normalization_root(batch_label) / "inputs" / str(stage).strip()


def stage_results_dir(batch_label: str, stage: str) -> Path:
    return normalization_root(batch_label) / "results" / str(stage).strip()


def stage_input_path(batch_label: str, stage: str, source_ref: str) -> Path:
    return stage_inputs_dir(batch_label, stage) / f"{source_ref}.json"


def stage_result_path(batch_label: str, stage: str, source_ref: str) -> Path:
    return stage_results_dir(batch_label, stage) / f"{source_ref}.json"


def assistant_tasks_dir(batch_label: str) -> Path:
    return normalization_root(batch_label) / "assistant_tasks"


def assistant_stage_task_manifest_path(batch_label: str, stage: str) -> Path:
    return assistant_tasks_dir(batch_label) / f"{str(stage).strip()}.json"


def assistant_batch_status_path(batch_label: str) -> Path:
    return assistant_tasks_dir(batch_label) / "batch_status.json"


def compiled_dir(batch_label: str) -> Path:
    return normalization_root(batch_label) / "compiled"


def source_resolution_path(batch_label: str) -> Path:
    return compiled_dir(batch_label) / "source_resolution.ndjson"


def entity_resolution_path(batch_label: str) -> Path:
    return compiled_dir(batch_label) / "entity_resolution.ndjson"


def pending_resolution_path(batch_label: str) -> Path:
    return compiled_dir(batch_label) / "pending_resolution.ndjson"


def image_resolution_path(batch_label: str) -> Path:
    return compiled_dir(batch_label) / "image_resolution.ndjson"


def trace_dir(batch_label: str) -> Path:
    return compiled_dir(batch_label) / "trace"


def trace_report_path(batch_label: str, source_ref: str) -> Path:
    return trace_dir(batch_label) / f"{source_ref}.json"


def schema_path(filename: str) -> Path:
    return SCHEMA_DIR / filename


def input_schema_path(stage: str) -> Path:
    return schema_path(INPUT_SCHEMA_BY_STAGE[str(stage).strip()])


def output_schema_path(stage: str) -> Path:
    return schema_path(OUTPUT_SCHEMA_BY_STAGE[str(stage).strip()])


def ensure_normalization_layout(batch_label: str) -> None:
    for path in (
        normalization_root(batch_label),
        source_bundles_root(batch_label),
        stage_inputs_dir(batch_label, "fetch"),
        stage_inputs_dir(batch_label, "extract"),
        stage_inputs_dir(batch_label, "review"),
        stage_inputs_dir(batch_label, "authority"),
        stage_inputs_dir(batch_label, "escalate"),
        stage_results_dir(batch_label, "fetch"),
        stage_results_dir(batch_label, "extract"),
        stage_results_dir(batch_label, "review"),
        stage_results_dir(batch_label, "authority"),
        stage_results_dir(batch_label, "escalate"),
        assistant_tasks_dir(batch_label),
        compiled_dir(batch_label),
        trace_dir(batch_label),
    ):
        ensure_directory(path)


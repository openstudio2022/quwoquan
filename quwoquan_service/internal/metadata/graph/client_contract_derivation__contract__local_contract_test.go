package graph

import (
	"encoding/json"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestBuildDerivesClientContractFromCanonicalResponseEntity(t *testing.T) {
	t.Parallel()

	catalog := &ast.Catalog{
		Operations: []ast.Operation{
			{
				ID:               "assistant.assistant_learning_fact.AppendLearningFact",
				LocalID:          "AppendLearningFact",
				Domain:           "assistant",
				ObjectID:         "assistant.assistant_learning_fact",
				ResponseBodyKind: "ack",
			},
			{
				ID:             "assistant.assistant_entry_view.GetAssistantEntry",
				LocalID:        "GetAssistantEntry",
				Domain:         "assistant",
				ObjectID:       "assistant.assistant_entry_view",
				ResponseEntity: "AssistantEntryResponse",
			},
			{
				ID:             "assistant.assistant_run.GetAssistantRun",
				LocalID:        "GetAssistantRun",
				Domain:         "assistant",
				ObjectID:       "assistant.assistant_run",
				ResponseEntity: "AssistantRunEnvelopeWire",
			},
			{
				ID:             "assistant.assistant_run.StreamAssistantRunEvents",
				LocalID:        "StreamAssistantRunEvents",
				Domain:         "assistant",
				ObjectID:       "assistant.assistant_run",
				ResponseEntity: "AssistantStreamEvent",
			},
			{
				ID:             "search.search_index_view.Search",
				LocalID:        "Search",
				Domain:         "search",
				ObjectID:       "search.search_index_view",
				ResponseEntity: "SearchResponseView",
			},
			{
				ID:             "circle.circle.GetCircleStats",
				LocalID:        "GetCircleStats",
				Domain:         "circle",
				ObjectID:       "circle.circle",
				ResponseEntity: "CircleStatsWire",
			},
		},
		Projections: []ast.Projection{
			{
				ReadModel: "AssistantStreamEvent",
				DartClass: "AssistantStreamEventWire",
			},
			{ReadModel: "SearchResponseView"},
			{
				ReadModel: "CircleStatsWire",
				DartClass: "CircleStatsWireDto",
			},
		},
		Documents: []ast.SourceDocument{
			{
				Path: "assistant/assistant_run/schema.yaml",
				Content: json.RawMessage(
					`{"contract":"assistant_run_envelope","dart_class":"AssistantRunEnvelopeWire"}`,
				),
			},
			{
				Path: "_shared/ui_surfaces.yaml",
				Content: json.RawMessage(
					`{"surfaces":[{"owner":"assistant","operation_ids":["AppendLearningFact","GetAssistantEntry","GetAssistantRun","StreamAssistantRunEvents"]},{"owner":"search","operation_ids":["Search"]},{"owner":"circle","operation_ids":["GetCircleStats"]}]}`,
				),
			},
		},
		Governance: ast.MetadataGovernance{Types: []ast.TypeDefinition{{
			Name:     "AssistantEntryResponse",
			Domain:   "assistant",
			ObjectID: "assistant.assistant_entry_view",
		}}},
	}

	contractGraph := Build(catalog)
	want := map[string]ast.ClientContract{
		"assistant.assistant_learning_fact.AppendLearningFact": {
			DartImport:      "../assistant/assistant_operation_contracts.g.dart",
			ResponseType:    "void",
			ResponseDecoder: "decodeEmptyResponse",
		},
		"assistant.assistant_entry_view.GetAssistantEntry": {
			DartImport:      "../assistant/assistant_operation_contracts.g.dart",
			ResponseType:    "AssistantEntryResponse",
			ResponseDecoder: "decodeAssistantEntryResponse",
		},
		"assistant.assistant_run.GetAssistantRun": {
			DartImport:      "../assistant/assistant_operation_contracts.g.dart",
			ResponseType:    "AssistantRunEnvelopeWire",
			ResponseDecoder: "decodeAssistantRunEnvelopeWire",
		},
		"assistant.assistant_run.StreamAssistantRunEvents": {
			DartImport:      "../assistant/assistant_operation_contracts.g.dart",
			ResponseType:    "AssistantStreamEventWire",
			ResponseDecoder: "decodeAssistantStreamEventWire",
		},
		"search.search_index_view.Search": {
			DartImport:      "../search/search_operation_contracts.g.dart",
			ResponseType:    "SearchResponseView",
			ResponseDecoder: "decodeSearchResponseView",
		},
		"circle.circle.GetCircleStats": {
			DartImport:      "../circle/circle_operation_contracts.g.dart",
			ResponseType:    "CircleStatsWire",
			ResponseDecoder: "decodeCircleStatsWire",
		},
	}
	for _, operation := range contractGraph.Operations {
		if operation.ClientContract == nil {
			t.Fatalf("%s has no derived client contract", operation.ID)
		}
		if got := *operation.ClientContract; got != want[operation.ID] {
			t.Fatalf("%s client contract = %#v, want %#v", operation.ID, got, want[operation.ID])
		}
	}
}

func TestBuildDoesNotGuessUnknownResponseEntity(t *testing.T) {
	t.Parallel()

	contractGraph := Build(&ast.Catalog{
		Operations: []ast.Operation{{
			ID:             "assistant.assistant_entry_view.Unknown",
			LocalID:        "Unknown",
			Domain:         "assistant",
			ObjectID:       "assistant.assistant_entry_view",
			ResponseEntity: "UnownedResponse",
		}},
		Documents: []ast.SourceDocument{{
			Path: "_shared/ui_surfaces.yaml",
			Content: json.RawMessage(
				`{"surfaces":[{"owner":"assistant","operation_ids":["Unknown"]}]}`,
			),
		}},
	})
	if got := contractGraph.Operations[0].ClientContract; got != nil {
		t.Fatalf("unknown response entity produced guessed client contract: %#v", got)
	}
}

func TestBuildDoesNotDeriveClientContractForUnexposedOperation(t *testing.T) {
	t.Parallel()

	contractGraph := Build(&ast.Catalog{
		Operations: []ast.Operation{{
			ID:             "assistant.assistant_entry_view.InternalRefresh",
			LocalID:        "InternalRefresh",
			Domain:         "assistant",
			ObjectID:       "assistant.assistant_entry_view",
			ResponseEntity: "AssistantEntryResponse",
		}},
		Governance: ast.MetadataGovernance{Types: []ast.TypeDefinition{{
			Name:     "AssistantEntryResponse",
			Domain:   "assistant",
			ObjectID: "assistant.assistant_entry_view",
		}}},
		Documents: []ast.SourceDocument{{
			Path:    "_shared/ui_surfaces.yaml",
			Content: json.RawMessage(`{"surfaces":[]}`),
		}},
	})
	if got := contractGraph.Operations[0].ClientContract; got != nil {
		t.Fatalf("unexposed operation produced client contract: %#v", got)
	}
}

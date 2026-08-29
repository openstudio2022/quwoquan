package main

import (
	"reflect"
	"strings"
	"testing"
)

func TestProductOpsObjectErrorPathsDiscoverEveryObject(t *testing.T) {
	paths, err := productOpsObjectErrorPaths([]string{
		"ops/product_ops/visit_record/errors.yaml",
		"ops/product_ops/account_enforcement_case/errors.yaml",
		"ops/product_ops/event_record/errors.yaml",
	})
	if err != nil {
		t.Fatalf("discover ProductOps object errors: %v", err)
	}
	want := []string{
		"ops/product_ops/account_enforcement_case/errors.yaml",
		"ops/product_ops/event_record/errors.yaml",
		"ops/product_ops/visit_record/errors.yaml",
	}
	if !reflect.DeepEqual(paths, want) {
		t.Fatalf("discovered paths = %#v, want %#v", paths, want)
	}
}

func TestProductOpsObjectErrorPathsRejectsSharedOrNestedOwnership(t *testing.T) {
	for _, path := range []string{
		"ops/product_ops/errors.yaml",
		"ops/product_ops/account_enforcement_case/internal/errors.yaml",
		"ops/other/account_enforcement_case/errors.yaml",
	} {
		if _, err := productOpsObjectErrorPaths([]string{path}); err == nil {
			t.Fatalf("non-object ProductOps error path accepted: %s", path)
		}
	}
}

func TestValidateEventRecordFieldsAcceptsCanonicalEnvelopeAndCatalogBinding(t *testing.T) {
	catalog := eventCatalogFile{CommonFields: strings.Split(
		"logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass",
		",",
	)}
	fields := eventRecordFieldsFile{
		TypedExtensions: typedExtensionBinding{
			Catalog:            "event_catalog.yaml",
			Discriminator:      "eventType",
			DefinitionsKey:     "extension_fields",
			RequiredByEventKey: "required_extensions",
			OptionalByEventKey: "optional_extensions",
			WireEncoding:       "flattened",
			UnknownFieldPolicy: "reject",
		},
	}
	for _, name := range catalog.CommonFields {
		fields.Fields = append(fields.Fields, eventRecordField{Name: name})
	}
	if err := validateEventRecordFields(fields, catalog); err != nil {
		t.Fatalf("canonical EventRecord contract rejected: %v", err)
	}
}

func TestValidateEventRecordFieldsRejectsFlattenedExtensionAsRootState(t *testing.T) {
	catalog := eventCatalogFile{CommonFields: []string{"logType", "eventType"}}
	fields := eventRecordFieldsFile{
		Fields: []eventRecordField{{Name: "logType"}, {Name: "eventType"}, {Name: "durationMs"}},
		TypedExtensions: typedExtensionBinding{
			Catalog:            "event_catalog.yaml",
			Discriminator:      "eventType",
			DefinitionsKey:     "extension_fields",
			RequiredByEventKey: "required_extensions",
			OptionalByEventKey: "optional_extensions",
			WireEncoding:       "flattened",
			UnknownFieldPolicy: "reject",
		},
	}
	if err := validateEventRecordFields(fields, catalog); err == nil {
		t.Fatal("flattened event extension must not become EventRecord root state")
	}
}

func TestEventCatalogGeneratesConditionalResultRetention(t *testing.T) {
	catalog := eventCatalogFile{
		CommonFields:      strings.Split("logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass", ","),
		ContextExtensions: []string{"devicePlatform"},
		ExtensionFields: map[string]eventExtensionDef{
			"devicePlatform": {Type: "string"},
			"result":         {Type: "string"},
		},
		Events: []eventCatalogEntry{{
			EventType:          "media_load_state",
			LogType:            "event",
			RequiredExtensions: []string{"result"},
			NormalSampleRate:   0.1,
			SlowThresholdMS:    3000,
			AlwaysKeepResults:  []string{"failure", "timeout", "retry", "absent"},
			InternalPriority:   "normal",
		}},
	}
	if err := validateEventCatalog(catalog); err != nil {
		t.Fatalf("validate conditional result retention: %v", err)
	}

	rendered := renderEventCatalogGo(catalog, appPagesFile{})
	for _, want := range []string{
		"AlwaysKeepResults map[string]struct{}",
		`AlwaysKeepResults:map[string]struct{}{"failure":{},"timeout":{},"retry":{},"absent":{},}`,
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("generated ProductOps event catalog missing %q:\n%s", want, rendered)
		}
	}
}

func TestEventCatalogRejectsInvalidConditionalResultRetention(t *testing.T) {
	for _, test := range []struct {
		name           string
		declareResult  bool
		retainedValues []string
	}{
		{name: "result extension absent", retainedValues: []string{"failure"}},
		{name: "empty result", declareResult: true, retainedValues: []string{""}},
		{name: "duplicate result", declareResult: true, retainedValues: []string{"failure", "failure"}},
	} {
		t.Run(test.name, func(t *testing.T) {
			extensions := map[string]eventExtensionDef{
				"devicePlatform": {Type: "string"},
				"result":         {Type: "string"},
			}
			event := eventCatalogEntry{
				EventType:         "media_load_state",
				LogType:           "event",
				NormalSampleRate:  0.1,
				AlwaysKeepResults: test.retainedValues,
			}
			if test.declareResult {
				event.RequiredExtensions = []string{"result"}
			}
			catalog := eventCatalogFile{
				CommonFields:      strings.Split("logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass", ","),
				ContextExtensions: []string{"devicePlatform"},
				ExtensionFields:   extensions,
				Events:            []eventCatalogEntry{event},
			}
			if err := validateEventCatalog(catalog); err == nil {
				t.Fatalf("invalid always_keep_results accepted: %#v", test.retainedValues)
			}
		})
	}
}

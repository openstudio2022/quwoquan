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

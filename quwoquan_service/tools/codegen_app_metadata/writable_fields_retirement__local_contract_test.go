package main

import (
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"
)

func TestOperationRequestContractsReplaceWritableFieldsSingleTrack(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	type operationExpectation struct {
		operationsPath string
		operation      string
		requestEntity  string
		bodyFields     []string
	}
	expectations := []operationExpectation{
		{
			operationsPath: "user/account/invitation/operations.yaml",
			operation:      "GenerateInvitation",
			requestEntity:  "GenerateInvitationCommand",
			bodyFields:     []string{"channel", "inviteePhone", "personaId"},
		},
		{
			operationsPath: "chat/chat/message/operations.yaml",
			operation:      "SendAssistantDeliveryMessage",
			requestEntity:  "ChatSendAssistantDeliveryMessageCommand",
			bodyFields:     []string{"clientMsgId", "content", "type"},
		},
		{
			operationsPath: "entity/entity_homepage/homepage/operations.yaml",
			operation:      "IntakeHomepageCandidate",
			requestEntity:  "IntakeHomepageCandidateCommand",
			bodyFields: []string{
				"address",
				"canonicalEntityId",
				"categoryTags",
				"city",
				"coverUrl",
				"homepageType",
				"introductionAssets",
				"introductionMarkdown",
				"location",
				"objectPageTemplate",
				"subtitle",
				"title",
			},
		},
		{
			operationsPath: "entity/entity_homepage/homepage_claim_request/operations.yaml",
			operation:      "ReviewHomepageClaimRequest",
			requestEntity:  "ReviewHomepageClaimRequestCommand",
			bodyFields:     []string{"reviewNote", "status"},
		},
		{
			operationsPath: "entity/entity_homepage/homepage_status_report/operations.yaml",
			operation:      "ReviewHomepageStatusReport",
			requestEntity:  "ReviewHomepageStatusReportCommand",
			bodyFields:     []string{"reviewNote", "status"},
		},
		{
			operationsPath: "content/content/post/operations.yaml",
			operation:      "UpdatePostSettings",
			requestEntity:  "UpdatePostSettingsRequest",
			bodyFields: []string{
				"assistantUsePolicy",
				"primaryHomepageId",
				"primaryHomepageSnapshot",
				"primaryHomepageType",
				"visibility",
			},
		},
		{
			operationsPath: "content/content/post/operations.yaml",
			operation:      "PromotePostToWork",
			requestEntity:  "PromotePostToWorkRequest",
			bodyFields: []string{
				"articleAssetManifest",
				"articleMarkdown",
				"articleRenderProfile",
				"assistantUsePolicy",
				"contentType",
				"coverUrl",
				"markdownDialect",
				"primaryHomepageId",
				"primaryHomepageSnapshot",
				"primaryHomepageType",
				"semanticMentions",
				"summary",
				"title",
				"visibility",
			},
		},
	}

	for _, expectation := range expectations {
		t.Run(expectation.operation, func(t *testing.T) {
			operationsPath := filepath.Join(metadataDir, expectation.operationsPath)
			var service serviceFile
			if err := decodeMetadataDocument(operationsPath, &service); err != nil {
				t.Fatalf("read operations: %v", err)
			}
			route := findRoute(service.APIRoutes, expectation.operation)
			if route.Operation == "" {
				t.Fatalf("operation %s is absent", expectation.operation)
			}
			if route.RequestEntity != expectation.requestEntity {
				t.Fatalf(
					"request_entity = %q, want %q",
					route.RequestEntity,
					expectation.requestEntity,
				)
			}
			if route.RequestBodyKind != "object" {
				t.Fatalf(
					"request_body_kind = %q, want object",
					route.RequestBodyKind,
				)
			}

			fields, err := readFields(
				filepath.Join(filepath.Dir(operationsPath), "fields.yaml"),
			)
			if err != nil {
				t.Fatalf("read fields: %v", err)
			}
			entity, exists := fields.Entities[expectation.requestEntity]
			if !exists {
				t.Fatalf(
					"request entity %s is absent from fields.yaml",
					expectation.requestEntity,
				)
			}
			model := requestModelSpec{
				Name:   expectation.requestEntity,
				Fields: entity.Fields,
			}
			bindings := appRequestBindings{
				Path:     appBindings(route.RequestBindings.Path),
				Query:    appBindings(route.RequestBindings.Query),
				Header:   appBindings(route.RequestBindings.Header),
				Injected: appBindings(route.RequestBindings.Injected),
			}
			if err := validateRequestModelBindings(
				expectation.operation,
				model,
				route.RequestBodyKind,
				bindings,
				nil,
			); err != nil {
				t.Fatalf("request contract is not canonical: %v", err)
			}

			bound := map[string]struct{}{}
			for _, values := range [][]requestBindingDef{
				route.RequestBindings.Path,
				route.RequestBindings.Query,
				route.RequestBindings.Header,
				route.RequestBindings.Injected,
			} {
				for _, binding := range values {
					bound[binding.Field] = struct{}{}
				}
			}
			var bodyFields []string
			for _, field := range entity.Fields {
				if _, exists := bound[field.Name]; exists {
					continue
				}
				bodyFields = append(bodyFields, requestFieldWireName(field))
			}
			sort.Strings(bodyFields)
			if !reflect.DeepEqual(bodyFields, expectation.bodyFields) {
				t.Fatalf(
					"body fields = %v, want %v",
					bodyFields,
					expectation.bodyFields,
				)
			}
		})
	}
}

func TestWritableFieldsConfigurationAndGeneratorsCannotReturn(t *testing.T) {
	err := filepath.WalkDir("../../services", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "operations.yaml" {
			return nil
		}
		content, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if strings.Contains(string(content), "writable_fields") {
			t.Errorf("%s retains forbidden writable_fields configuration", path)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("scan service operations: %v", err)
	}

	entries, err := os.ReadDir(".")
	if err != nil {
		t.Fatalf("read generator directory: %v", err)
	}
	for _, entry := range entries {
		if entry.IsDir() ||
			!strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		content, readErr := os.ReadFile(entry.Name())
		if readErr != nil {
			t.Fatalf("read %s: %v", entry.Name(), readErr)
		}
		if strings.Contains(string(content), "WritableFields") ||
			strings.Contains(string(content), "writable_fields") {
			t.Errorf("%s retains forbidden writable-fields generator state", entry.Name())
		}
	}

	appDir := filepath.Clean("../../../quwoquan_app")
	for _, legacyPath := range []string{
		"lib/cloud/runtime/generated/circle/circle_write_wire_writable_keys.g.dart",
		"lib/cloud/runtime/generated/content/content_post_mutation_wires.g.dart",
		"lib/cloud/runtime/generated/entity/entity_homepage_mutation_wires.g.dart",
	} {
		path := filepath.Join(appDir, legacyPath)
		if _, statErr := os.Stat(path); !os.IsNotExist(statErr) {
			t.Errorf("retired App artifact still exists: %s", path)
		}
	}

	for _, generatorPath := range []string{
		"circle_write_wire_keys_codegen.go",
		"content_post_mutation_wires_codegen.go",
		"entity_homepage_mutation_wires_codegen.go",
	} {
		if _, statErr := os.Stat(generatorPath); !os.IsNotExist(statErr) {
			t.Errorf("retired special generator still exists: %s", generatorPath)
		}
	}
}

func appBindings(values []requestBindingDef) []appRequestBinding {
	out := make([]appRequestBinding, 0, len(values))
	for _, value := range values {
		out = append(out, appRequestBinding{
			Name:     value.Name,
			Field:    value.Field,
			Required: value.Required,
		})
	}
	return out
}

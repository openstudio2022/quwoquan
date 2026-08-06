package main

import (
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
	"testing"
)

func TestRenderOperationRequestPartProjectsCanonicalNonBodyBindings(t *testing.T) {
	required := true
	optional := false
	model := requestModelSpec{
		Name: "UpdateThingRequest",
		Fields: []fieldDef{
			{
				Name:        "thingId",
				Type:        "string",
				Constraints: []string{"NOT_BLANK"},
			},
			{
				Name:           "expectedVersion",
				Type:           "int",
				Constraints:    []string{"POSITIVE"},
				ClientWire:     "quoted",
				ClientDartType: "int",
			},
			{
				Name:          "limit",
				Type:          "int",
				Constraints:   []string{"NULLABLE", "MAX_100"},
				ClientDefault: "null",
			},
			{
				Name:          "page",
				Type:          "int",
				Constraints:   []string{"POSITIVE"},
				ClientDefault: "1",
			},
			{
				Name:        "title",
				Type:        "string",
				Constraints: []string{"NOT_BLANK", "MAX_LENGTH_80"},
			},
		},
	}
	rendered, err := renderOperationRequestPart(
		requestLibrarySpec{
			OwnerImport: "../thing/thing_contracts.dart",
			Models: map[string]requestModelSpec{
				model.Name: model,
			},
			Operations: []requestOperationSpec{
				{
					CanonicalOperationID: "thing.thing.UpdateThing",
					RequestType:          model.Name,
					RequestBodyKind:      "object",
					RequestBindings: appRequestBindings{
						Path: []appRequestBinding{
							{Name: "thingId", Field: "thingId", Required: &required},
						},
						Query: []appRequestBinding{
							{Name: "limit", Field: "limit", Required: &optional},
							{Name: "page", Field: "page", Required: &optional},
						},
						Header: []appRequestBinding{
							{
								Name:     "If-Match",
								Field:    "expectedVersion",
								Required: &required,
							},
						},
					},
				},
			},
		},
		"../../../thing/thing_contracts.dart",
		nil,
	)
	if err != nil {
		t.Fatalf("renderOperationRequestPart() error = %v", err)
	}
	for _, expected := range []string{
		"final class UpdateThingRequest",
		"thingId = thingId",
		"expectedVersion = expectedVersion",
		"limit = limit",
		"page = page",
		"title = title",
		`"thingId": request.thingId`,
		`if (request.limit != null) "limit": (request.limit!).toString()`,
		`"page": (request.page).toString()`,
		`"If-Match": '"${request.expectedVersion}"'`,
		`"title": request.title`,
		"encodeThingThingUpdateThingGeneratedRequest",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated request part misses %q:\n%s", expected, rendered)
		}
	}
	for _, forbidden := range []string{
		"_normalizeGeneratedOptionalText",
		"_normalizeGeneratedTextList",
		`if (request.page != null)`,
	} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("generated request part emits unused helper %q:\n%s", forbidden, rendered)
		}
	}
	bodyStart := strings.Index(rendered, "body: <String, Object?>{")
	if bodyStart < 0 {
		t.Fatalf("generated request part has no body:\n%s", rendered)
	}
	body := rendered[bodyStart:]
	for _, forbidden := range []string{
		`"thingId"`,
		`"limit"`,
		`"expectedVersion"`,
	} {
		if strings.Contains(body, forbidden) {
			t.Fatalf("body repeats canonical non-body field %q:\n%s", forbidden, body)
		}
	}
}

func TestProjectClientRequestModelExcludesInjectedIdentityAndUsesNoArgConstructor(
	t *testing.T,
) {
	model := requestModelSpec{
		Name: "IssueConnectionTicketRequest",
		Fields: []fieldDef{
			{Name: "accountId", Type: "string"},
			{Name: "personaId", Type: "string"},
			{Name: "deviceId", Type: "string"},
		},
	}
	projected := projectClientRequestModel(
		model,
		appRequestBindings{
			Injected: []appRequestBinding{
				{Name: "authenticatedAccountId", Field: "accountId"},
				{Name: "authenticatedPersonaId", Field: "personaId"},
				{Name: "authenticatedDeviceId", Field: "deviceId"},
			},
		},
	)
	if len(projected.Fields) != 0 {
		t.Fatalf("projected client fields = %#v, want none", projected.Fields)
	}
	rendered, err := renderOperationRequestPart(
		requestLibrarySpec{
			Models: map[string]requestModelSpec{projected.Name: projected},
			Operations: []requestOperationSpec{
				{
					CanonicalOperationID: "realtime.connection.IssueConnectionTicket",
					RequestType:          projected.Name,
					RequestBodyKind:      "none",
					RequestBindings: appRequestBindings{
						Injected: []appRequestBinding{
							{Name: "authenticatedAccountId", Field: "accountId"},
							{Name: "authenticatedPersonaId", Field: "personaId"},
							{Name: "authenticatedDeviceId", Field: "deviceId"},
						},
					},
				},
			},
		},
		"connection_contracts.dart",
		nil,
	)
	if err != nil {
		t.Fatalf("renderOperationRequestPart() error = %v", err)
	}
	if !strings.Contains(
		rendered,
		"final class IssueConnectionTicketRequest {\n  const IssueConnectionTicketRequest();\n}",
	) {
		t.Fatalf("generated request has no canonical no-arg constructor:\n%s", rendered)
	}
	for _, forbidden := range []string{
		"IssueConnectionTicketRequest({",
		"final String accountId",
		"final String personaId",
		"final String deviceId",
	} {
		if strings.Contains(rendered, forbidden) {
			t.Fatalf("generated request exposes injected field %q:\n%s", forbidden, rendered)
		}
	}
}

func TestProjectClientRequestModelRetainsClientBindings(t *testing.T) {
	model := requestModelSpec{
		Name: "ListSkillsQuery",
		Fields: []fieldDef{
			{Name: "limit", Type: "int", Constraints: []string{"NULLABLE"}},
			{Name: "accountId", Type: "string"},
		},
	}
	projected := projectClientRequestModel(
		model,
		appRequestBindings{
			Query: []appRequestBinding{
				{Name: "limit", Field: "limit"},
			},
			Injected: []appRequestBinding{
				{Name: "authenticatedAccountId", Field: "accountId"},
			},
		},
	)
	if len(projected.Fields) != 1 || projected.Fields[0].Name != "limit" {
		t.Fatalf("projected client fields = %#v, want limit only", projected.Fields)
	}
}

func TestApplyOperationPaginationContractAddsOneCanonicalLimitBoundary(
	t *testing.T,
) {
	model, err := applyOperationPaginationContract(
		"content.post.GetFeed",
		requestModelSpec{
			Name: "ContentDiscoveryFeedQuery",
			Fields: []fieldDef{{
				Name:          "limit",
				Type:          "int",
				ClientDefault: "GeneratedContentPostGetFeedPolicy.defaultItems",
			}},
		},
		"none",
		appRequestBindings{Query: []appRequestBinding{{
			Name:  "limit",
			Field: "limit",
		}}},
		&appPaginationPolicy{DefaultItems: 20, MaximumItems: 20},
	)
	if err != nil {
		t.Fatalf("applyOperationPaginationContract() error = %v", err)
	}
	constraints := model.Fields[0].Constraints
	for _, required := range []string{"POSITIVE", "MAX_20"} {
		if !containsString(constraints, required) {
			t.Fatalf("pagination constraints = %#v, missing %q", constraints, required)
		}
	}
}

func TestApplyOperationPaginationContractOwnsNumericClientDefault(t *testing.T) {
	model, err := applyOperationPaginationContract(
		"search.search_request_fact.ListHotQueries",
		requestModelSpec{
			Name:   "ListHotQueriesQuery",
			Fields: []fieldDef{{Name: "limit", Type: "int"}},
		},
		"none",
		appRequestBindings{Query: []appRequestBinding{{
			Name: "limit", Field: "limit",
		}}},
		&appPaginationPolicy{DefaultItems: 10, MaximumItems: 20},
	)
	if err != nil {
		t.Fatalf("applyOperationPaginationContract() error = %v", err)
	}
	if got := model.Fields[0].ClientDefault; got != "10" {
		t.Fatalf("pagination-owned client default = %q, want 10", got)
	}

	_, err = applyOperationPaginationContract(
		"search.search_request_fact.ListHotQueries",
		requestModelSpec{
			Name: "ListHotQueriesQuery",
			Fields: []fieldDef{{
				Name: "limit", Type: "int", ClientDefault: "9",
			}},
		},
		"none",
		appRequestBindings{Query: []appRequestBinding{{
			Name: "limit", Field: "limit",
		}}},
		&appPaginationPolicy{DefaultItems: 10, MaximumItems: 20},
	)
	if err == nil || !strings.Contains(err.Error(), "differs from policy default") {
		t.Fatalf("pagination accepted a conflicting numeric client default: %v", err)
	}
}

func TestApplyOperationPaginationContractAcceptsCanonicalObjectBodyLimit(
	t *testing.T,
) {
	model, err := applyOperationPaginationContract(
		"chat.message.SyncMessages",
		requestModelSpec{
			Name: "ChatSyncMessagesQuery",
			Fields: []fieldDef{{
				Name:          "limit",
				Type:          "int",
				ClientDefault: "500",
			}},
		},
		"object",
		appRequestBindings{},
		&appPaginationPolicy{DefaultItems: 500, MaximumItems: 500},
	)
	if err != nil {
		t.Fatalf("applyOperationPaginationContract() error = %v", err)
	}
	for _, required := range []string{"POSITIVE", "MAX_500"} {
		if !containsString(model.Fields[0].Constraints, required) {
			t.Fatalf(
				"object-body pagination constraints = %#v, missing %q",
				model.Fields[0].Constraints,
				required,
			)
		}
	}
	if model.Pagination == nil ||
		model.Pagination.Field != "limit" ||
		model.Pagination.DefaultItems != 500 ||
		model.Pagination.MaximumItems != 500 {
		t.Fatalf("object-body pagination metadata = %#v", model.Pagination)
	}

	var rendered strings.Builder
	if err := renderRequestModel(&rendered, model, nil); err != nil {
		t.Fatalf("renderRequestModel() error = %v", err)
	}
	for _, expected := range []string{
		"static const int defaultLimit = 500;",
		"static const int maximumLimit = 500;",
	} {
		if !strings.Contains(rendered.String(), expected) {
			t.Fatalf(
				"generated request model misses %q:\n%s",
				expected,
				rendered.String(),
			)
		}
	}
}

func TestRenderRequestModelRejectsDetachedPaginationConstants(t *testing.T) {
	var rendered strings.Builder
	err := renderRequestModel(
		&rendered,
		requestModelSpec{
			Name:   "DetachedPaginationQuery",
			Fields: []fieldDef{{Name: "cursor", Type: "string"}},
			Pagination: &requestPaginationSpec{
				Field:        "limit",
				DefaultItems: 20,
				MaximumItems: 20,
			},
		},
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "field limit is absent") {
		t.Fatalf("detached pagination constants error = %v", err)
	}
}

func TestValidateVersionPreconditionRequestContractRequiresQuotedPositiveETag(
	t *testing.T,
) {
	operation := appExposedOperation{
		CanonicalOperationID: "circle.circle_file.UpdateCircleFile",
		Concurrency:          appConcurrencyPolicy{VersionPrecondition: "if_match"},
	}
	model := requestModelSpec{
		Name: "UpdateCircleFileCommand",
		Fields: []fieldDef{{
			Name:        "expectedVersion",
			Type:        "int",
			Constraints: []string{"POSITIVE"},
			ClientWire:  "quoted",
		}},
	}
	bindings := appRequestBindings{Header: []appRequestBinding{{
		Name: "If-Match", Field: "expectedVersion",
	}}}
	if err := validateVersionPreconditionRequestContract(
		operation,
		model,
		bindings,
	); err != nil {
		t.Fatalf("valid If-Match contract rejected: %v", err)
	}

	model.Fields[0].ClientWire = ""
	err := validateVersionPreconditionRequestContract(operation, model, bindings)
	if err == nil || !strings.Contains(err.Error(), "client_wire quoted") {
		t.Fatalf("unquoted If-Match contract accepted: %v", err)
	}
}

func TestRenderRequestModelPreservesConstOnlyWithoutRuntimeWork(t *testing.T) {
	var simple strings.Builder
	if err := renderRequestModel(
		&simple,
		requestModelSpec{
			Name: "SimpleQuery",
			Fields: []fieldDef{{
				Name: "limit",
				Type: "int",
			}},
		},
		nil,
	); err != nil {
		t.Fatalf("render simple request: %v", err)
	}
	if !strings.Contains(simple.String(), "const SimpleQuery({") {
		t.Fatalf("simple immutable request lost const constructor:\n%s", simple.String())
	}

	var validated strings.Builder
	if err := renderRequestModel(
		&validated,
		requestModelSpec{
			Name: "BoundedQuery",
			Fields: []fieldDef{{
				Name:        "limit",
				Type:        "int",
				Constraints: []string{"POSITIVE"},
			}},
		},
		nil,
	); err != nil {
		t.Fatalf("render validated request: %v", err)
	}
	if strings.Contains(validated.String(), "const BoundedQuery({") ||
		!strings.Contains(validated.String(), "must be positive") {
		t.Fatalf("validated request must remain runtime-checked:\n%s", validated.String())
	}
}

func TestRenderRequestModelWireDecoderUsesCanonicalFieldDecodersAndDefaults(
	t *testing.T,
) {
	var rendered strings.Builder
	if err := renderRequestModel(
		&rendered,
		requestModelSpec{
			Name: "SubmitCommand",
			Fields: []fieldDef{
				{
					Name:            "mentions",
					Type:            "[]Mention",
					ClientDefault:   "const []",
					ClientOmitEmpty: true,
				},
				{
					Name:           "deviceInfo",
					Type:           "DeviceInfo",
					ClientDartType: "DeviceInfo?",
					Constraints:    []string{"NULLABLE"},
				},
			},
		},
		nil,
	); err != nil {
		t.Fatalf("render request decoder: %v", err)
	}
	for _, expected := range []string{
		"factory SubmitCommand.fromWire(",
		`map.containsKey("mentions") ? List<Mention>.unmodifiable(`,
		": const []",
		"Mention.fromWire(_generatedRequestObject(entry.value",
		`map["deviceInfo"] == null ? null : DeviceInfo.fromWire(`,
	} {
		if !strings.Contains(rendered.String(), expected) {
			t.Fatalf("generated request decoder misses %q:\n%s", expected, rendered.String())
		}
	}
}

func TestRenderRequestModelValidatesNormalizedValue(t *testing.T) {
	var rendered strings.Builder
	if err := renderRequestModel(
		&rendered,
		requestModelSpec{
			Name: "NormalizedQuery",
			Fields: []fieldDef{{
				Name:                "query",
				Type:                "string",
				Constraints:         []string{"NOT_BLANK"},
				ClientNormalization: "trim",
			}},
		},
		nil,
	); err != nil {
		t.Fatalf("render normalized request: %v", err)
	}
	if !strings.Contains(rendered.String(), "if (this.query.isEmpty)") {
		t.Fatalf(
			"normalized request validates the raw parameter instead of the owned value:\n%s",
			rendered.String(),
		)
	}
}

func TestRenderRequestModelEmitsCanonicalConditionalPresenceValidation(
	t *testing.T,
) {
	var rendered strings.Builder
	if err := renderRequestModel(
		&rendered,
		requestModelSpec{
			Name: "CreateAssetCommand",
			Fields: []fieldDef{
				{
					Name:           "assetType",
					Type:           "AssetType",
					EnumRef:        "AssetType",
					ClientDartType: "AssetType",
					ClientWire:     "canonicalEnum",
				},
				{
					Name: "assetId",
					Type: "string",
					Constraints: []string{
						"NULLABLE",
						"REQUIRED_WHEN_assetType_file",
						"FORBIDDEN_WHEN_assetType_folder",
						"FORBIDDEN_UNLESS_assetType_file",
					},
					ClientDartType:      "String?",
					ClientNormalization: "trim_to_null",
				},
			},
		},
		map[string][]string{"AssetType": {"file", "folder"}},
	); err != nil {
		t.Fatalf("render conditional request: %v", err)
	}
	for _, expected := range []string{
		"this.assetType == AssetType.file && this.assetId == null",
		"this.assetType == AssetType.folder && this.assetId != null",
		"this.assetType != AssetType.file && this.assetId != null",
	} {
		if !strings.Contains(rendered.String(), expected) {
			t.Fatalf("conditional request misses %q:\n%s", expected, rendered.String())
		}
	}
}

func TestRenderRequestEncoderOmitsEmptyBoundCollection(t *testing.T) {
	required := false
	var rendered strings.Builder
	err := renderRequestEncoder(
		&rendered,
		requestOperationSpec{
			CanonicalOperationID: "content.post.GetFeed",
			RequestType:          "ContentFeedQuery",
			RequestBodyKind:      "none",
			RequestBindings: appRequestBindings{
				Header: []appRequestBinding{{
					Name: "X-Blocked-Keywords", Field: "blockedKeywords", Required: &required,
				}},
			},
		},
		requestModelSpec{
			Name: "ContentFeedQuery",
			Fields: []fieldDef{{
				Name:            "blockedKeywords",
				Type:            "[]string",
				ClientDartType:  "List<String>",
				ClientWire:      "uri_csv",
				ClientOmitEmpty: true,
			}},
		},
		nil,
	)
	if err != nil {
		t.Fatalf("render bound collection: %v", err)
	}
	if !strings.Contains(
		rendered.String(),
		`if (request.blockedKeywords.isNotEmpty) "X-Blocked-Keywords"`,
	) {
		t.Fatalf("bound empty collection is not omitted:\n%s", rendered.String())
	}
}

func TestValidateRequestModelDefaultsRejectsNotBlankEmptyListDefault(
	t *testing.T,
) {
	for _, clientDefault := range []string{
		"const []",
		"const <String>[]",
		"<String>[]",
	} {
		t.Run(clientDefault, func(t *testing.T) {
			err := validateRequestModelDefaults(
				"chat.message.SendMessage",
				requestModelSpec{
					Name: "ChatSendMessageCommand",
					Fields: []fieldDef{{
						Name:          "mentions",
						Type:          "[]string",
						Constraints:   []string{"NOT_BLANK"},
						ClientDefault: clientDefault,
					}},
				},
			)
			if err == nil || !strings.Contains(
				err.Error(),
				"combines NOT_BLANK with explicit empty list client_default",
			) {
				t.Fatalf("error = %v, want contradictory list default failure", err)
			}
		})
	}
}

func TestValidateRequestModelDefaultsAllowsCanonicalEmptyListDefault(
	t *testing.T,
) {
	err := validateRequestModelDefaults(
		"chat.message.SendMessage",
		requestModelSpec{
			Name: "ChatSendMessageCommand",
			Fields: []fieldDef{{
				Name:          "mentions",
				Type:          "[]string",
				ClientDefault: "const <String>[]",
			}},
		},
	)
	if err != nil {
		t.Fatalf("canonical optional empty list default rejected: %v", err)
	}
}

func TestRenderOperationRequestPartEmitsOnlyRequiredNormalizationHelpers(t *testing.T) {
	for _, test := range []struct {
		name          string
		normalization string
		fieldType     string
		dartType      string
		want          string
		forbid        string
	}{
		{
			name:          "optional text",
			normalization: "trim_to_null",
			fieldType:     "string",
			dartType:      "String?",
			want:          "_normalizeGeneratedOptionalText",
			forbid:        "_normalizeGeneratedTextList",
		},
		{
			name:          "text list",
			normalization: "trim_dedupe_drop_empty",
			fieldType:     "[]string",
			dartType:      "List<String>",
			want:          "_normalizeGeneratedTextList",
			forbid:        "_normalizeGeneratedOptionalText",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			model := requestModelSpec{
				Name: "NormalizeRequest",
				Fields: []fieldDef{{
					Name:                "value",
					Type:                test.fieldType,
					ClientDartType:      test.dartType,
					ClientNormalization: test.normalization,
					Constraints:         []string{"NULLABLE"},
				}},
			}
			rendered, err := renderOperationRequestPart(
				requestLibrarySpec{
					Models: map[string]requestModelSpec{model.Name: model},
				},
				"normalize_contracts.dart",
				nil,
			)
			if err != nil {
				t.Fatalf("renderOperationRequestPart() error = %v", err)
			}
			if !strings.Contains(rendered, test.want) {
				t.Fatalf("generated request part misses helper %q:\n%s", test.want, rendered)
			}
			if strings.Contains(rendered, test.forbid) {
				t.Fatalf("generated request part emits unrelated helper %q:\n%s", test.forbid, rendered)
			}
		})
	}
}

func TestRenderOperationRequestPartNormalizesIterableStringTrimAsTextList(
	t *testing.T,
) {
	model := requestModelSpec{
		Name: "ValidateTagsQuery",
		Fields: []fieldDef{
			{
				Name:                "tagRefs",
				Type:                "[]string",
				ClientDartType:      "List<String>",
				ClientParameterType: "Iterable<String>",
				ClientNormalization: "trim",
			},
		},
	}
	rendered, err := renderOperationRequestPart(
		requestLibrarySpec{
			Models: map[string]requestModelSpec{model.Name: model},
		},
		"tag_contracts.dart",
		nil,
	)
	if err != nil {
		t.Fatalf("renderOperationRequestPart() error = %v", err)
	}
	for _, expected := range []string{
		"_normalizeGeneratedTextList",
		"required Iterable<String> tagRefs",
		"tagRefs = _normalizeGeneratedTextList(tagRefs, deduplicate: false)",
		"final List<String> tagRefs",
	} {
		if !strings.Contains(rendered, expected) {
			t.Fatalf("generated request misses %q:\n%s", expected, rendered)
		}
	}
	if strings.Contains(rendered, "tagRefs = tagRefs.trim()") {
		t.Fatalf("generated request calls String.trim on Iterable<String>:\n%s", rendered)
	}
}

func TestValidateRequestModelBindingsRejectsIncompleteSingleTrack(t *testing.T) {
	required := true
	model := requestModelSpec{
		Name: "ThingQuery",
		Fields: []fieldDef{
			{Name: "thingId", Type: "string"},
		},
	}
	tests := []struct {
		name     string
		bodyKind string
		bindings appRequestBindings
		want     string
	}{
		{
			name:     "bodyless operation leaves an unbound field",
			bodyKind: "none",
			want:     "without a canonical non-body binding",
		},
		{
			name:     "object body becomes empty",
			bodyKind: "object",
			bindings: appRequestBindings{
				Path: []appRequestBinding{
					{Name: "thingId", Field: "thingId", Required: &required},
				},
			},
			want: "empty body",
		},
		{
			name:     "binding points outside request model",
			bodyKind: "none",
			bindings: appRequestBindings{
				Path: []appRequestBinding{
					{Name: "missingId", Field: "missingId", Required: &required},
				},
			},
			want: "is absent from request_entity",
		},
		{
			name:     "field occupies two wire positions",
			bodyKind: "none",
			bindings: appRequestBindings{
				Path: []appRequestBinding{
					{Name: "thingId", Field: "thingId", Required: &required},
				},
				Query: []appRequestBinding{
					{Name: "thingId", Field: "thingId", Required: &required},
				},
			},
			want: "bound to both path and query",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := validateRequestModelBindings(
				"thing.thing.GetThing",
				model,
				test.bodyKind,
				test.bindings,
				nil,
			)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want substring %q", err, test.want)
			}
		})
	}
}

func TestRequestFieldWireExpressionInfersGeneratedValueObjectSerialization(t *testing.T) {
	got, err := requestFieldWireExpression(
		"request.subject",
		fieldDef{
			Name:           "subject",
			Type:           "SubjectRef",
			ClientDartType: "FollowSubjectRef",
		},
		false,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if got != "request.subject.toWire()" {
		t.Fatalf("custom value object wire expression = %q", got)
	}
}

func TestCanonicalExternalSearchEnumsUseTheirGeneratedWireValue(t *testing.T) {
	for _, enumRef := range []string{
		"CanonicalSearchMode",
		"SearchFeedbackEventType",
	} {
		if got := canonicalEnumWireGetter(enumRef); got != "wireValue" {
			t.Fatalf("%s wire getter = %q, want wireValue", enumRef, got)
		}
	}
	if got := canonicalEnumWireGetter("Visibility"); got != "wireName" {
		t.Fatalf("Visibility wire getter = %q, want wireName", got)
	}
}

func TestRequestFieldWireExpressionSerializesCanonicalDatetime(t *testing.T) {
	field := fieldDef{
		Name:        "capturedAt",
		Type:        "datetime",
		Constraints: []string{"NULLABLE"},
	}
	dartType, nullable, err := requestFieldDartType(field)
	if err != nil {
		t.Fatal(err)
	}
	if dartType != "DateTime?" || !nullable {
		t.Fatalf("datetime type = %q nullable=%v", dartType, nullable)
	}
	got, err := requestFieldWireExpression(
		"request.capturedAt",
		field,
		false,
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	if got != "request.capturedAt!.toUtc().toIso8601String()" {
		t.Fatalf("datetime wire expression = %q", got)
	}
}

func TestRequestFieldWireExpressionRequiresExplicitListSerializationInStringPosition(
	t *testing.T,
) {
	_, err := requestFieldWireExpression(
		"request.blockedKeywords",
		fieldDef{
			Name:           "blockedKeywords",
			Type:           "[]string",
			ClientDartType: "List<String>",
		},
		true,
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "client_wire uri_csv") {
		t.Fatalf("error = %v, want explicit uri_csv failure", err)
	}
}

func TestRequestFieldWireExpressionUsesCanonicalURICSVForStringLists(t *testing.T) {
	got, err := requestFieldWireExpression(
		"request.blockedKeywords",
		fieldDef{
			Name:           "blockedKeywords",
			Type:           "[]string",
			ClientDartType: "List<String>",
			ClientWire:     "uri_csv",
		},
		true,
		nil,
	)
	if err != nil {
		t.Fatalf("requestFieldWireExpression() error = %v", err)
	}
	want := "request.blockedKeywords.map(Uri.encodeQueryComponent).join(',')"
	if got != want {
		t.Fatalf("requestFieldWireExpression() = %q, want %q", got, want)
	}
}

func TestRequestFieldWireExpressionProjectsCanonicalEnumGenerically(t *testing.T) {
	got, err := requestFieldWireExpression(
		"request.state",
		fieldDef{
			Name:           "state",
			Type:           "ReviewState",
			EnumRef:        "ReviewState",
			ClientDartType: "ReviewState",
			ClientWire:     "canonicalEnum",
		},
		false,
		map[string][]string{
			"ReviewState": {"pending_review", "accepted"},
		},
	)
	if err != nil {
		t.Fatalf("requestFieldWireExpression() error = %v", err)
	}
	want := "switch (request.state) { ReviewState.pendingReview => \"pending_review\", ReviewState.accepted => \"accepted\", }"
	if got != want {
		t.Fatalf("requestFieldWireExpression() = %q, want %q", got, want)
	}
}

func TestRequestFieldWireExpressionRejectsCanonicalEnumWithoutCatalog(t *testing.T) {
	_, err := requestFieldWireExpression(
		"request.state",
		fieldDef{
			Name:           "state",
			Type:           "ReviewState",
			EnumRef:        "ReviewState",
			ClientDartType: "ReviewState",
			ClientWire:     "canonicalEnum",
		},
		false,
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "has no canonical values") {
		t.Fatalf("error = %v, want missing canonical enum values failure", err)
	}
}

func TestValidateCanonicalRequestEnumFieldUsesEnumRefAsSingleTruth(t *testing.T) {
	enums := map[string][]string{
		"ReviewState": {"pending_review", "accepted"},
	}
	tests := []struct {
		name  string
		field fieldDef
		want  string
	}{
		{
			name: "missing enum ref",
			field: fieldDef{
				Name:           "state",
				Type:           "ReviewState",
				ClientDartType: "ReviewState",
				ClientWire:     "canonicalEnum",
			},
			want: "requires explicit enum_ref",
		},
		{
			name: "legacy name serialization",
			field: fieldDef{
				Name:           "state",
				Type:           "ReviewState",
				EnumRef:        "ReviewState",
				ClientDartType: "ReviewState",
				ClientWire:     "name",
			},
			want: "only permits implicit enum_ref serialization",
		},
	}
	if err := validateCanonicalRequestEnumField(
		fieldDef{
			Name:           "state",
			Type:           "ReviewState",
			EnumRef:        "ReviewState",
			ClientDartType: "ReviewState",
		},
		enums,
	); err != nil {
		t.Fatalf("implicit canonical enum_ref serialization rejected: %v", err)
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			err := validateCanonicalRequestEnumField(test.field, enums)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want substring %q", err, test.want)
			}
		})
	}
	if err := validateCanonicalRequestEnumField(
		fieldDef{
			Name:           "state",
			Type:           "ClientReviewState",
			EnumRef:        "ReviewState",
			ClientDartType: "ClientReviewState",
			ClientWire:     "canonicalEnum",
		},
		enums,
	); err != nil {
		t.Fatalf("explicit canonical enum alias rejected: %v", err)
	}
}

func currentSourceAppOperations(t *testing.T) []appExposedOperation {
	t.Helper()
	initializeTestContractGraph(t)
	sourceOperations := activeMetadataSource.Graph().Operations
	payload, err := json.Marshal(sourceOperations)
	if err != nil {
		t.Fatalf("encode current source operation catalog: %v", err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(payload, &operations); err != nil {
		t.Fatalf("decode current source operation catalog: %v", err)
	}
	for index := range operations {
		operations[index].CanonicalOperationID = sourceOperations[index].ID
		operations[index].LocalOperationID = sourceOperations[index].LocalID
	}
	return operations
}

func currentSourceAppClientContractLock(t *testing.T) appContractLock {
	t.Helper()
	lock := appContractLock{}
	for _, operation := range currentSourceAppOperations(t) {
		if operation.ClientContract == nil {
			continue
		}
		lock.AppExposedOperations = append(
			lock.AppExposedOperations,
			operation,
		)
	}
	if len(lock.AppExposedOperations) == 0 {
		t.Fatal("current source catalog contains no App client contract")
	}
	return lock
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCurrentSourceSearchOwnersAreCanonicalAndInternalRecoveryIsNotAppExposed(t *testing.T) {
	const currentHomepageSearchID = "entity.homepage.SearchHomepages"
	const retiredHomepageSearchID = "entity.homepage_search_item_view.SearchHomepages"
	const currentRecoveryID = "search.search_request_fact.RecoverSearchAccountClosureDeadLetter"
	const retiredRecoveryID = "search.recent_search_state.RecoverSearchAccountClosureDeadLetter"

	operations := currentSourceAppOperations(t)
	var homepageSearch *appExposedOperation
	var recovery *appExposedOperation
	for index := range operations {
		operation := &operations[index]
		switch operation.CanonicalOperationID {
		case currentHomepageSearchID:
			homepageSearch = operation
		case currentRecoveryID:
			recovery = operation
		case retiredHomepageSearchID, retiredRecoveryID:
			t.Fatalf(
				"current source catalog retained retired operation owner %s",
				operation.CanonicalOperationID,
			)
		}
	}
	if homepageSearch == nil {
		t.Fatalf("current source catalog is missing %s", currentHomepageSearchID)
	}
	if homepageSearch.ObjectID != "entity.homepage" || homepageSearch.ClientContract == nil {
		t.Fatalf(
			"%s owner/client contract = %s/%v, want entity.homepage/non-nil",
			currentHomepageSearchID,
			homepageSearch.ObjectID,
			homepageSearch.ClientContract,
		)
	}
	if recovery == nil {
		t.Fatalf("current source catalog is missing %s", currentRecoveryID)
	}
	if recovery.ObjectID != "search.search_request_fact" ||
		recovery.Principal != "operator" ||
		recovery.ClientContract != nil {
		t.Fatalf(
			"%s owner/principal/client contract = %s/%s/%v, want search.search_request_fact/operator/nil",
			currentRecoveryID,
			recovery.ObjectID,
			recovery.Principal,
			recovery.ClientContract,
		)
	}

	appSurface := currentSourceAppClientContractLock(t)
	seenHomepageSearch := false
	var feedOperation *appExposedOperation
	for _, operation := range appSurface.AppExposedOperations {
		switch operation.CanonicalOperationID {
		case currentHomepageSearchID:
			seenHomepageSearch = true
		case "content.post.GetFeed":
			operation := operation
			feedOperation = &operation
		case currentRecoveryID, retiredHomepageSearchID, retiredRecoveryID:
			t.Fatalf(
				"non-App or retired operation entered App codegen surface: %s",
				operation.CanonicalOperationID,
			)
		}
	}
	if !seenHomepageSearch {
		t.Fatalf("App codegen surface is missing %s", currentHomepageSearchID)
	}
	if feedOperation == nil {
		t.Fatal("App codegen surface is missing content.post.GetFeed policy owner")
	}

	appDir := t.TempDir()
	if err := writeGeneratedOperationContracts(
		appDir,
		appContractLock{AppExposedOperations: []appExposedOperation{
			*homepageSearch,
			*feedOperation,
		}},
		map[string]operationRequestArtifact{
			currentHomepageSearchID: {
				RequestType: homepageSearch.RequestEntity,
				Encoder: generatedOperationRequestEncoder(
					currentHomepageSearchID,
				),
			},
			"content.post.GetFeed": {
				RequestType: feedOperation.RequestEntity,
				Encoder: generatedOperationRequestEncoder(
					"content.post.GetFeed",
				),
			},
		},
	); err != nil {
		t.Fatal(err)
	}
	generated := readGeneratedTestFile(t, filepath.Join(
		appDir,
		"packages/quwoquan_cloud_contracts/lib/src/generated/operation_contracts.g.dart",
	))
	for _, expected := range []string{
		`static const String entityHomepageSearchHomepages = "entity.homepage.SearchHomepages";`,
		`entityHomepageSearchHomepages(`,
		`"entity.homepage.SearchHomepages": CloudOperationContract(`,
		`encodeEntityHomepageSearchHomepagesGeneratedRequest`,
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("canonical homepage search App surface is missing %q", expected)
		}
	}
	for _, forbidden := range []string{
		retiredHomepageSearchID,
		currentRecoveryID,
		retiredRecoveryID,
		"entityHomepageSearchItemViewSearchHomepages",
		"searchSearchRequestFactRecoverSearchAccountClosureDeadLetter",
	} {
		if strings.Contains(generated, forbidden) {
			t.Fatalf("App codegen surface retained non-App or retired operation %q", forbidden)
		}
	}
}

func TestCurrentSourceAppRequestTypedEnumsAreCanonicalSingleTrack(t *testing.T) {
	lock := currentSourceAppClientContractLock(t)
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		t.Fatalf("load canonical request enums: %v", err)
	}
	if _, exists := enumValues["CircleGroupVisibility"]; !exists {
		t.Fatal("canonical enum catalog misses CircleGroupVisibility")
	}
	violations := make([]string, 0)
	for _, operation := range lock.AppExposedOperations {
		model, _, err := loadOperationRequestModel(
			operation,
			strings.TrimSpace(operation.RequestEntity),
		)
		if err != nil {
			t.Fatalf("load %s request model: %v", operation.CanonicalOperationID, err)
		}
		for _, field := range model.Fields {
			if err := validateCanonicalRequestEnumField(field, enumValues); err != nil {
				violations = append(
					violations,
					operation.CanonicalOperationID+" "+model.Name+"."+field.Name+": "+err.Error(),
				)
			}
		}
	}
	if len(violations) > 0 {
		sort.Strings(violations)
		t.Fatalf(
			"App request typed enums are not canonical single-track:\n%s",
			strings.Join(violations, "\n"),
		)
	}
}

func TestCurrentSourceAppRequestDefaultsAreConsistent(t *testing.T) {
	lock := currentSourceAppClientContractLock(t)
	violations := make([]string, 0)
	for _, operation := range lock.AppExposedOperations {
		model, _, err := loadOperationRequestModel(
			operation,
			strings.TrimSpace(operation.RequestEntity),
		)
		if err != nil {
			t.Fatalf("load %s request model: %v", operation.CanonicalOperationID, err)
		}
		if err := validateRequestModelDefaults(
			operation.CanonicalOperationID,
			model,
		); err != nil {
			violations = append(violations, err.Error())
		}
	}
	if len(violations) > 0 {
		sort.Strings(violations)
		t.Fatalf(
			"App request defaults are contradictory:\n%s",
			strings.Join(violations, "\n"),
		)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-codegen/struct-repo-handler-migration-generation/spec.md#gwt-001
func TestCurrentSourcePaginationPublishesPerRequestLimits(t *testing.T) {
	want := map[string]struct {
		requestType string
		defaultItem int
		maximumItem int
	}{
		"chat.chat_inbox_view.ListInbox": {
			requestType: "ChatListInboxQuery",
			defaultItem: 50,
			maximumItem: 50,
		},
		"chat.message.SyncMessages": {
			requestType: "ChatSyncMessagesQuery",
			defaultItem: 500,
			maximumItem: 500,
		},
		"content.post.GetFeed": {
			requestType: "ContentDiscoveryFeedQuery",
			defaultItem: 20,
			maximumItem: 20,
		},
	}
	seen := map[string]struct{}{}
	for _, operation := range currentSourceAppClientContractLock(t).AppExposedOperations {
		expected, exists := want[operation.CanonicalOperationID]
		if !exists {
			continue
		}
		model, _, err := loadOperationRequestModel(
			operation,
			strings.TrimSpace(operation.RequestEntity),
		)
		if err != nil {
			t.Fatalf("load %s request model: %v", operation.CanonicalOperationID, err)
		}
		bindings := appRequestBindings{}
		if operation.RequestBindings != nil {
			bindings = *operation.RequestBindings
		}
		model = projectClientRequestModel(model, bindings)
		model, err = applyOperationPaginationContract(
			operation.CanonicalOperationID,
			model,
			operation.RequestBodyKind,
			bindings,
			operation.Pagination,
		)
		if err != nil {
			t.Fatalf("apply %s pagination: %v", operation.CanonicalOperationID, err)
		}
		if model.Name != expected.requestType || model.Pagination == nil ||
			model.Pagination.Field != "limit" ||
			model.Pagination.DefaultItems != expected.defaultItem ||
			model.Pagination.MaximumItems != expected.maximumItem {
			t.Fatalf(
				"%s request/pagination = %s/%#v, want %s/%d/%d",
				operation.CanonicalOperationID,
				model.Name,
				model.Pagination,
				expected.requestType,
				expected.defaultItem,
				expected.maximumItem,
			)
		}
		var rendered strings.Builder
		if err := renderRequestModel(&rendered, model, nil); err != nil {
			t.Fatalf("render %s request model: %v", operation.CanonicalOperationID, err)
		}
		for _, constant := range []string{
			fmt.Sprintf("static const int defaultLimit = %d;", expected.defaultItem),
			fmt.Sprintf("static const int maximumLimit = %d;", expected.maximumItem),
		} {
			if !strings.Contains(rendered.String(), constant) {
				t.Fatalf("%s generated request misses %q", operation.CanonicalOperationID, constant)
			}
		}
		seen[operation.CanonicalOperationID] = struct{}{}
	}
	if len(seen) != len(want) {
		missing := make([]string, 0, len(want)-len(seen))
		for operationID := range want {
			if _, exists := seen[operationID]; !exists {
				missing = append(missing, operationID)
			}
		}
		sort.Strings(missing)
		t.Fatalf("current App source misses pagination operations: %v", missing)
	}
}

func TestGeneratedOperationRequestsRejectsEmptyGreen(t *testing.T) {
	_, err := writeGeneratedOperationRequests(
		t.TempDir(),
		appContractLock{},
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "empty-green") {
		t.Fatalf("error = %v, want empty-green failure", err)
	}
}

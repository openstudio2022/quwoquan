package main

import (
	"encoding/json"
	"os"
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
		appRequestBindings{Query: []appRequestBinding{{
			Name: "limit", Field: "limit",
		}}},
		&appPaginationPolicy{DefaultItems: 10, MaximumItems: 20},
	)
	if err == nil || !strings.Contains(err.Error(), "differs from policy default") {
		t.Fatalf("pagination accepted a conflicting numeric client default: %v", err)
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

func TestRequestFieldWireExpressionRejectsUnspecifiedCustomSerialization(t *testing.T) {
	_, err := requestFieldWireExpression(
		"request.subject",
		fieldDef{
			Name:           "subject",
			Type:           "SubjectRef",
			ClientDartType: "FollowSubjectRef",
		},
		false,
		nil,
	)
	if err == nil || !strings.Contains(err.Error(), "requires canonical client_wire") {
		t.Fatalf("error = %v, want missing client_wire failure", err)
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

func TestValidateCanonicalRequestEnumFieldRejectsMissingTruthAndLegacyWire(t *testing.T) {
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
			name: "implicit enum name serialization",
			field: fieldDef{
				Name:           "state",
				Type:           "ReviewState",
				EnumRef:        "ReviewState",
				ClientDartType: "ReviewState",
			},
			want: "requires client_wire canonicalEnum",
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
			want: "requires client_wire canonicalEnum",
		},
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

func TestAcceptedAppRequestTypedEnumsAreCanonicalSingleTrack(t *testing.T) {
	lockPath := filepath.Join(
		"..",
		"..",
		"..",
		"quwoquan_app",
		"tool",
		"cloud_codegen",
		"contract_graph.lock.json",
	)
	initializeTestContractGraph(t)
	lockBytes, err := os.ReadFile(lockPath)
	if err != nil {
		t.Fatalf("read accepted App operation lock: %v", err)
	}
	var lock appContractLock
	if err := json.Unmarshal(lockBytes, &lock); err != nil {
		t.Fatalf("decode accepted App operation lock: %v", err)
	}
	activeContractLock = lock
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		t.Fatalf("load canonical request enums: %v", err)
	}
	if _, exists := enumValues["CircleGroupVisibility"]; !exists {
		t.Fatal("canonical enum catalog misses CircleGroupVisibility")
	}
	violations := make([]string, 0)
	for _, operation := range activeContractLock.AppExposedOperations {
		if operation.ClientContract == nil {
			continue
		}
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

func TestAcceptedAppRequestDefaultsAreConsistent(t *testing.T) {
	lockPath := filepath.Join(
		"..",
		"..",
		"..",
		"quwoquan_app",
		"tool",
		"cloud_codegen",
		"contract_graph.lock.json",
	)
	initializeTestContractGraph(t)
	lockBytes, err := os.ReadFile(lockPath)
	if err != nil {
		t.Fatalf("read accepted App operation lock: %v", err)
	}
	var lock appContractLock
	if err := json.Unmarshal(lockBytes, &lock); err != nil {
		t.Fatalf("decode accepted App operation lock: %v", err)
	}
	activeContractLock = lock
	violations := make([]string, 0)
	for _, operation := range activeContractLock.AppExposedOperations {
		if operation.ClientContract == nil {
			continue
		}
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

func TestGeneratedOperationRequestsRejectsEmptyGreen(t *testing.T) {
	_, err := writeGeneratedOperationRequests(t.TempDir(), appContractLock{})
	if err == nil || !strings.Contains(err.Error(), "empty-green") {
		t.Fatalf("error = %v, want empty-green failure", err)
	}
}

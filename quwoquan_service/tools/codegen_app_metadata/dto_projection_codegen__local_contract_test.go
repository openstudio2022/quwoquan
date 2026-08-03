package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestReadProjectionDoesNotInferAppDtoForBackendOnlyProjection(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	path := filepath.Join(
		metadataDir,
		"chat",
		"chat",
		"message",
		"projections",
		"chat_message_sync_slice.yaml",
	)

	projection, err := readProjection(path)
	if err != nil {
		t.Fatalf("backend-only projection rejected by App codegen: %v", err)
	}
	if len(projection.ClientProjection.Fields) != 0 {
		t.Fatalf("backend fields were inferred as App fields: %#v", projection.ClientProjection.Fields)
	}
}

func TestReadProjectionDoesNotRetainExternalAppDtoForCanonicalProjection(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	path := filepath.Join(
		metadataDir,
		"content",
		"content",
		"comment",
		"projections",
		"author_comment_page_slice.yaml",
	)

	projection, err := readProjection(path)
	if err != nil {
		t.Fatalf("canonical projection rejected: %v", err)
	}
	if projection.ClientProjection.ExternalDartPath != "" {
		t.Fatalf("canonical projection retained external Dart owner %q", projection.ClientProjection.ExternalDartPath)
	}
	if len(projection.ClientProjection.Fields) != 0 {
		t.Fatalf("canonical fields were reinterpreted by legacy DTO generator: %#v", projection.ClientProjection.Fields)
	}
}

func TestProjectionWireTypeToDartSupportsCanonicalNamedValueObjects(t *testing.T) {
	for wireType, expected := range map[string]string{
		"float64":                  "double",
		"HomepageSource":           "HomepageSource",
		"[]HomepageContentPreview": "List<HomepageContentPreview>",
		"[]IntersectionTextSpan":   "List<IntersectionTextSpan>",
	} {
		actual, err := projectionWireTypeToDart(wireType)
		if err != nil {
			t.Fatalf("projection type %s rejected: %v", wireType, err)
		}
		if actual != expected {
			t.Fatalf("projection type %s = %s, want %s", wireType, actual, expected)
		}
	}
}

func TestReadProjectionDoesNotReintroduceLegacyNestedDecoderBindings(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	path := filepath.Join(
		metadataDir,
		"entity",
		"entity_homepage",
		"homepage",
		"projections",
		"object_page_bundle.yaml",
	)

	projection, err := readProjection(path)
	if err != nil {
		t.Fatal(err)
	}
	if projection.ClientProjection.ExternalDartPath != "" {
		t.Fatalf(
			"canonical projection retained external Dart owner %q",
			projection.ClientProjection.ExternalDartPath,
		)
	}
	if len(projection.ClientProjection.Fields) != 0 {
		t.Fatalf(
			"canonical fields were reinterpreted by legacy nested decoder: %#v",
			projection.ClientProjection.Fields,
		)
	}
}

func TestRenderStandaloneDtoHasExactlyOneTrailingNewline(t *testing.T) {
	projection := clientProjection{
		DartClass: "TimestampedDto",
		Fields: []projectionFieldDef{
			{
				Name:     "createdAt",
				Source:   "createdAt",
				DartType: "DateTime",
			},
		},
	}

	generated := renderStandaloneDtoDart(projection, "fixture.yaml")
	if !strings.HasSuffix(generated, "}\n") {
		t.Fatalf("generated DTO must end with one newline")
	}
	if strings.HasSuffix(generated, "\n\n") {
		t.Fatal("generated DTO must not contain a blank line at EOF")
	}
}

func TestRenderStandaloneDtoUsesCanonicalNameAsWireKey(t *testing.T) {
	projection := clientProjection{
		DartClass: "CreatedDto",
		Fields: []projectionFieldDef{
			{Name: "conversationId", Source: "id", DartType: "String"},
		},
	}

	generated := renderStandaloneDtoDart(projection, "fixture.yaml")
	for _, expected := range []string{
		"conversationId: m['conversationId']?.toString()",
		"'conversationId': conversationId",
		"factory CreatedDto.fromReadModelMap(Map<String, dynamic> source)",
		"'conversationId': source['id']",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("canonical wire round-trip missing %q:\n%s", expected, generated)
		}
	}
	if strings.Contains(generated, "m['id']") || strings.Contains(generated, "'id': conversationId") {
		t.Fatalf("read-model source must not become a public wire key:\n%s", generated)
	}
}

func TestSpecializedDtoRenderersUseCanonicalNameAsWireKey(t *testing.T) {
	projection := clientProjection{
		DartClass: "ProjectedDto",
		BaseClass: "ContentPostViewData",
		Fields: []projectionFieldDef{
			{Name: "id", Source: "postId", DartType: "String"},
		},
	}

	for name, generated := range map[string]string{
		"feed": renderFeedItemDtoDart(projection),
		"post": renderTypedPostDtoDart(projection, "fixture.yaml"),
	} {
		if !strings.Contains(generated, "'id': id") {
			t.Fatalf("%s DTO must emit the field name as wire key:\n%s", name, generated)
		}
		if strings.Contains(generated, "m['postId']") || strings.Contains(generated, "'postId': id") {
			t.Fatalf("%s DTO must not use source as wire key:\n%s", name, generated)
		}
		if !strings.Contains(generated, "'id': source['postId']") {
			t.Fatalf("%s DTO must expose the explicit read-model projection factory:\n%s", name, generated)
		}
	}
}

func TestRenderTypedPostDtoNestedProjectionEmitsStringKeyMapHelper(
	t *testing.T,
) {
	projection := clientProjection{
		DartClass: "ProjectedPostDto",
		BaseClass: "ContentPostViewData",
		Fields: []projectionFieldDef{
			{
				Name:                  "sourceAttribution",
				Source:                "sourceAttribution",
				DartType:              "SourceAttributionDto",
				Nullable:              true,
				MapFromStringKeyClass: "SourceAttributionDto",
			},
		},
	}

	generated := renderTypedPostDtoDart(projection, "fixture.yaml")
	for _, expected := range []string{
		"SourceAttributionDto.fromMap(_parseStringKeyMap(m['sourceAttribution'])!)",
		"Map<String, dynamic>? _parseStringKeyMap(dynamic v)",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("typed post DTO nested projection missing %q:\n%s", expected, generated)
		}
	}
}

func TestRenderStandaloneDtoStrictProjectionRejectsUnknownAndInvalidWireValues(t *testing.T) {
	projection := clientProjection{
		DartClass: "StrictMessageDto",
		Strict:    true,
		Fields: []projectionFieldDef{
			{Name: "id", Source: "id", DartType: "String"},
			{Name: "mentions", Source: "mentions", DartType: "List<String>", Nullable: true},
			{Name: "timestamp", Source: "timestamp", DartType: "DateTime", Nullable: true},
			{Name: "createdAt", Source: "createdAt", DartType: "DateTime"},
		},
	}

	generated := renderStandaloneDtoDart(projection, "fixture.yaml")
	for _, expected := range []string{
		"_validateStrictMessageDtoWire(m);",
		"final unknown = m.keys.where((key) => !allowed.contains(key))",
		"!m.containsKey('id') || m['id'] == null || (m['id'] is! String)",
		"m.containsKey('mentions') && m['mentions'] != null && (m['mentions'] is! List || (m['mentions'] as List).any((value) => value is! String))",
		"DateTime.tryParse(m['timestamp'] as String) == null",
		"createdAt: DateTime.parse(m['createdAt'] as String)",
		"'timestamp': timestamp?.toIso8601String()",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("strict DTO missing %q:\n%s", expected, generated)
		}
	}
	for _, retired := range []string{
		"DateTime? _parseDateTime",
		"List<String>? _parseStringList",
	} {
		if strings.Contains(generated, retired) {
			t.Fatalf("strict DTO must not emit unused helper %q:\n%s", retired, generated)
		}
	}
}

func TestRenderStandaloneDtoUsesCanonicalGeneratedEnum(t *testing.T) {
	projection := clientProjection{
		DartClass:   "FollowingSubjectItemViewDto",
		Strict:      true,
		DartImports: []string{"package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart"},
		Fields: []projectionFieldDef{
			{
				Name:     "subjectType",
				Source:   "subjectType",
				WireType: "enum",
				DartType: "FollowSubjectKind",
				EnumRef:  "FollowSubjectKind",
			},
		},
	}

	generated := renderStandaloneDtoDart(projection, "following_subject.yaml")
	for _, expected := range []string{
		"import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';",
		"final FollowSubjectKind subjectType;",
		"subjectType: FollowSubjectKind.fromWire(m['subjectType'])",
		"'subjectType': subjectType.wireValue",
		"m['subjectType'] is! String",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("canonical enum DTO missing %q:\n%s", expected, generated)
		}
	}
	if strings.Contains(generated, "final String subjectType") {
		t.Fatalf("canonical enum was downgraded to String:\n%s", generated)
	}
}

func TestValidateClientProjectionEnumsFailsClosed(t *testing.T) {
	catalog := map[string][]string{
		"FollowSubjectKind": {"persona", "homepage", "circle", "location"},
		"OtherKind":         {"other"},
	}
	valid := projectionFieldDef{
		Name:     "subjectType",
		Source:   "subjectType",
		WireType: "enum",
		DartType: "FollowSubjectKind",
		EnumRef:  "FollowSubjectKind",
	}
	cases := []struct {
		name string
		edit func(*projectionFieldDef)
		want string
	}{
		{
			name: "missing wire enum declaration",
			edit: func(field *projectionFieldDef) { field.WireType = "" },
			want: "requires type=enum",
		},
		{
			name: "unknown enum ref",
			edit: func(field *projectionFieldDef) { field.EnumRef = "UnknownKind" },
			want: "absent from _shared/types.yaml",
		},
		{
			name: "second dart enum class",
			edit: func(field *projectionFieldDef) { field.DartType = "OtherKind" },
			want: "must use the same enum_ref",
		},
		{
			name: "client default",
			edit: func(field *projectionFieldDef) { field.Default = "FollowSubjectKind.persona" },
			want: "must not declare a default",
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			field := valid
			testCase.edit(&field)
			projection := &projectionFile{
				ClientProjection:               clientProjection{Fields: []projectionFieldDef{field}},
				clientProjectionFieldsDeclared: true,
			}
			err := validateClientProjectionEnums("projection.yaml", projection, catalog)
			if err == nil || !strings.Contains(err.Error(), testCase.want) {
				t.Fatalf("error = %v, want %q", err, testCase.want)
			}
		})
	}
}

func TestValidateClientProjectionEnumsAllowsCanonicalValidationOnlyString(t *testing.T) {
	projection := &projectionFile{
		ClientProjection: clientProjection{Fields: []projectionFieldDef{{
			Name:     "edgeType",
			DartType: "String",
			EnumRef:  "ObjectRelationEdgeType",
			Default:  "''",
		}}},
		clientProjectionFieldsDeclared: true,
	}
	err := validateClientProjectionEnums(
		"projection.yaml",
		projection,
		map[string][]string{"ObjectRelationEdgeType": {"parent", "child"}},
	)
	if err != nil {
		t.Fatalf("validation-only String enum_ref rejected: %v", err)
	}
}

func TestRenderStandaloneDtoKeepsStringWireWhenEnumRefIsValidationOnly(t *testing.T) {
	projection := clientProjection{
		DartClass: "ObjectRelationEdge",
		Fields: []projectionFieldDef{
			{
				Name:     "edgeType",
				Source:   "edgeType",
				DartType: "String",
				EnumRef:  "ObjectRelationEdgeType",
				Default:  "''",
			},
		},
	}

	generated := renderStandaloneDtoDart(projection, "object_relation_edge.yaml")
	for _, expected := range []string{
		"final String edgeType;",
		"edgeType: m['edgeType']?.toString() ?? ''",
		"'edgeType': edgeType",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("String enum-ref projection missing %q:\n%s", expected, generated)
		}
	}
	if strings.Contains(generated, "ObjectRelationEdgeType.fromWire") {
		t.Fatalf("validation-only enum_ref changed String wire type:\n%s", generated)
	}
}

func TestRenderStandaloneDtoStrictNestedProjection(t *testing.T) {
	generated := renderStandaloneDtoDart(clientProjection{
		DartClass: "EnvelopeDto",
		Strict:    true,
		Fields: []projectionFieldDef{
			{
				Name:                  "card",
				DartType:              "CardDto",
				Nullable:              true,
				Source:                "card",
				MapFromStringKeyClass: "CardDto",
			},
			{
				Name:                 "items",
				DartType:             "List<ItemDto>",
				Source:               "items",
				ListElementDartClass: "ItemDto",
			},
		},
	}, "nested.yaml")

	for _, expected := range []string{
		"card: m['card'] == null ? null : CardDto.fromMap(_parseStringKeyMap(m['card'])!)",
		"Map<String, dynamic>? _parseStringKeyMap(dynamic v)",
		"'card': card?.toMap()",
		"'items': items.map((value) => value.toMap()).toList(growable: false)",
		"m.containsKey('card') && m['card'] != null && (m['card'] is! Map",
		"!m.containsKey('items') || m['items'] == null || (m['items'] is! List",
		"value is! Map || value.keys.any((key) => key is! String)",
	} {
		if !strings.Contains(generated, expected) {
			t.Fatalf("strict nested DTO missing %q:\n%s", expected, generated)
		}
	}
	if strings.Contains(generated, "(value as Map).keys") {
		t.Fatalf("strict nested DTO must rely on flow promotion instead of an unnecessary cast:\n%s", generated)
	}
}

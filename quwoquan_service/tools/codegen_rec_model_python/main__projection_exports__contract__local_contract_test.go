package main

import (
	"strings"
	"testing"
)

func TestGenerateModelsInitProjectionExports(t *testing.T) {
	t.Run("empty projections do not import retired models", func(t *testing.T) {
		generated := generateModelsInit(nil)
		if strings.Contains(generated, "from .projections") {
			t.Fatalf("empty projection metadata must not emit projection imports:\n%s", generated)
		}
	})

	t.Run("current projections define the exported classes", func(t *testing.T) {
		generated := generateModelsInit([]projectionSpec{
			{ReadModel: "ModelRegistry"},
			{ReadModel: "TrainingSamples"},
		})
		for _, expected := range []string{"ModelRegistryEntry", "TrainingSample"} {
			if !strings.Contains(generated, expected) {
				t.Fatalf("generated exports missing %q:\n%s", expected, generated)
			}
		}
	})
}

func TestGenerateRankedWindowGoTransportExcludesInjectedRequestFields(t *testing.T) {
	generated := generateRankedWindowGoTransport(
		&fieldsFile{Entities: map[string]entityDef{
			"CreateRankedRecommendationWindowCommand": {
				Fields: []fieldDef{
					{Name: "idempotencyKey", Type: "string", Constraints: []string{"NOT_NULL"}},
					{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
					{Name: "limit", Type: "int", Constraints: []string{"NOT_NULL"}},
				},
			},
		}},
		&operationsFile{APIRoutes: []routeDef{
			{
				Method:        "POST",
				Path:          "/internal/recommendation/ranked-pages",
				Operation:     "CreateRankedRecommendationWindow",
				RequestEntity: "CreateRankedRecommendationWindowCommand",
				RequestBindings: requestBindings{Injected: []bindingDef{
					{Name: "Idempotency-Key", Field: "idempotencyKey"},
				}},
			},
		}},
	)
	bodyStart := strings.Index(generated, "type CreateRankedRecommendationWindowRequestBody struct")
	if bodyStart < 0 {
		t.Fatalf("generated transport is missing request body type:\n%s", generated)
	}
	body := generated[bodyStart:]
	if strings.Contains(body, "IdempotencyKey") {
		t.Fatalf("injected idempotency key must not be emitted in the JSON body:\n%s", body)
	}
	for _, expected := range []string{"SubjectId string", "Limit int"} {
		if !strings.Contains(body, expected) {
			t.Fatalf("generated request body missing %q:\n%s", expected, body)
		}
	}
}

func TestGenerateRankedWindowTransportIncludesObjectOwnedCardSnapshot(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"RecommendationObjectCard": {
			Fields: []fieldDef{
				{Name: "objectKind", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "objectId", Type: "string", Constraints: []string{"NOT_NULL"}},
			},
		},
		"RankedRecommendationPage": {
			Fields: []fieldDef{
				{Name: "objectCards", Type: "[]RecommendationObjectCard", Constraints: []string{"NOT_NULL"}},
			},
		},
		"GetRankedRecommendationPageQuery": {
			Fields: []fieldDef{
				{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "windowId", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "fromOrdinal", Type: "int", Constraints: []string{"NULLABLE"}},
				{Name: "limit", Type: "int", Constraints: []string{"NULLABLE"}},
			},
		},
	}}

	python := generateRequestResponsePyForNames(fields, rankedWindowTransportOrder)
	for _, expected := range []string{
		"class RecommendationObjectCard(BaseModel):",
		"class GetRankedRecommendationPageQuery(BaseModel):",
		"subjectId: str",
		"objectCards: list[RecommendationObjectCard]",
	} {
		if !strings.Contains(python, expected) {
			t.Fatalf("generated Python transport missing %q:\n%s", expected, python)
		}
	}

	goTransport := generateRankedWindowGoTransport(fields, &operationsFile{})
	for _, expected := range []string{
		"type RecommendationObjectCard struct",
		"type GetRankedRecommendationPageQuery struct",
		"SubjectId string",
		"ObjectCards []RecommendationObjectCard",
	} {
		if !strings.Contains(goTransport, expected) {
			t.Fatalf("generated Go transport missing %q:\n%s", expected, goTransport)
		}
	}
}

func TestFeatureProfileTransportUsesObjectLocalIntersectionProjectionTypes(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"IntersectionTarget": {Fields: []fieldDef{
			{Name: "objectId", Type: "string", Constraints: []string{"NOT_NULL"}},
		}},
		"IntersectionReason": {Fields: []fieldDef{
			{Name: "intersectionId", Type: "string", Constraints: []string{"NOT_NULL"}},
			{Name: "typeVisual", Type: "IntersectionTarget", Constraints: []string{"NULLABLE"}},
		}},
		"RecommendationIntersectionReasonSlice": {Fields: []fieldDef{
			{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
			{Name: "reasons", Type: "[]IntersectionReason", Constraints: []string{"NOT_NULL"}},
		}},
	}}

	python := generateRequestResponsePyForNames(fields, featureProfileTransportOrder)
	for _, expected := range []string{
		"class IntersectionReason(BaseModel):",
		"typeVisual: IntersectionTarget | None = None",
		"reasons: list[IntersectionReason]",
	} {
		if !strings.Contains(python, expected) {
			t.Fatalf("generated feature-profile Python missing %q:\n%s", expected, python)
		}
	}

	goTransport := generateFeatureProfileGoTransport(fields, &operationsFile{})
	for _, expected := range []string{
		"type IntersectionReason struct",
		"TypeVisual *IntersectionTarget",
		"Reasons []IntersectionReason",
	} {
		if !strings.Contains(goTransport, expected) {
			t.Fatalf("generated feature-profile Go missing %q:\n%s", expected, goTransport)
		}
	}
}

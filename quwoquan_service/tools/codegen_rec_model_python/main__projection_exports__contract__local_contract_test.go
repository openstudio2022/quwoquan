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

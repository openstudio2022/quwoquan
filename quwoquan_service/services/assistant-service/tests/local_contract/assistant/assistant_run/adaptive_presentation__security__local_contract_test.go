// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"strings"
	"testing"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentation "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

type actionPolicyStub struct{ reject bool }

func (p actionPolicyStub) ValidateAction(
	_ context.Context,
	_ string,
	_ presentation.ActionIntent,
) error {
	if p.reject {
		return errors.New("unreachable action")
	}
	return nil
}

type mediaPolicyStub struct{ reject bool }

func (p mediaPolicyStub) ValidateMedia(
	_ context.Context,
	_ presentation.MediaRef,
) error {
	if p.reject {
		return errors.New("unavailable media")
	}
	return nil
}

func TestAdaptivePresentationResolvesValidatedTemplateDataAndVariant(t *testing.T) {
	template := validPresentationTemplate()
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(catalog, actionPolicyStub{}, mediaPolicyStub{})
	document, err := resolver.Resolve(
		context.Background(),
		"travel",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data: map[string]any{
				"title":    "川西三日行程",
				"showRisk": true,
			},
		},
		presentation.SurfaceCapabilities{
			SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
				generated.AssistantPresentationNodeKindCard:    true,
				generated.AssistantPresentationNodeKindText:    true,
				generated.AssistantPresentationNodeKindCallout: true,
			},
			ViewportClass: "narrow",
			Density:       generated.AssistantPresentationDensityCompact,
		},
		3,
	)
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if document.UseFallback || document.SelectedVariant != "compact" || document.DataDigest == "" {
		t.Fatalf("document = %#v", document)
	}
	if len(document.Nodes) != 3 || document.Nodes[1].Title != "川西三日行程" || document.Nodes[1].Binding != nil {
		t.Fatalf("resolved nodes = %#v", document.Nodes)
	}
	if document.TemplateDigest != template.AssetDigest || document.FallbackMarkdown == "" || document.FallbackPlainText == "" {
		t.Fatalf("fallback/template fields = %#v", document)
	}
}

func TestAdaptivePresentationFallsBackForInvalidDataUnsupportedNodeOrPolicyFailure(t *testing.T) {
	template := validPresentationTemplate()
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatal(err)
	}
	tests := []struct {
		name         string
		data         map[string]any
		supported    map[generated.AssistantPresentationNodeKind]bool
		actionReject bool
		mediaReject  bool
	}{
		{
			name:      "schema invalid",
			data:      map[string]any{"title": 42, "showRisk": true},
			supported: allPresentationKinds(),
		},
		{
			name:      "bound html rejected",
			data:      map[string]any{"title": "<img src=x onerror=alert(1)>", "showRisk": true},
			supported: allPresentationKinds(),
		},
		{
			name: "unsupported semantic node",
			data: map[string]any{"title": "trip", "showRisk": true},
			supported: map[generated.AssistantPresentationNodeKind]bool{
				generated.AssistantPresentationNodeKindCard: true,
				generated.AssistantPresentationNodeKindText: true,
			},
		},
		{
			name:         "action unreachable",
			data:         map[string]any{"title": "trip", "showRisk": true},
			supported:    allPresentationKinds(),
			actionReject: true,
		},
		{
			name:        "media unavailable",
			data:        map[string]any{"title": "trip", "showRisk": true},
			supported:   allPresentationKinds(),
			mediaReject: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			resolver := presentation.NewResolver(
				catalog,
				actionPolicyStub{reject: test.actionReject},
				mediaPolicyStub{reject: test.mediaReject},
			)
			document, err := resolver.Resolve(
				context.Background(),
				"travel",
				presentation.Selection{TemplateRef: presentation.TemplateRef(template), Data: test.data},
				presentation.SurfaceCapabilities{
					SupportedNodeKinds: test.supported,
					ViewportClass:      "narrow",
					Density:            generated.AssistantPresentationDensityCompact,
				},
				1,
			)
			if err != nil {
				t.Fatal(err)
			}
			if !document.UseFallback || document.FallbackMarkdown == "" || document.FallbackPlainText == "" || document.FallbackReason == "" {
				t.Fatalf("fallback document = %#v", document)
			}
		})
	}
}

func TestAdaptivePresentationTemplateRejectsUnsafeStructureStyleAndActions(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*presentation.Template)
	}{
		{
			name: "cycle",
			mutate: func(template *presentation.Template) {
				template.Nodes[0].ParentNodeID = "risk"
			},
		},
		{
			name: "raw style token",
			mutate: func(template *presentation.Template) {
				template.Nodes[0].Style.Variant = "color:#ff0000"
			},
		},
		{
			name: "arbitrary route",
			mutate: func(template *presentation.Template) {
				template.Nodes[2].Action.Payload["route"] = "/admin"
			},
		},
		{
			name: "unknown action",
			mutate: func(template *presentation.Template) {
				template.Nodes[2].Action.Operation = "UnknownOperation"
			},
		},
		{
			name: "unclosed input schema",
			mutate: func(template *presentation.Template) {
				template.InputSchema["additionalProperties"] = true
			},
		},
		{
			name: "raw html fallback",
			mutate: func(template *presentation.Template) {
				template.FallbackMarkdown = "<script>alert(1)</script>"
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			template := validPresentationTemplate()
			test.mutate(&template)
			if err := presentation.ValidateTemplate(template); !errors.Is(err, presentation.ErrInvalidTemplate) {
				t.Fatalf("ValidateTemplate() error = %v", err)
			}
		})
	}
}

func validPresentationTemplate() presentation.Template {
	style := presentation.Style{
		Tone:           generated.AssistantPresentationToneNeutral,
		Density:        generated.AssistantPresentationDensityStandard,
		Emphasis:       "normal",
		Variant:        "standard",
		Alignment:      "start",
		SpacingRole:    "related",
		ResponsiveSpan: 1,
	}
	return presentation.Template{
		TemplateID: "travel.timeline",
		SkillID:    "travel",
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"title":    map[string]any{"type": "string"},
				"showRisk": map[string]any{"type": "boolean"},
			},
			"required": []any{"title", "showRisk"},
		},
		RootNodeID: "root",
		Nodes: []presentation.Node{
			{
				NodeID: "root",
				Kind:   generated.AssistantPresentationNodeKindCard,
				Style:  style,
				Media: &presentation.MediaRef{
					MediaAssetID:  "media_trip",
					Alt:           "川西山景",
					Width:         1200,
					Height:        800,
					ProvenanceRef: "source_media_1",
				},
			},
			{
				NodeID:       "title",
				ParentNodeID: "root",
				Kind:         generated.AssistantPresentationNodeKindText,
				Binding:      map[string]string{"title": "$.title"},
				Style:        style,
			},
			{
				NodeID:       "risk",
				ParentNodeID: "root",
				Order:        1,
				Kind:         generated.AssistantPresentationNodeKindCallout,
				Body:         "出发前确认天气预警。",
				Binding:      map[string]string{"visible": "$.showRisk"},
				Style:        style,
				Action: &presentation.ActionIntent{
					IntentID:             "open_weather",
					Operation:            "OpenWeatherDetail",
					ObjectTypeRef:        "weather_location",
					ObjectID:             "chengdu",
					Payload:              map[string]any{"sourceRef": "weather_1"},
					RequiresConfirmation: false,
				},
			},
		},
		ResponsiveVariants: []presentation.ResponsiveVariant{{
			VariantID:         "compact",
			RequiredNodeKinds: []generated.AssistantPresentationNodeKind{generated.AssistantPresentationNodeKindCard},
			ViewportClass:     "narrow",
			Density:           generated.AssistantPresentationDensityCompact,
		}},
		AllowedActionIntents: []string{"OpenWeatherDetail"},
		FallbackMarkdown:     "## 川西行程\n请查看天气与来源。",
		AssetDigest:          "sha256:" + strings.Repeat("a", 64),
	}
}

func allPresentationKinds() map[generated.AssistantPresentationNodeKind]bool {
	return map[generated.AssistantPresentationNodeKind]bool{
		generated.AssistantPresentationNodeKindCard:    true,
		generated.AssistantPresentationNodeKindText:    true,
		generated.AssistantPresentationNodeKindCallout: true,
	}
}

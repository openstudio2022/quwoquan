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
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
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

func TestAdaptivePresentationOldClientFallbackComesFromFrozenTemplateBinding(t *testing.T) {
	template := validPresentationTemplate()
	properties := template.InputSchema["properties"].(map[string]any)
	properties["answer"] = map[string]any{"type": "string"}
	template.FallbackMarkdownBinding = "$.answer"
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
	const answer = "## 西湖行程\n\n明早从断桥出发。"
	document, err := resolver.Resolve(
		t.Context(),
		"travel",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data: map[string]any{
				"title": "西湖一日行程", "showRisk": true, "answer": answer,
			},
		},
		presentation.SurfaceCapabilities{},
		1,
	)
	if err != nil || !document.UseFallback || document.FallbackMarkdown != answer ||
		document.FallbackPlainText == "" {
		t.Fatalf("old-client fallback document=%#v err=%v", document, err)
	}
}

func TestAdaptivePresentationUnknownNodeDataPolicyFailsClosed(t *testing.T) {
	template := validRouteMapTemplate()
	template.Nodes[0].DataPolicyRef = "travel.unknown.route_map"
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
	document, err := resolver.Resolve(
		t.Context(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data:        map[string]any{"routeMap": routeMapData()},
		},
		presentation.SurfaceCapabilities{
			SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
				generated.AssistantPresentationNodeKindRouteMap: true,
			},
			ViewportClass: "narrow",
			Density:       generated.AssistantPresentationDensityCompact,
		},
		1,
	)
	if err != nil || !document.UseFallback ||
		document.FallbackReason != presentation.ErrDataPolicyRejected.Error() {
		t.Fatalf("unknown-policy document=%#v err=%v", document, err)
	}
}

func TestAdaptivePresentationRejectsOversizedStructuredDataBeforeResolution(t *testing.T) {
	template := validRouteMapTemplate()
	template.InputSchema = map[string]any{
		"type":                 "object",
		"additionalProperties": false,
		"properties": map[string]any{
			"routeMap": map[string]any{"type": "object"},
		},
		"required": []any{"routeMap"},
	}
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
	document, err := resolver.Resolve(
		t.Context(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data: map[string]any{
				"routeMap": map[string]any{"oversized": strings.Repeat("x", 300<<10)},
			},
		},
		presentation.SurfaceCapabilities{},
		1,
	)
	if err != nil || !document.UseFallback ||
		!strings.Contains(document.FallbackReason, presentation.ErrInvalidData.Error()) {
		t.Fatalf("oversized data document=%#v err=%v", document, err)
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
				presentation.NewOfficialNodeDataPolicies(),
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
		{
			name: "fallback binding outside input schema",
			mutate: func(template *presentation.Template) {
				template.FallbackMarkdownBinding = "$.missingAnswer"
			},
		},
		{
			name: "semantic data policy ref is invalid",
			mutate: func(template *presentation.Template) {
				template.Nodes[0].DataPolicyRef = "https://adapter.example"
			},
		},
		{
			name: "route map without data policy",
			mutate: func(template *presentation.Template) {
				template.Nodes[0].Kind = generated.AssistantPresentationNodeKindRouteMap
			},
		},
		{
			name: "media dimensions are absent",
			mutate: func(template *presentation.Template) {
				template.Nodes[0].Media.Width = 0
			},
		},
		{
			name: "responsive variant id is duplicated",
			mutate: func(template *presentation.Template) {
				template.ResponsiveVariants = append(
					template.ResponsiveVariants,
					template.ResponsiveVariants[0],
				)
			},
		},
		{
			name: "responsive variant requires an absent node kind",
			mutate: func(template *presentation.Template) {
				template.ResponsiveVariants[0].RequiredNodeKinds = append(
					template.ResponsiveVariants[0].RequiredNodeKinds,
					generated.AssistantPresentationNodeKindRouteMap,
				)
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

func TestAdaptivePresentationRejectsTamperedBoundActionIntent(t *testing.T) {
	template := validBoundActionTemplate()
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		nil,
		presentation.NewOfficialNodeDataPolicies(),
	)
	validAction := map[string]any{
		"intentId":             "continue_tool_use",
		"operation":            "ContinueAssistantToolUse",
		"objectTypeRef":        "assistant_tool_use",
		"objectId":             "tu_01KZ1AAX6373K6ETA4ETAXPYW1",
		"payload":              map[string]any{"decision": "approved"},
		"requiresConfirmation": true,
	}
	for _, test := range []struct {
		name   string
		mutate func(map[string]any)
	}{
		{
			name: "operation outside template allowlist",
			mutate: func(action map[string]any) {
				action["operation"] = "DeleteAccount"
			},
		},
		{
			name: "unsafe callback payload",
			mutate: func(action map[string]any) {
				action["payload"] = map[string]any{"callbackUrl": "https://evil.example"}
			},
		},
		{
			name: "unknown action field",
			mutate: func(action map[string]any) {
				action["route"] = "/admin"
			},
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			action := cloneTestObject(validAction)
			test.mutate(action)
			document, resolveErr := resolver.Resolve(
				t.Context(),
				"calendar_task",
				presentation.Selection{
					TemplateRef: presentation.TemplateRef(template),
					Data:        map[string]any{"action": action},
				},
				presentation.SurfaceCapabilities{
					SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
						generated.AssistantPresentationNodeKindActionGroup: true,
					},
					ViewportClass: "standard",
					Density:       generated.AssistantPresentationDensityStandard,
				},
				1,
			)
			if resolveErr != nil || !document.UseFallback || document.FallbackReason == "" {
				t.Fatalf("tampered action document=%#v err=%v", document, resolveErr)
			}
		})
	}
}

func TestAdaptivePresentationBindsOnlyTypedMediaReferences(t *testing.T) {
	template := validBoundMediaTemplate()
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		nil,
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
	media := map[string]any{
		"mediaAssetId":  "asset_west_lake_01",
		"alt":           "西湖边的行程随拍",
		"width":         1600,
		"height":        900,
		"provenanceRef": "travel_moment_01",
	}
	document, resolveErr := resolver.Resolve(
		t.Context(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data:        map[string]any{"media": media},
		},
		presentation.SurfaceCapabilities{
			SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
				generated.AssistantPresentationNodeKindMedia: true,
			},
			ViewportClass: "standard",
			Density:       generated.AssistantPresentationDensityStandard,
		},
		1,
	)
	if resolveErr != nil || document.UseFallback || len(document.Nodes) != 1 ||
		document.Nodes[0].Media == nil ||
		document.Nodes[0].Media.MediaAssetID != "asset_west_lake_01" {
		t.Fatalf("bound media document=%#v err=%v", document, resolveErr)
	}

	tampered := cloneTestObject(media)
	tampered["cdnUrl"] = "https://untrusted.example/media.jpg"
	document, resolveErr = resolver.Resolve(
		t.Context(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data:        map[string]any{"media": tampered},
		},
		presentation.SurfaceCapabilities{
			SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
				generated.AssistantPresentationNodeKindMedia: true,
			},
			ViewportClass: "standard",
			Density:       generated.AssistantPresentationDensityStandard,
		},
		1,
	)
	if resolveErr != nil || !document.UseFallback || document.FallbackReason == "" {
		t.Fatalf("tampered media document=%#v err=%v", document, resolveErr)
	}
}

func TestAdaptivePresentationRouteMapPolicyAcceptsOnlyCanonicalSemanticData(t *testing.T) {
	canonicalData := routeMapData()
	routeMap, err := presentation.NewOfficialNodeDataPolicies().ResolveNodeData(
		t.Context(),
		presentation.CanonicalRouteMapDataPolicyRef,
		generated.AssistantPresentationNodeKindRouteMap,
		canonicalData,
	)
	if err != nil {
		t.Fatalf("canonical semantic route_map was rejected: %v", err)
	}
	for _, forbidden := range []string{"url", "provider", "coordinates", "routeSegments"} {
		if _, leaked := routeMap[forbidden]; leaked {
			t.Fatalf("route_map leaked forbidden field %q: %#v", forbidden, routeMap)
		}
	}
	canonicalData["routeSegments"] = []any{}
	if _, err := presentation.NewOfficialNodeDataPolicies().ResolveNodeData(
		t.Context(),
		presentation.CanonicalRouteMapDataPolicyRef,
		generated.AssistantPresentationNodeKindRouteMap,
		canonicalData,
	); err == nil {
		t.Fatal("generic Presentation accepted a vertical TripMapView field")
	}
}

func TestAdaptivePresentationRouteMapAcceptsOnlyCanonicalPlaceAndSegmentReferences(t *testing.T) {
	template := validRouteMapTemplate()
	catalog, err := presentation.NewCatalog([]presentation.Template{template})
	if err != nil {
		t.Fatalf("NewCatalog() error = %v", err)
	}
	resolver := presentation.NewResolver(
		catalog,
		actionPolicyStub{},
		mediaPolicyStub{},
		presentation.NewOfficialNodeDataPolicies(),
	)
	capabilities := presentation.SurfaceCapabilities{
		SupportedNodeKinds: map[generated.AssistantPresentationNodeKind]bool{
			generated.AssistantPresentationNodeKindRouteMap: true,
		},
		ViewportClass: "narrow",
		Density:       generated.AssistantPresentationDensityCompact,
	}
	valid := routeMapData()
	document, err := resolver.Resolve(
		context.Background(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data:        map[string]any{"routeMap": valid},
		},
		capabilities,
		1,
	)
	if err != nil || document.UseFallback || len(document.Nodes) != 1 {
		t.Fatalf("valid route_map document=%#v err=%v", document, err)
	}

	invalid := routeMapData()
	invalid["providerUrl"] = "https://maps.example/route"
	document, err = resolver.Resolve(
		context.Background(),
		"travel_companion",
		presentation.Selection{
			TemplateRef: presentation.TemplateRef(template),
			Data:        map[string]any{"routeMap": invalid},
		},
		capabilities,
		2,
	)
	if err != nil || !document.UseFallback || document.FallbackReason == "" {
		t.Fatalf("unsafe route_map document=%#v err=%v", document, err)
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

func validRouteMapTemplate() presentation.Template {
	return presentation.Template{
		TemplateID: "travel.route_map",
		SkillID:    "travel_companion",
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"routeMap": map[string]any{"type": "object"},
			},
			"required": []any{"routeMap"},
		},
		RootNodeID: "route",
		Nodes: []presentation.Node{{
			NodeID:        "route",
			Kind:          generated.AssistantPresentationNodeKindRouteMap,
			DataPolicyRef: presentation.CanonicalRouteMapDataPolicyRef,
			Binding: map[string]string{
				"data": "$.routeMap",
			},
			Style: presentation.Style{
				Tone:     generated.AssistantPresentationToneNeutral,
				Density:  generated.AssistantPresentationDensityStandard,
				Emphasis: "normal", Variant: "standard", Alignment: "start",
				SpacingRole: "related", ResponsiveSpan: 1,
			},
		}},
		FallbackMarkdown: "## 行程路线\n请按地点顺序查看路线。",
		AssetDigest:      "sha256:" + strings.Repeat("c", 64),
	}
}

func validBoundActionTemplate() presentation.Template {
	return presentation.Template{
		TemplateID: "assistant.tool_confirmation",
		SkillID:    presentation.PlatformTemplateSkillID,
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"action": map[string]any{"type": "object"},
			},
			"required": []any{"action"},
		},
		RootNodeID: "action",
		Nodes: []presentation.Node{{
			NodeID: "action",
			Kind:   generated.AssistantPresentationNodeKindActionGroup,
			Binding: map[string]string{
				"action": "$.action",
			},
			Style: presentation.Style{
				Tone:           generated.AssistantPresentationToneNeutral,
				Density:        generated.AssistantPresentationDensityStandard,
				Emphasis:       "normal",
				Variant:        "standard",
				Alignment:      "start",
				SpacingRole:    "related",
				ResponsiveSpan: 1,
			},
		}},
		AllowedActionIntents: []string{"ContinueAssistantToolUse"},
		FallbackMarkdown:     "需要确认后才能执行此操作。",
		AssetDigest:          "sha256:" + strings.Repeat("d", 64),
	}
}

func validBoundMediaTemplate() presentation.Template {
	return presentation.Template{
		TemplateID: "travel.media.grounded",
		SkillID:    "travel_companion",
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"media": map[string]any{"type": "object"},
			},
			"required": []any{"media"},
		},
		RootNodeID: "media",
		Nodes: []presentation.Node{{
			NodeID: "media",
			Kind:   generated.AssistantPresentationNodeKindMedia,
			Binding: map[string]string{
				"media": "$.media",
			},
			Style: presentation.Style{
				Tone:           generated.AssistantPresentationToneNeutral,
				Density:        generated.AssistantPresentationDensityStandard,
				Emphasis:       "normal",
				Variant:        "standard",
				Alignment:      "start",
				SpacingRole:    "related",
				ResponsiveSpan: 12,
			},
		}},
		FallbackMarkdown: "媒体暂时无法展示。",
		AssetDigest:      "sha256:" + strings.Repeat("e", 64),
	}
}

func cloneTestObject(value map[string]any) map[string]any {
	result := make(map[string]any, len(value))
	for key, item := range value {
		if child, ok := item.(map[string]any); ok {
			result[key] = cloneTestObject(child)
			continue
		}
		result[key] = item
	}
	return result
}

func routeMapData() map[string]any {
	return map[string]any{
		"tripId":       "trip_1",
		"revisionId":   "trv_2",
		"sourceDigest": "sha256:" + strings.Repeat("b", 64),
		"stops": []any{
			map[string]any{
				"placeRef": map[string]any{"objectTypeRef": "entity.Place", "objectId": "place_west_lake"},
				"dayIndex": 0, "order": 0, "itemId": "item_west_lake", "title": "西湖",
			},
			map[string]any{
				"placeRef": map[string]any{"objectTypeRef": "entity.Place", "objectId": "place_hefang"},
				"dayIndex": 0, "order": 1, "itemId": "item_hefang", "title": "河坊街",
			},
		},
		"segments": []any{
			map[string]any{
				"fromPlaceRef": map[string]any{"objectTypeRef": "entity.Place", "objectId": "place_west_lake"},
				"toPlaceRef":   map[string]any{"objectTypeRef": "entity.Place", "objectId": "place_hefang"},
				"modeToken":    "walk", "order": 0,
			},
		},
		"markers": []any{
			map[string]any{
				"momentId": "tmo_1",
				"placeRef": map[string]any{"objectTypeRef": "entity.Place", "objectId": "place_west_lake"},
				"dayIndex": 0, "itemId": "item_west_lake",
			},
		},
	}
}

func allPresentationKinds() map[generated.AssistantPresentationNodeKind]bool {
	return map[generated.AssistantPresentationNodeKind]bool{
		generated.AssistantPresentationNodeKindCard:    true,
		generated.AssistantPresentationNodeKindText:    true,
		generated.AssistantPresentationNodeKindCallout: true,
	}
}

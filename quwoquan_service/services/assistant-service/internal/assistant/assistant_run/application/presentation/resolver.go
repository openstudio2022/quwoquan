package presentation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"regexp"
	"strings"
	"time"

	"github.com/santhosh-tekuri/jsonschema/v6"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Resolver struct {
	catalog      *Catalog
	actionPolicy ActionPolicy
	mediaPolicy  MediaPolicy
	now          func() time.Time
}

func NewResolver(
	catalog *Catalog,
	actionPolicy ActionPolicy,
	mediaPolicy MediaPolicy,
) *Resolver {
	if catalog == nil {
		panic("assistant presentation catalog is required")
	}
	return &Resolver{
		catalog:      catalog,
		actionPolicy: actionPolicy,
		mediaPolicy:  mediaPolicy,
		now:          time.Now,
	}
}

func (r *Resolver) Resolve(
	ctx context.Context,
	skillID string,
	selection Selection,
	capabilities SurfaceCapabilities,
	revision int64,
) (Document, error) {
	template, err := r.catalog.Resolve(selection.TemplateRef, skillID)
	if err != nil {
		return Document{}, err
	}
	document := fallbackDocument(template, selection.TemplateRef, revision, r.now().UTC())
	if err := validateInputData(template, selection.Data); err != nil {
		document.FallbackReason = err.Error()
		return document, nil
	}
	nodes, err := resolveNodes(template, selection.Data)
	if err != nil {
		document.FallbackReason = err.Error()
		return document, nil
	}
	allowedActions := make(map[string]bool, len(template.AllowedActionIntents))
	for _, operation := range template.AllowedActionIntents {
		allowedActions[operation] = true
	}
	for index := range nodes {
		node := &nodes[index]
		if node.Kind == generated.AssistantPresentationNodeKindRouteMap {
			if err := validateRouteMapData(node.Data); err != nil {
				normalized, valid := RouteMapFromTravelProjection(node.Data)
				if !valid {
					document.FallbackReason = err.Error()
					return document, nil
				}
				node.Data = normalized
			}
		}
		if node.Action != nil {
			if err := validateActionIntent(*node.Action, allowedActions); err != nil {
				document.FallbackReason = ErrActionRejected.Error()
				return document, nil
			}
		}
	}
	if !supportsNodes(nodes, capabilities.SupportedNodeKinds) {
		document.FallbackReason = "surface does not support required semantic nodes"
		return document, nil
	}
	for _, node := range nodes {
		if node.Action != nil {
			if r.actionPolicy == nil || r.actionPolicy.ValidateAction(ctx, skillID, *node.Action) != nil {
				document.FallbackReason = ErrActionRejected.Error()
				return document, nil
			}
		}
		if node.Media != nil {
			if r.mediaPolicy == nil || r.mediaPolicy.ValidateMedia(ctx, *node.Media) != nil {
				document.FallbackReason = ErrMediaRejected.Error()
				return document, nil
			}
		}
	}
	digest, err := canonicalDataDigest(selection.Data)
	if err != nil {
		document.FallbackReason = ErrInvalidData.Error()
		return document, nil
	}
	document.Nodes = nodes
	document.DataDigest = digest
	document.SelectedVariant = selectVariant(template, capabilities)
	document.UseFallback = false
	document.FallbackReason = ""
	return document, nil
}

func validateInputData(template Template, data map[string]any) error {
	compiler := jsonschema.NewCompiler()
	const location = "mem://assistant-presentation/input.json"
	if err := compiler.AddResource(location, template.InputSchema); err != nil {
		return fmt.Errorf("%w: compile resource: %v", ErrInvalidData, err)
	}
	schema, err := compiler.Compile(location)
	if err != nil {
		return fmt.Errorf("%w: compile schema: %v", ErrInvalidData, err)
	}
	if err := schema.Validate(data); err != nil {
		return fmt.Errorf("%w: %v", ErrInvalidData, err)
	}
	return nil
}

func resolveNodes(template Template, data map[string]any) ([]Node, error) {
	resolved := cloneNodes(template.Nodes)
	visible := make(map[string]bool, len(resolved))
	for index := range resolved {
		visible[resolved[index].NodeID] = true
		for field, path := range resolved[index].Binding {
			value, ok := lookupPath(data, path)
			if !ok {
				return nil, ErrInvalidData
			}
			switch field {
			case "title":
				text, ok := value.(string)
				if !ok || len([]rune(text)) > 512 || rawHTMLPattern.MatchString(text) || unsafeURIPattern.MatchString(text) {
					return nil, ErrInvalidData
				}
				resolved[index].Title = text
			case "body":
				text, ok := value.(string)
				if !ok || len([]rune(text)) > 20_000 || rawHTMLPattern.MatchString(text) || unsafeURIPattern.MatchString(text) {
					return nil, ErrInvalidData
				}
				resolved[index].Body = text
			case "data":
				object, ok := value.(map[string]any)
				if !ok || len(object) > 128 {
					return nil, ErrInvalidData
				}
				resolved[index].Data = cloneMap(object)
			case "visible":
				show, ok := value.(bool)
				if !ok {
					return nil, ErrInvalidData
				}
				visible[resolved[index].NodeID] = show
			case "action":
				action, ok := actionIntentFrom(value)
				if !ok {
					return nil, ErrInvalidData
				}
				resolved[index].Action = &action
			}
		}
		resolved[index].Binding = nil
	}
	for {
		changed := false
		for _, node := range resolved {
			if node.ParentNodeID != "" && !visible[node.ParentNodeID] && visible[node.NodeID] {
				visible[node.NodeID] = false
				changed = true
			}
		}
		if !changed {
			break
		}
	}
	result := make([]Node, 0, len(resolved))
	for _, node := range resolved {
		if visible[node.NodeID] {
			result = append(result, node)
		}
	}
	if len(result) == 0 {
		return nil, ErrInvalidData
	}
	return result, nil
}

func actionIntentFrom(value any) (ActionIntent, bool) {
	object, ok := value.(map[string]any)
	if !ok {
		return ActionIntent{}, false
	}
	raw, err := json.Marshal(object)
	if err != nil || len(raw) > maxPayloadBytes {
		return ActionIntent{}, false
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	var action ActionIntent
	if err := decoder.Decode(&action); err != nil {
		return ActionIntent{}, false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return ActionIntent{}, false
	}
	return action, true
}

func lookupPath(data map[string]any, path string) (any, bool) {
	parts := strings.Split(strings.TrimPrefix(path, "$."), ".")
	var current any = data
	for _, part := range parts {
		object, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		current, ok = object[part]
		if !ok {
			return nil, false
		}
	}
	return current, true
}

func supportsNodes(
	nodes []Node,
	supported map[generated.AssistantPresentationNodeKind]bool,
) bool {
	for _, node := range nodes {
		if !supported[node.Kind] {
			return false
		}
	}
	return true
}

func selectVariant(template Template, capabilities SurfaceCapabilities) string {
	for _, variant := range template.ResponsiveVariants {
		if variant.ViewportClass != "any" && variant.ViewportClass != capabilities.ViewportClass {
			continue
		}
		if variant.Density != capabilities.Density {
			continue
		}
		allSupported := true
		for _, kind := range variant.RequiredNodeKinds {
			if !capabilities.SupportedNodeKinds[kind] {
				allSupported = false
				break
			}
		}
		if allSupported {
			return variant.VariantID
		}
	}
	return "standard"
}

func fallbackDocument(template Template, ref string, revision int64, now time.Time) Document {
	return Document{
		TemplateRef:       ref,
		TemplateDigest:    template.AssetDigest,
		Revision:          revision,
		RootNodeID:        template.RootNodeID,
		SelectedVariant:   "standard",
		FallbackMarkdown:  template.FallbackMarkdown,
		FallbackPlainText: markdownPlainText(template.FallbackMarkdown),
		CommittedAt:       now,
		UseFallback:       true,
		FallbackReason:    "presentation validation failed",
	}
}

func canonicalDataDigest(data map[string]any) (string, error) {
	raw, err := json.Marshal(data)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

var markdownMarker = regexp.MustCompile(`[*_~#>` + "`" + `\[\]()]`)

func markdownPlainText(value string) string {
	return strings.TrimSpace(markdownMarker.ReplaceAllString(value, ""))
}

func cloneNodes(values []Node) []Node {
	result := make([]Node, len(values))
	for index, node := range values {
		result[index] = node
		result[index].Data = cloneMap(node.Data)
		result[index].Binding = make(map[string]string, len(node.Binding))
		for key, value := range node.Binding {
			result[index].Binding[key] = value
		}
		if node.Media != nil {
			media := *node.Media
			result[index].Media = &media
		}
		if node.Action != nil {
			action := *node.Action
			action.Payload = cloneMap(node.Action.Payload)
			result[index].Action = &action
		}
	}
	return result
}

func cloneMap(value map[string]any) map[string]any {
	if value == nil {
		return nil
	}
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}

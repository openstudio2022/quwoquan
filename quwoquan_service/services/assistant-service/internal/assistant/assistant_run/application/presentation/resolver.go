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
	dataPolicy   NodeDataPolicy
	now          func() time.Time
}

func NewResolver(
	catalog *Catalog,
	actionPolicy ActionPolicy,
	mediaPolicy MediaPolicy,
	dataPolicy NodeDataPolicy,
) *Resolver {
	if catalog == nil {
		panic("assistant presentation catalog is required")
	}
	return &Resolver{
		catalog:      catalog,
		actionPolicy: actionPolicy,
		mediaPolicy:  mediaPolicy,
		dataPolicy:   dataPolicy,
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
	document := fallbackDocument(
		template,
		selection.TemplateRef,
		selection.Data,
		revision,
		r.now().UTC(),
	)
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
		if strings.TrimSpace(node.DataPolicyRef) != "" {
			if r.dataPolicy == nil {
				document.FallbackReason = ErrDataPolicyRejected.Error()
				return document, nil
			}
			normalized, err := r.dataPolicy.ResolveNodeData(
				ctx,
				node.DataPolicyRef,
				node.Kind,
				node.Data,
			)
			if err != nil {
				document.FallbackReason = ErrDataPolicyRejected.Error()
				return document, nil
			}
			node.Data = normalized
			node.DataPolicyRef = ""
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
	variant, compatible := selectVariant(template, capabilities)
	if !compatible {
		document.FallbackReason = "surface does not support a compatible presentation variant"
		return document, nil
	}
	document.Nodes = nodes
	document.DataDigest = digest
	document.SelectedVariant = variant
	document.UseFallback = false
	document.FallbackReason = ""
	return document, nil
}

func validateInputData(template Template, data map[string]any) error {
	raw, err := json.Marshal(data)
	if err != nil || len(raw) > maxDataBytes {
		return fmt.Errorf("%w: structured data budget", ErrInvalidData)
	}
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
			case "media":
				media, ok := mediaRefFrom(value)
				if !ok {
					return nil, ErrInvalidData
				}
				resolved[index].Media = &media
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

func mediaRefFrom(value any) (MediaRef, bool) {
	object, ok := value.(map[string]any)
	if !ok {
		return MediaRef{}, false
	}
	raw, err := json.Marshal(object)
	if err != nil || len(raw) > maxPayloadBytes {
		return MediaRef{}, false
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	var media MediaRef
	if err := decoder.Decode(&media); err != nil {
		return MediaRef{}, false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return MediaRef{}, false
	}
	if !identifierPattern.MatchString(strings.TrimSpace(media.MediaAssetID)) ||
		!identifierPattern.MatchString(strings.TrimSpace(media.ProvenanceRef)) ||
		strings.TrimSpace(media.Alt) == "" || len([]rune(media.Alt)) > 512 ||
		rawHTMLPattern.MatchString(media.Alt) || unsafeURIPattern.MatchString(media.Alt) ||
		media.Width <= 0 || media.Height <= 0 {
		return MediaRef{}, false
	}
	return media, true
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

func selectVariant(
	template Template,
	capabilities SurfaceCapabilities,
) (string, bool) {
	if len(template.ResponsiveVariants) == 0 {
		return "standard", true
	}
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
			return variant.VariantID, true
		}
	}
	return "", false
}

func fallbackDocument(
	template Template,
	ref string,
	data map[string]any,
	revision int64,
	now time.Time,
) Document {
	fallbackMarkdown := template.FallbackMarkdown
	if binding := strings.TrimSpace(template.FallbackMarkdownBinding); binding != "" {
		if value, found := lookupPath(data, binding); found {
			if text, valid := safeFallbackMarkdown(value); valid {
				fallbackMarkdown = text
			}
		}
	}
	return Document{
		TemplateRef:       ref,
		TemplateDigest:    template.AssetDigest,
		Revision:          revision,
		RootNodeID:        template.RootNodeID,
		SelectedVariant:   "standard",
		FallbackMarkdown:  fallbackMarkdown,
		FallbackPlainText: markdownPlainText(fallbackMarkdown),
		CommittedAt:       now,
		UseFallback:       true,
		FallbackReason:    "presentation validation failed",
	}
}

func safeFallbackMarkdown(value any) (string, bool) {
	text, ok := value.(string)
	text = strings.TrimSpace(text)
	if !ok || text == "" || len([]rune(text)) > 20_000 ||
		rawHTMLPattern.MatchString(text) || unsafeURIPattern.MatchString(text) {
		return "", false
	}
	return text, true
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
		result[key] = cloneValue(item)
	}
	return result
}

func cloneValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMap(typed)
	case []any:
		result := make([]any, len(typed))
		for index, item := range typed {
			result[index] = cloneValue(item)
		}
		return result
	case []map[string]any:
		result := make([]map[string]any, len(typed))
		for index, item := range typed {
			result[index] = cloneMap(item)
		}
		return result
	default:
		return value
	}
}

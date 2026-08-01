package presentation

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

const (
	maxTemplateNodes = 128
	maxTemplateDepth = 12
	maxPayloadBytes  = 16 << 10
)

var (
	digestPattern     = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	bindingPattern    = regexp.MustCompile(`^\$\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$`)
	identifierPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)
	rawHTMLPattern    = regexp.MustCompile(`(?i)<\s*/?\s*[a-z][^>]*>`)
	unsafeURIPattern  = regexp.MustCompile(`(?i)(?:javascript|data|file):`)
)

func ValidateTemplate(template Template) error {
	if !identifierPattern.MatchString(strings.TrimSpace(template.TemplateID)) ||
		!identifierPattern.MatchString(strings.TrimSpace(template.SkillID)) ||
		!digestPattern.MatchString(strings.TrimSpace(template.AssetDigest)) ||
		strings.TrimSpace(template.RootNodeID) == "" ||
		strings.TrimSpace(template.FallbackMarkdown) == "" ||
		rawHTMLPattern.MatchString(template.FallbackMarkdown) ||
		unsafeURIPattern.MatchString(template.FallbackMarkdown) ||
		len(template.Nodes) == 0 || len(template.Nodes) > maxTemplateNodes {
		return ErrInvalidTemplate
	}
	if template.InputSchema["type"] != "object" || template.InputSchema["additionalProperties"] != false {
		return fmt.Errorf("%w: input schema must be a closed object", ErrInvalidTemplate)
	}
	allowedActions := make(map[string]bool, len(template.AllowedActionIntents))
	for _, operation := range template.AllowedActionIntents {
		if !identifierPattern.MatchString(operation) {
			return ErrInvalidTemplate
		}
		allowedActions[operation] = true
	}
	nodes := make(map[string]Node, len(template.Nodes))
	for _, node := range template.Nodes {
		if !identifierPattern.MatchString(node.NodeID) || node.Order < 0 {
			return ErrInvalidTemplate
		}
		if _, exists := nodes[node.NodeID]; exists {
			return fmt.Errorf("%w: duplicate node %s", ErrInvalidTemplate, node.NodeID)
		}
		if parsed, err := generated.ParseAssistantPresentationNodeKind(node.Kind.WireName()); err != nil || parsed == generated.AssistantPresentationNodeKindUnknown {
			return fmt.Errorf("%w: unknown node kind %s", ErrInvalidTemplate, node.Kind)
		}
		if len([]rune(node.Title)) > 512 || len([]rune(node.Body)) > 20_000 ||
			len(node.Data) > 128 || len(node.Binding) > 32 || rawHTMLPattern.MatchString(node.Body) {
			return fmt.Errorf("%w: node content budget", ErrInvalidTemplate)
		}
		if err := validateStyle(node.Style); err != nil {
			return err
		}
		if err := validateBinding(node.Binding); err != nil {
			return err
		}
		if node.Media != nil {
			if strings.TrimSpace(node.Media.MediaAssetID) == "" || strings.TrimSpace(node.Media.Alt) == "" ||
				strings.TrimSpace(node.Media.ProvenanceRef) == "" || node.Media.Width < 0 || node.Media.Height < 0 {
				return ErrInvalidTemplate
			}
		}
		if node.Action != nil {
			if !allowedActions[node.Action.Operation] || !identifierPattern.MatchString(node.Action.IntentID) ||
				!identifierPattern.MatchString(node.Action.Operation) || unsafeActionPayload(node.Action.Payload) {
				return ErrInvalidTemplate
			}
			raw, err := json.Marshal(node.Action.Payload)
			if err != nil || len(raw) > maxPayloadBytes {
				return ErrInvalidTemplate
			}
		}
		if node.Kind == generated.AssistantPresentationNodeKindIcon {
			icon, _ := node.Data["iconToken"].(string)
			if !allowedIconTokens[icon] {
				return fmt.Errorf("%w: unknown icon token", ErrInvalidTemplate)
			}
		}
		nodes[node.NodeID] = node
	}
	root, ok := nodes[template.RootNodeID]
	if !ok || strings.TrimSpace(root.ParentNodeID) != "" {
		return fmt.Errorf("%w: invalid root node", ErrInvalidTemplate)
	}
	for _, node := range template.Nodes {
		if node.NodeID == template.RootNodeID {
			continue
		}
		if _, ok := nodes[node.ParentNodeID]; !ok {
			return fmt.Errorf("%w: missing parent for %s", ErrInvalidTemplate, node.NodeID)
		}
		if depth, cyclic := nodeDepth(node, nodes); cyclic || depth > maxTemplateDepth {
			return fmt.Errorf("%w: node depth or cycle", ErrInvalidTemplate)
		}
	}
	for _, variant := range template.ResponsiveVariants {
		if !identifierPattern.MatchString(variant.VariantID) || strings.TrimSpace(variant.ViewportClass) == "" {
			return ErrInvalidTemplate
		}
		if _, err := generated.ParseAssistantPresentationDensity(variant.Density.WireName()); err != nil {
			return ErrInvalidTemplate
		}
		for _, kind := range variant.RequiredNodeKinds {
			if parsed, err := generated.ParseAssistantPresentationNodeKind(kind.WireName()); err != nil || parsed == generated.AssistantPresentationNodeKindUnknown {
				return ErrInvalidTemplate
			}
		}
	}
	return nil
}

func validateStyle(style Style) error {
	if _, err := generated.ParseAssistantPresentationTone(style.Tone.WireName()); err != nil {
		return ErrInvalidTemplate
	}
	if _, err := generated.ParseAssistantPresentationDensity(style.Density.WireName()); err != nil {
		return ErrInvalidTemplate
	}
	if !allowedStyleToken(style.Emphasis, "normal", "subtle", "strong") ||
		!allowedStyleToken(style.Variant, "standard", "outlined", "filled", "hero") ||
		!allowedStyleToken(style.Alignment, "start", "center", "end", "space_between") ||
		!allowedStyleToken(style.SpacingRole, "none", "related", "section", "screen") ||
		style.AspectRatio < 0 || style.AspectRatio > 10 ||
		style.ResponsiveSpan < 1 || style.ResponsiveSpan > 12 {
		return ErrInvalidTemplate
	}
	return nil
}

func validateBinding(binding map[string]string) error {
	for field, path := range binding {
		switch field {
		case "title", "body", "data", "visible":
		default:
			return ErrInvalidTemplate
		}
		if !bindingPattern.MatchString(path) {
			return ErrInvalidTemplate
		}
	}
	return nil
}

func nodeDepth(node Node, nodes map[string]Node) (int, bool) {
	depth := 1
	seen := map[string]bool{node.NodeID: true}
	for node.ParentNodeID != "" {
		if seen[node.ParentNodeID] {
			return depth, true
		}
		seen[node.ParentNodeID] = true
		node = nodes[node.ParentNodeID]
		depth++
	}
	return depth, false
}

func unsafeActionPayload(payload map[string]any) bool {
	for key, value := range payload {
		normalized := strings.ToLower(strings.ReplaceAll(key, "_", ""))
		switch normalized {
		case "url", "route", "callback", "callbackurl", "javascript", "script", "authorization", "cookie":
			return true
		}
		if child, ok := value.(map[string]any); ok && unsafeActionPayload(child) {
			return true
		}
	}
	return false
}

func allowedStyleToken(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}

var allowedIconTokens = map[string]bool{
	"calendar": true,
	"clock":    true,
	"location": true,
	"weather":  true,
	"warning":  true,
	"check":    true,
	"info":     true,
	"travel":   true,
	"source":   true,
	"image":    true,
}

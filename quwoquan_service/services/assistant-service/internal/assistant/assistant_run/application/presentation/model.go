// Package presentation resolves immutable Skill templates into a bounded
// semantic component tree. It never accepts Flutter, HTML, CSS or executable
// style payloads.
package presentation

import (
	"context"
	"errors"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Style struct {
	Tone           generated.AssistantPresentationTone    `json:"tone"`
	Density        generated.AssistantPresentationDensity `json:"density"`
	Emphasis       string                                 `json:"emphasis"`
	Variant        string                                 `json:"variant"`
	Alignment      string                                 `json:"alignment"`
	SpacingRole    string                                 `json:"spacingRole"`
	AspectRatio    float64                                `json:"aspectRatio"`
	ResponsiveSpan int                                    `json:"responsiveSpan"`
}

type MediaRef struct {
	MediaAssetID  string `json:"mediaAssetId"`
	Alt           string `json:"alt"`
	Width         int    `json:"width"`
	Height        int    `json:"height"`
	ProvenanceRef string `json:"provenanceRef"`
}

type ActionIntent struct {
	IntentID             string         `json:"intentId"`
	Operation            string         `json:"operation"`
	ObjectTypeRef        string         `json:"objectTypeRef"`
	ObjectID             string         `json:"objectId"`
	Payload              map[string]any `json:"payload"`
	RequiresConfirmation bool           `json:"requiresConfirmation"`
}

type Accessibility struct {
	SemanticLabel        string `json:"semanticLabel"`
	SemanticHint         string `json:"semanticHint"`
	ExcludeFromSemantics bool   `json:"excludeFromSemantics"`
}

type Node struct {
	NodeID        string                                  `json:"nodeId"`
	ParentNodeID  string                                  `json:"parentNodeId"`
	Order         int                                     `json:"order"`
	Kind          generated.AssistantPresentationNodeKind `json:"kind"`
	Title         string                                  `json:"title"`
	Body          string                                  `json:"body"`
	Data          map[string]any                          `json:"data"`
	Binding       map[string]string                       `json:"binding"`
	DataPolicyRef string                                  `json:"dataPolicyRef,omitempty"`
	Style         Style                                   `json:"style"`
	Media         *MediaRef                               `json:"media,omitempty"`
	Action        *ActionIntent                           `json:"action,omitempty"`
	Accessibility Accessibility                           `json:"accessibility"`
}

type ResponsiveVariant struct {
	VariantID         string                                    `json:"variantId"`
	RequiredNodeKinds []generated.AssistantPresentationNodeKind `json:"requiredNodeKinds"`
	ViewportClass     string                                    `json:"viewportClass"`
	Density           generated.AssistantPresentationDensity    `json:"density"`
}

type Template struct {
	TemplateID              string              `json:"templateId"`
	SkillID                 string              `json:"skillId"`
	InputSchema             map[string]any      `json:"inputSchema"`
	RootNodeID              string              `json:"rootNodeId"`
	Nodes                   []Node              `json:"nodes"`
	ResponsiveVariants      []ResponsiveVariant `json:"responsiveVariants"`
	AllowedActionIntents    []string            `json:"allowedActionIntents"`
	FallbackMarkdown        string              `json:"fallbackMarkdown"`
	FallbackMarkdownBinding string              `json:"fallbackMarkdownBinding,omitempty"`
	Accessibility           map[string]any      `json:"accessibility"`
	AssetDigest             string              `json:"assetDigest"`
}

type Selection struct {
	TemplateRef string         `json:"templateRef"`
	Data        map[string]any `json:"data"`
}

type SurfaceCapabilities struct {
	SupportedNodeKinds     map[generated.AssistantPresentationNodeKind]bool `json:"supportedNodeKinds"`
	SupportedActionIntents map[string]bool                                  `json:"supportedActionIntents"`
	ViewportClass          string                                           `json:"viewportClass"`
	Density                generated.AssistantPresentationDensity           `json:"density"`
}

type Document struct {
	TemplateRef       string    `json:"templateRef"`
	TemplateDigest    string    `json:"templateDigest"`
	Revision          int64     `json:"revision"`
	RootNodeID        string    `json:"rootNodeId"`
	Nodes             []Node    `json:"nodes"`
	DataDigest        string    `json:"dataDigest"`
	SelectedVariant   string    `json:"selectedVariant"`
	FallbackMarkdown  string    `json:"fallbackMarkdown"`
	FallbackPlainText string    `json:"fallbackPlainText"`
	CommittedAt       time.Time `json:"committedAt"`
	UseFallback       bool      `json:"-"`
	FallbackReason    string    `json:"-"`
}

type ActionPolicy interface {
	ValidateAction(context.Context, string, ActionIntent) error
}

type MediaPolicy interface {
	ValidateMedia(context.Context, MediaRef) error
}

// NodeDataPolicy is the dependency-inversion boundary for semantic node data.
// The immutable template selects a policy by reference; Resolver never knows
// about a vertical domain or rewrites its read model itself.
type NodeDataPolicy interface {
	ResolveNodeData(
		context.Context,
		string,
		generated.AssistantPresentationNodeKind,
		map[string]any,
	) (map[string]any, error)
}

var (
	ErrInvalidTemplate     = errors.New("invalid assistant presentation template")
	ErrTemplateUnavailable = errors.New("assistant presentation template unavailable")
	ErrInvalidData         = errors.New("invalid assistant presentation data")
	ErrActionRejected      = errors.New("assistant presentation action rejected")
	ErrMediaRejected       = errors.New("assistant presentation media rejected")
	ErrDataPolicyRejected  = errors.New("assistant presentation data policy rejected")
)

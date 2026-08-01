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
	Tone           generated.AssistantPresentationTone
	Density        generated.AssistantPresentationDensity
	Emphasis       string
	Variant        string
	Alignment      string
	SpacingRole    string
	AspectRatio    float64
	ResponsiveSpan int
}

type MediaRef struct {
	MediaAssetID  string
	Alt           string
	Width         int
	Height        int
	ProvenanceRef string
}

type ActionIntent struct {
	IntentID             string
	Operation            string
	ObjectTypeRef        string
	ObjectID             string
	Payload              map[string]any
	RequiresConfirmation bool
}

type Accessibility struct {
	SemanticLabel        string
	SemanticHint         string
	ExcludeFromSemantics bool
}

type Node struct {
	NodeID        string
	ParentNodeID  string
	Order         int
	Kind          generated.AssistantPresentationNodeKind
	Title         string
	Body          string
	Data          map[string]any
	Binding       map[string]string
	Style         Style
	Media         *MediaRef
	Action        *ActionIntent
	Accessibility Accessibility
}

type ResponsiveVariant struct {
	VariantID         string
	RequiredNodeKinds []generated.AssistantPresentationNodeKind
	ViewportClass     string
	Density           generated.AssistantPresentationDensity
}

type Template struct {
	TemplateID           string
	SkillID              string
	InputSchema          map[string]any
	RootNodeID           string
	Nodes                []Node
	ResponsiveVariants   []ResponsiveVariant
	AllowedActionIntents []string
	FallbackMarkdown     string
	Accessibility        map[string]any
	AssetDigest          string
}

type Selection struct {
	TemplateRef string
	Data        map[string]any
}

type SurfaceCapabilities struct {
	SupportedNodeKinds map[generated.AssistantPresentationNodeKind]bool
	ViewportClass      string
	Density            generated.AssistantPresentationDensity
}

type Document struct {
	TemplateRef       string
	TemplateDigest    string
	Revision          int64
	RootNodeID        string
	Nodes             []Node
	DataDigest        string
	SelectedVariant   string
	FallbackMarkdown  string
	FallbackPlainText string
	CommittedAt       time.Time
	UseFallback       bool
	FallbackReason    string
}

type ActionPolicy interface {
	ValidateAction(context.Context, string, ActionIntent) error
}

type MediaPolicy interface {
	ValidateMedia(context.Context, MediaRef) error
}

var (
	ErrInvalidTemplate     = errors.New("invalid assistant presentation template")
	ErrTemplateUnavailable = errors.New("assistant presentation template unavailable")
	ErrInvalidData         = errors.New("invalid assistant presentation data")
	ErrActionRejected      = errors.New("assistant presentation action rejected")
	ErrMediaRejected       = errors.New("assistant presentation media rejected")
)

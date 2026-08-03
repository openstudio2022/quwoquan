package application

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var (
	ErrIntersectionEvidenceNotFound    = errors.New("authorized intersection evidence not found")
	ErrIntersectionEvidenceUnavailable = errors.New(
		"authorized intersection evidence unavailable",
	)
)

type IntersectionEvidenceRef struct {
	IntersectionID string `json:"intersectionId"`
	EvidenceID     string `json:"evidenceId"`
	SourceRef      string `json:"sourceRef"`
	ObjectTypeRef  string `json:"objectTypeRef"`
	ObjectID       string `json:"objectId"`
}

type AuthorizedIntersectionEvidence struct {
	IntersectionID string    `json:"intersectionId"`
	EvidenceID     string    `json:"evidenceId"`
	SourceRef      string    `json:"sourceRef"`
	ObjectTypeRef  string    `json:"objectTypeRef"`
	ObjectID       string    `json:"objectId"`
	PrimaryText    string    `json:"primaryText"`
	Dimension      string    `json:"dimension,omitempty"`
	VerifiedAt     time.Time `json:"verifiedAt"`
}

type CurrentPageContextReader interface {
	CurrentPageContext(context.Context, string) (map[string]any, bool, error)
}

type CurrentPageContextReaderFunc func(
	context.Context,
	string,
) (map[string]any, bool, error)

func (read CurrentPageContextReaderFunc) CurrentPageContext(
	ctx context.Context,
	accountID string,
) (map[string]any, bool, error) {
	return read(ctx, accountID)
}

type IntersectionEvidenceAuthorizer interface {
	AuthorizeIntersectionEvidence(
		context.Context,
		string,
		[]IntersectionEvidenceRef,
	) ([]AuthorizedIntersectionEvidence, error)
}

type IntersectionEvidenceAuthorizerFunc func(
	context.Context,
	string,
	[]IntersectionEvidenceRef,
) ([]AuthorizedIntersectionEvidence, error)

func (authorize IntersectionEvidenceAuthorizerFunc) AuthorizeIntersectionEvidence(
	ctx context.Context,
	personaID string,
	references []IntersectionEvidenceRef,
) ([]AuthorizedIntersectionEvidence, error) {
	return authorize(ctx, personaID, references)
}

// ContextResolver is the single AssistantRun ingress policy for contextual
// facts. It overlays the object-owned PageContext snapshot and replaces client
// intersection references with facts re-authorized for the trusted persona.
type ContextResolver struct {
	pages    CurrentPageContextReader
	evidence IntersectionEvidenceAuthorizer
}

func NewContextResolver(
	pages CurrentPageContextReader,
	evidence IntersectionEvidenceAuthorizer,
) *ContextResolver {
	return &ContextResolver{pages: pages, evidence: evidence}
}

func (resolver *ContextResolver) Resolve(
	ctx context.Context,
	accountID string,
	personaID string,
	requested map[string]any,
) (map[string]any, error) {
	resolved, err := cloneJSONMap(requested)
	if err != nil {
		return nil, err
	}
	if resolved == nil {
		resolved = map[string]any{}
	}
	// Page context is object-owned runtime state. Client-provided values must
	// never survive when the canonical reader is unavailable or has no current
	// snapshot, otherwise a shared-surface run could be grounded with spoofed
	// private objects or consent facts.
	for _, key := range []string{
		"capturedAt", "pageType", "pageObjects", "userActions", "consentMatrix",
	} {
		delete(resolved, key)
	}
	if resolver != nil && resolver.pages != nil {
		current, found, readErr := resolver.pages.CurrentPageContext(
			ctx,
			strings.TrimSpace(accountID),
		)
		if readErr != nil {
			return nil, readErr
		}
		if found {
			for _, key := range []string{
				"capturedAt", "pageType", "pageObjects", "userActions", "consentMatrix",
			} {
				if value, ok := current[key]; ok {
					resolved[key] = value
				}
			}
		}
	}
	references, err := decodeIntersectionEvidenceRefs(
		resolved["intersectionEvidenceRefs"],
	)
	if err != nil {
		return nil, ErrIntersectionEvidenceNotFound
	}
	delete(resolved, "authorizedIntersectionEvidence")
	if len(references) == 0 {
		return resolved, nil
	}
	for _, reference := range references {
		if strings.TrimSpace(reference.IntersectionID) == "" ||
			strings.TrimSpace(reference.EvidenceID) == "" ||
			strings.TrimSpace(reference.SourceRef) == "" ||
			strings.TrimSpace(reference.ObjectTypeRef) == "" ||
			strings.TrimSpace(reference.ObjectID) == "" {
			return nil, ErrIntersectionEvidenceNotFound
		}
	}
	if resolver == nil || resolver.evidence == nil {
		return nil, ErrIntersectionEvidenceUnavailable
	}
	authorized, err := resolver.evidence.AuthorizeIntersectionEvidence(
		ctx,
		strings.TrimSpace(personaID),
		references,
	)
	if err != nil {
		if errors.Is(err, ErrIntersectionEvidenceNotFound) {
			return nil, ErrIntersectionEvidenceNotFound
		}
		return nil, ErrIntersectionEvidenceUnavailable
	}
	if len(authorized) != len(references) {
		return nil, ErrIntersectionEvidenceNotFound
	}
	encoded, err := json.Marshal(authorized)
	if err != nil {
		return nil, err
	}
	var canonical []any
	if err := json.Unmarshal(encoded, &canonical); err != nil {
		return nil, err
	}
	resolved["authorizedIntersectionEvidence"] = canonical
	return resolved, nil
}

func decodeIntersectionEvidenceRefs(raw any) ([]IntersectionEvidenceRef, error) {
	if raw == nil {
		return nil, nil
	}
	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil, err
	}
	var references []IntersectionEvidenceRef
	if err := json.Unmarshal(encoded, &references); err != nil {
		return nil, err
	}
	return references, nil
}

func cloneJSONMap(value map[string]any) (map[string]any, error) {
	if value == nil {
		return nil, nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	var cloned map[string]any
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		return nil, err
	}
	return cloned, nil
}

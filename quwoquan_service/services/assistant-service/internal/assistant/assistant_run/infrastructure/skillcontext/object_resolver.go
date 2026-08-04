package skillcontext

import (
	"context"
	"encoding/hex"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
)

const (
	CircleContextResolverRef  = "circle.current_context"
	ContentContextResolverRef = "content.current_context"
	EntityContextResolverRef  = "entity.current_context"
)

// ObjectContextResolver is deliberately object-neutral: new vertical facts
// provide an owning Reader and declarative object/surface bindings without
// adding a branch to AgentLoop.
type ObjectContextResolver struct {
	Runs               RunReader
	Reader             domainreader.ObjectContextReader
	OperationRef       string
	ObjectTypeRefs     []string
	SurfaceObjectTypes map[string]string
}

func (resolver ObjectContextResolver) Resolve(
	ctx context.Context,
	request application.ResolveRequest,
) (application.ResolvedContext, error) {
	if resolver.Runs == nil || resolver.Reader == nil ||
		strings.TrimSpace(resolver.OperationRef) == "" || len(resolver.ObjectTypeRefs) == 0 {
		return application.ResolvedContext{}, fmt.Errorf("domain object context resolver is unavailable")
	}
	run, err := resolver.Runs.Load(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	target, err := resolveObjectTarget(
		run.ContextSnapshot["pageObjects"],
		run.RequestContext.SurfaceKind,
		run.RequestContext.SurfaceID,
		resolver.ObjectTypeRefs,
		resolver.SurfaceObjectTypes,
	)
	if err != nil {
		return application.ResolvedContext{}, err
	}
	result, err := resolver.Reader.ReadObjectContext(ctx, target)
	if err != nil {
		return application.ResolvedContext{}, err
	}
	if result.Target != target || result.OperationRef != strings.TrimSpace(resolver.OperationRef) ||
		result.CapturedAt.IsZero() || !validSHA256Digest(result.SourceDigest) ||
		result.TokenCost < 0 || result.Value == nil {
		return application.ResolvedContext{}, fmt.Errorf("domain object context provenance is invalid")
	}
	return application.ResolvedContext{
		Kind:        "domain",
		SourceRef:   target.ObjectTypeRef + ":" + target.ObjectID + "@" + result.SourceDigest,
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityPublic,
		CapturedAt:  result.CapturedAt.UTC(),
		TokenCost:   result.TokenCost,
		Value:       result.Value,
		Summary:     strings.TrimSpace(result.Summary),
	}, nil
}

// NewCanonicalDomainResolverRegistrations is the single AssistantRun
// registration API. The composition root may append this returned slice to
// NewRuntimeRegistry without knowing any vertical-specific routing rule.
func NewCanonicalDomainResolverRegistrations(
	runs RunReader,
	readers domainreader.CanonicalReaders,
) ([]application.RegisteredResolver, error) {
	if runs == nil || readers.Circle == nil || readers.Content == nil || readers.Entity == nil {
		return nil, fmt.Errorf("canonical domain context readers are unavailable")
	}
	return []application.RegisteredResolver{
		{
			ResolverRef: CircleContextResolverRef,
			Resolver: ObjectContextResolver{
				Runs: runs, Reader: readers.Circle,
				OperationRef:       "circle.circle.GetCircle",
				ObjectTypeRefs:     []string{"circle.Circle"},
				SurfaceObjectTypes: map[string]string{"circle": "circle.Circle"},
			},
		},
		{
			ResolverRef: ContentContextResolverRef,
			Resolver: ObjectContextResolver{
				Runs: runs, Reader: readers.Content,
				OperationRef:   "content.post.GetPost",
				ObjectTypeRefs: []string{"content.Post"},
			},
		},
		{
			ResolverRef: EntityContextResolverRef,
			Resolver: ObjectContextResolver{
				Runs: runs, Reader: readers.Entity,
				OperationRef:   "entity.homepage.GetHomepageDetail",
				ObjectTypeRefs: []string{"entity.Homepage"},
			},
		},
	}, nil
}

func resolveObjectTarget(
	rawPageObjects any,
	surfaceKind string,
	surfaceID string,
	allowedObjectTypes []string,
	surfaceObjectTypes map[string]string,
) (domainreader.ObjectTarget, error) {
	allowed := make(map[string]struct{}, len(allowedObjectTypes))
	for _, value := range allowedObjectTypes {
		value = strings.TrimSpace(value)
		if value != "" {
			allowed[value] = struct{}{}
		}
	}
	candidates := map[domainreader.ObjectTarget]struct{}{}
	appendTarget := func(objectTypeRef, objectID string) {
		objectTypeRef = strings.TrimSpace(objectTypeRef)
		objectID = strings.TrimSpace(objectID)
		if _, ok := allowed[objectTypeRef]; !ok || objectID == "" {
			return
		}
		candidates[domainreader.ObjectTarget{ObjectTypeRef: objectTypeRef, ObjectID: objectID}] = struct{}{}
	}
	if values, ok := rawPageObjects.([]any); ok {
		for _, raw := range values {
			value, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			appendTarget(stringMapValue(value, "objectTypeRef"), stringMapValue(value, "objectId"))
		}
	}
	if values, ok := rawPageObjects.([]map[string]any); ok {
		for _, value := range values {
			appendTarget(stringMapValue(value, "objectTypeRef"), stringMapValue(value, "objectId"))
		}
	}
	if objectTypeRef := strings.TrimSpace(surfaceObjectTypes[strings.TrimSpace(surfaceKind)]); objectTypeRef != "" {
		appendTarget(objectTypeRef, surfaceID)
	}
	if len(candidates) != 1 {
		if len(candidates) == 0 {
			return domainreader.ObjectTarget{}, fmt.Errorf("domain object context target is unavailable")
		}
		return domainreader.ObjectTarget{}, fmt.Errorf("domain object context target is ambiguous")
	}
	for target := range candidates {
		return target, nil
	}
	return domainreader.ObjectTarget{}, fmt.Errorf("domain object context target is unavailable")
}

func validSHA256Digest(value string) bool {
	const prefix = "sha256:"
	value = strings.TrimSpace(value)
	if !strings.HasPrefix(value, prefix) || len(value) != len(prefix)+64 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, prefix))
	return err == nil
}

var _ application.Resolver = ObjectContextResolver{}

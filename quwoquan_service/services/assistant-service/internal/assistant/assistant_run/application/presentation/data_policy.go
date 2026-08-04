package presentation

import (
	"context"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

const (
	CanonicalRouteMapDataPolicyRef = "presentation.route_map.canonical"
)

type nodeDataPolicyFunc func(
	context.Context,
	generated.AssistantPresentationNodeKind,
	map[string]any,
) (map[string]any, error)

// NodeDataPolicyRegistry is the closed runtime registry for semantic data
// adapters shipped by the platform. Templates select one immutable reference;
// neither AgentLoop nor Resolver contains vertical-specific routing branches.
type NodeDataPolicyRegistry struct {
	policies map[string]nodeDataPolicyFunc
}

func NewOfficialNodeDataPolicies() *NodeDataPolicyRegistry {
	return &NodeDataPolicyRegistry{policies: map[string]nodeDataPolicyFunc{
		CanonicalRouteMapDataPolicyRef: canonicalRouteMapData,
	}}
}

func (registry *NodeDataPolicyRegistry) ResolveNodeData(
	ctx context.Context,
	policyRef string,
	kind generated.AssistantPresentationNodeKind,
	data map[string]any,
) (map[string]any, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if registry == nil {
		return nil, ErrDataPolicyRejected
	}
	policy, found := registry.policies[strings.TrimSpace(policyRef)]
	if !found || policy == nil {
		return nil, fmt.Errorf("%w: unknown policy", ErrDataPolicyRejected)
	}
	resolved, err := policy(ctx, kind, cloneMap(data))
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrDataPolicyRejected, err)
	}
	return resolved, nil
}

func canonicalRouteMapData(
	_ context.Context,
	kind generated.AssistantPresentationNodeKind,
	data map[string]any,
) (map[string]any, error) {
	if kind != generated.AssistantPresentationNodeKindRouteMap {
		return nil, ErrInvalidData
	}
	if err := validateRouteMapData(data); err != nil {
		return nil, err
	}
	return cloneMap(data), nil
}

var _ NodeDataPolicy = (*NodeDataPolicyRegistry)(nil)

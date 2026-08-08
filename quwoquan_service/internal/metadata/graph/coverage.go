package graph

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

type Coverage struct {
	Sources                  int            `json:"sources"`
	Documents                int            `json:"documents"`
	Objects                  int            `json:"objects"`
	ExplicitObjectKinds      int            `json:"explicitObjectKinds"`
	Operations               int            `json:"operations"`
	RuntimeEntrypoints       int            `json:"runtimeEntrypoints"`
	ExplicitOperationKinds   int            `json:"explicitOperationKinds"`
	BoundOperations          int            `json:"boundOperations"`
	Projections              int            `json:"projections"`
	PublicOperations         int            `json:"publicOperations"`
	OpenAPIOperations        int            `json:"openapiOperations"`
	OpenAPIMatched           int            `json:"openapiMatched"`
	OpenAPIOrphans           int            `json:"openapiOrphans"`
	RegisteredDomains        int            `json:"registeredDomains"`
	BoundedContexts          int            `json:"boundedContexts"`
	RegisteredObjects        int            `json:"registeredObjects"`
	ObjectRelationships      int            `json:"objectRelationships"`
	ReadinessCases           int            `json:"readinessCases"`
	ReadinessEvidencePackets int            `json:"readinessEvidencePackets"`
	ReadinessEvidenceObjects int            `json:"readinessEvidenceObjects"`
	ReadinessModeled         int            `json:"readinessModeled"`
	ReadinessContractReady   int            `json:"readinessContractReady"`
	ReadinessImplemented     int            `json:"readinessImplemented"`
	ReadinessCommercialReady int            `json:"readinessCommercialReady"`
	ObjectsByKind            map[string]int `json:"objectsByKind"`
	OperationsByKind         map[string]int `json:"operationsByKind"`
	ObjectsByReadiness       map[string]int `json:"objectsByReadiness"`
}

func (g *ContractGraph) Coverage() Coverage {
	result := Coverage{
		Sources:            len(g.Sources),
		Documents:          len(g.Documents),
		Objects:            len(g.Objects),
		Operations:         len(g.Operations),
		RuntimeEntrypoints: len(g.RuntimeEntrypoints),
		Projections:        len(g.Projections),
		ReadinessCases:     len(g.ReadinessCases),
		ObjectsByKind:      map[string]int{},
		OperationsByKind:   map[string]int{},
		ObjectsByReadiness: map[string]int{},
	}
	for _, object := range g.Objects {
		result.ObjectsByKind[string(object.Kind)]++
		if object.KindExplicit {
			result.ExplicitObjectKinds++
		}
	}
	result.RegisteredDomains = len(g.BusinessObjectMaps)
	result.ReadinessEvidencePackets = len(g.ReadinessEvidence)
	knownObjects := make(map[string]struct{}, len(g.Objects))
	for _, object := range g.Objects {
		knownObjects[object.ID] = struct{}{}
	}
	evidenceObjects := map[string]struct{}{}
	for _, evidence := range g.ReadinessEvidence {
		if _, exists := knownObjects[evidence.ObjectID]; exists {
			evidenceObjects[evidence.ObjectID] = struct{}{}
		}
	}
	result.ReadinessEvidenceObjects = len(evidenceObjects)
	for _, readiness := range g.ObjectReadiness {
		result.ObjectsByReadiness[readiness.Stage]++
		if readiness.Modeled {
			result.ReadinessModeled++
		}
		if readiness.ContractReady {
			result.ReadinessContractReady++
		}
		if readiness.Implemented {
			result.ReadinessImplemented++
		}
		if readiness.CommercialReady {
			result.ReadinessCommercialReady++
		}
	}
	for _, objectMap := range g.BusinessObjectMaps {
		result.BoundedContexts += len(objectMap.BoundedContexts)
		result.RegisteredObjects += len(objectMap.Objects)
		for _, object := range objectMap.Objects {
			result.ObjectRelationships += len(object.Relationships)
		}
	}
	for _, operation := range g.Operations {
		result.OperationsByKind[string(operation.Kind)]++
		if operation.KindExplicit {
			result.ExplicitOperationKinds++
		}
		if operation.Facet != "" && operation.FacadeMethod != "" {
			switch operation.Kind {
			case ast.OperationKindCommand:
				if operation.AggregateOwner != "" || operation.AppendSink != "" ||
					operation.LifecycleOwner != "" {
					result.BoundOperations++
				}
			case ast.OperationKindQuery:
				if operation.Reader != "" && operation.Slice != "" {
					result.BoundOperations++
				}
			case ast.OperationKindSession:
				if operation.SessionOwner != "" {
					result.BoundOperations++
				}
			}
		}
		if isPublicTransportPath(operation.PathTemplate) {
			result.PublicOperations++
		}
	}
	openAPITransports, err := g.OpenAPITransports()
	if err == nil {
		result.OpenAPIOperations = len(openAPITransports)
		operationTransports := map[string]struct{}{}
		for _, operation := range g.Operations {
			operationTransports[operation.Method+" "+operation.PathTemplate] = struct{}{}
		}
		for _, transport := range openAPITransports {
			if _, exists := operationTransports[transport.Method+" "+transport.Path]; exists {
				result.OpenAPIMatched++
			} else {
				result.OpenAPIOrphans++
			}
		}
	}
	return result
}

func isPublicTransportPath(path string) bool {
	switch path {
	case "", "/health", "/healthz", "/readyz", "/metrics", "/livez", "/startupz":
		return false
	}
	if strings.HasPrefix(path, "/internal/") || strings.HasPrefix(path, "/callbacks/") {
		return false
	}
	return strings.HasPrefix(path, "/")
}

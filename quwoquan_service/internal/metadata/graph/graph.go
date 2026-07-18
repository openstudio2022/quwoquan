package graph

import (
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
)

// ContractGraph 是所有 validator、generator 和 coverage 消费的唯一规范化图。
type ContractGraph struct {
	Objects            []ast.Object                  `json:"objects"`
	Operations         []ast.Operation               `json:"operations"`
	Projections        []ast.Projection              `json:"projections"`
	BusinessObjectMaps []ast.BusinessObjectMap       `json:"businessObjectMaps"`
	ReadinessEvidence  []ast.ObjectReadinessEvidence `json:"readinessEvidence"`
	ObjectReadiness    []ObjectReadiness             `json:"objectReadiness"`
	Sources            []ast.SourceDigest            `json:"sources"`
	Documents          []ast.SourceDocument          `json:"documents"`
}

type ObjectReadiness struct {
	ObjectID        string   `json:"objectId"`
	Stage           string   `json:"stage"`
	Modeled         bool     `json:"modeled"`
	ContractReady   bool     `json:"contractReady"`
	Implemented     bool     `json:"implemented"`
	CommercialReady bool     `json:"commercialReady"`
	Missing         []string `json:"missing"`
}

type Coverage struct {
	Sources                  int            `json:"sources"`
	Documents                int            `json:"documents"`
	Objects                  int            `json:"objects"`
	ExplicitObjectKinds      int            `json:"explicitObjectKinds"`
	Operations               int            `json:"operations"`
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
	ReadinessEvidencePackets int            `json:"readinessEvidencePackets"`
	ObjectsByKind            map[string]int `json:"objectsByKind"`
	OperationsByKind         map[string]int `json:"operationsByKind"`
	ObjectsByReadiness       map[string]int `json:"objectsByReadiness"`
}

func Build(catalog *ast.Catalog) *ContractGraph {
	result := &ContractGraph{
		Objects:     append([]ast.Object(nil), catalog.Objects...),
		Operations:  append([]ast.Operation(nil), catalog.Operations...),
		Projections: append([]ast.Projection(nil), catalog.Projections...),
		BusinessObjectMaps: append(
			[]ast.BusinessObjectMap{},
			catalog.BusinessObjectMaps...,
		),
		ReadinessEvidence: append(
			[]ast.ObjectReadinessEvidence{},
			catalog.ReadinessEvidence...,
		),
		Sources:   append([]ast.SourceDigest(nil), catalog.Sources...),
		Documents: append([]ast.SourceDocument(nil), catalog.Documents...),
	}
	sort.Slice(result.Objects, func(i, j int) bool {
		return result.Objects[i].ID < result.Objects[j].ID
	})
	sort.Slice(result.Operations, func(i, j int) bool {
		return result.Operations[i].ID < result.Operations[j].ID
	})
	sort.Slice(result.Projections, func(i, j int) bool {
		return result.Projections[i].ID < result.Projections[j].ID
	})
	sort.Slice(result.BusinessObjectMaps, func(i, j int) bool {
		return result.BusinessObjectMaps[i].Domain <
			result.BusinessObjectMaps[j].Domain
	})
	sort.Slice(result.ReadinessEvidence, func(i, j int) bool {
		return result.ReadinessEvidence[i].ObjectID < result.ReadinessEvidence[j].ObjectID
	})
	for index := range result.ReadinessEvidence {
		evidence := &result.ReadinessEvidence[index]
		sort.Strings(evidence.OperationIDs)
		sortEvidenceArtifacts(evidence.DomainBehavior)
		sortEvidenceArtifacts(evidence.Store)
		sortEvidenceArtifacts(evidence.Outbox)
		sortEvidenceArtifacts(evidence.Reader)
		sortEvidenceArtifacts(evidence.Transport)
		sortEvidenceArtifacts(evidence.AppClient)
		sortEvidenceArtifacts(evidence.Page)
		sortEvidenceArtifacts(evidence.LocalContract)
		sortEvidenceArtifacts(evidence.APIIntegration)
		sortEvidenceArtifacts(evidence.UserAcceptance)
		if evidence.Environments == nil {
			evidence.Environments = []ast.EnvironmentEvidence{}
		}
		sort.Slice(evidence.Environments, func(i, j int) bool {
			return evidence.Environments[i].Name < evidence.Environments[j].Name
		})
	}
	for index := range result.BusinessObjectMaps {
		sort.Slice(
			result.BusinessObjectMaps[index].BoundedContexts,
			func(i, j int) bool {
				return result.BusinessObjectMaps[index].BoundedContexts[i].Name <
					result.BusinessObjectMaps[index].BoundedContexts[j].Name
			},
		)
		sort.Slice(
			result.BusinessObjectMaps[index].Objects,
			func(i, j int) bool {
				return result.BusinessObjectMaps[index].Objects[i].CanonicalObject <
					result.BusinessObjectMaps[index].Objects[j].CanonicalObject
			},
		)
		for objectIndex := range result.BusinessObjectMaps[index].Objects {
			sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].Identity.Fields)
			sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].InvariantRefs)
			sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].MutationEntrypoints)
			sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].EventConsumers)
			sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].LifecycleRefs)
			sort.Slice(
				result.BusinessObjectMaps[index].Objects[objectIndex].Relationships,
				func(i, j int) bool {
					return result.BusinessObjectMaps[index].Objects[objectIndex].Relationships[i].Name <
						result.BusinessObjectMaps[index].Objects[objectIndex].Relationships[j].Name
				},
			)
			for relationshipIndex := range result.BusinessObjectMaps[index].Objects[objectIndex].Relationships {
				sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].Relationships[relationshipIndex].TargetObjects)
				sort.Strings(result.BusinessObjectMaps[index].Objects[objectIndex].Relationships[relationshipIndex].ReferenceFields)
			}
		}
	}
	sort.Slice(result.Sources, func(i, j int) bool {
		return result.Sources[i].Path < result.Sources[j].Path
	})
	sort.Slice(result.Documents, func(i, j int) bool {
		return result.Documents[i].Path < result.Documents[j].Path
	})
	result.ObjectReadiness = deriveObjectReadiness(result)
	return result
}

func sortEvidenceArtifacts(values []ast.EvidenceArtifact) {
	sort.Slice(values, func(i, j int) bool { return values[i].Path < values[j].Path })
}

func deriveObjectReadiness(contractGraph *ContractGraph) []ObjectReadiness {
	registered := map[string]struct{}{}
	for _, objectMap := range contractGraph.BusinessObjectMaps {
		for _, object := range objectMap.Objects {
			registered[objectMap.Domain+"."+strings.TrimSpace(object.CanonicalObject)] = struct{}{}
		}
	}
	evidenceByObject := make(map[string]ast.ObjectReadinessEvidence, len(contractGraph.ReadinessEvidence))
	for _, evidence := range contractGraph.ReadinessEvidence {
		evidenceByObject[evidence.ObjectID] = evidence
	}
	operationsByObject := map[string][]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		operationsByObject[operation.ObjectID] = append(operationsByObject[operation.ObjectID], operation)
	}
	result := make([]ObjectReadiness, 0, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		missing := map[string]struct{}{}
		_, hasRegistration := registered[object.Domain+"."+object.Name]
		modeled := object.KindExplicit && hasRegistration
		if !object.KindExplicit {
			missing["object.kind"] = struct{}{}
		}
		if !hasRegistration {
			missing["object.registry"] = struct{}{}
		}
		operations := operationsByObject[object.ID]
		contractReady := modeled && objectContractReady(object, operations, missing)
		evidence, hasEvidence := evidenceByObject[object.ID]
		implemented := contractReady && hasEvidence && implementationEvidenceReady(
			object,
			operations,
			evidence,
			missing,
		)
		if contractReady && !hasEvidence {
			missing["readiness.evidence"] = struct{}{}
		}
		commercialReady := implemented && commercialEvidenceReady(evidence, missing)
		stage := "modeled"
		switch {
		case commercialReady:
			stage = "commercial-ready"
		case implemented:
			stage = "implemented"
		case contractReady:
			stage = "contract-ready"
		case !modeled:
			stage = "unmodeled"
		}
		missingList := make([]string, 0, len(missing))
		for item := range missing {
			missingList = append(missingList, item)
		}
		sort.Strings(missingList)
		result = append(result, ObjectReadiness{
			ObjectID: object.ID, Stage: stage, Modeled: modeled,
			ContractReady: contractReady, Implemented: implemented,
			CommercialReady: commercialReady, Missing: missingList,
		})
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ObjectID < result[j].ObjectID })
	return result
}

func objectContractReady(
	object ast.Object,
	operations []ast.Operation,
	missing map[string]struct{},
) bool {
	if len(operations) == 0 {
		if object.Kind == ast.ObjectKindProjection || object.Kind == ast.ObjectKindExternalReference {
			return true
		}
		missing["operation.entrypoint"] = struct{}{}
		return false
	}
	ready := true
	for _, operation := range operations {
		prefix := "operation." + operation.LocalID + "."
		if !operation.KindExplicit || operation.Facet == "" || operation.FacadeMethod == "" {
			missing[prefix+"application"] = struct{}{}
			ready = false
		}
		switch operation.Kind {
		case ast.OperationKindCommand:
			if (operation.AggregateOwner == "") == (operation.AppendSink == "") {
				missing[prefix+"mutation_owner"] = struct{}{}
				ready = false
			}
		case ast.OperationKindQuery:
			if operation.Reader == "" || operation.Slice == "" {
				missing[prefix+"reader"] = struct{}{}
				ready = false
			}
		case ast.OperationKindSession:
			if operation.SessionOwner == "" {
				missing[prefix+"session_owner"] = struct{}{}
				ready = false
			}
		}
		if operation.AuthMode == "" || operation.AuthMode == "deny" ||
			operation.Principal == "" || operation.OwnershipPolicy == "" {
			missing[prefix+"security"] = struct{}{}
			ready = false
		}
		if operation.Reliability.TimeoutMilliseconds <= 0 ||
			operation.Reliability.Cancellation == "" ||
			operation.Reliability.RetryMode == "" ||
			operation.Reliability.MaxAttempts <= 0 ||
			operation.Reliability.Idempotency == "" {
			missing[prefix+"reliability"] = struct{}{}
			ready = false
		}
		if len(operation.ErrorCodes) == 0 ||
			operation.Privacy.RequestClassification == "" ||
			operation.Privacy.ResponseClassification == "" ||
			operation.Privacy.LogPolicy == "" ||
			operation.Telemetry.Metric == "" || !operation.Telemetry.Trace ||
			operation.SLO.LatencyP95Milliseconds <= 0 ||
			operation.SLO.AvailabilityPercent <= 0 {
			missing[prefix+"commercial_contract"] = struct{}{}
			ready = false
		}
	}
	return ready
}

func implementationEvidenceReady(
	object ast.Object,
	operations []ast.Operation,
	evidence ast.ObjectReadinessEvidence,
	missing map[string]struct{},
) bool {
	ready := true
	require := func(name string, values []ast.EvidenceArtifact) {
		if len(values) == 0 {
			missing["implementation."+name] = struct{}{}
			ready = false
		}
	}
	require("domain_behavior", evidence.DomainBehavior)
	require("transport", evidence.Transport)
	require("local_contract", evidence.LocalContract)
	require("api_integration", evidence.APIIntegration)
	hasCommand := false
	hasQuery := false
	hasClient := false
	for _, operation := range operations {
		hasCommand = hasCommand || operation.Kind == ast.OperationKindCommand
		hasQuery = hasQuery || operation.Kind == ast.OperationKindQuery
		hasClient = hasClient || operation.ClientContract != nil
	}
	if object.Kind == ast.ObjectKindAggregateRoot || object.Kind == ast.ObjectKindRuntimeSession {
		require("store", evidence.Store)
	}
	if hasCommand && object.Kind == ast.ObjectKindAggregateRoot {
		require("outbox", evidence.Outbox)
	}
	if hasQuery {
		require("reader", evidence.Reader)
	}
	if hasClient {
		require("app_client", evidence.AppClient)
		require("page", evidence.Page)
	}
	return ready
}

func commercialEvidenceReady(
	evidence ast.ObjectReadinessEvidence,
	missing map[string]struct{},
) bool {
	ready := true
	if len(evidence.UserAcceptance) == 0 {
		missing["commercial.user_acceptance"] = struct{}{}
		ready = false
	}
	environments := map[string]struct{}{}
	for _, environment := range evidence.Environments {
		environments[environment.Name] = struct{}{}
	}
	for _, required := range []string{"alpha", "beta", "gamma", "prod"} {
		if _, exists := environments[required]; !exists {
			missing["commercial.environment."+required] = struct{}{}
			ready = false
		}
	}
	return ready
}

func (g *ContractGraph) Coverage() Coverage {
	result := Coverage{
		Sources:            len(g.Sources),
		Documents:          len(g.Documents),
		Objects:            len(g.Objects),
		Operations:         len(g.Operations),
		Projections:        len(g.Projections),
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
	for _, readiness := range g.ObjectReadiness {
		result.ObjectsByReadiness[readiness.Stage]++
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
				if operation.AggregateOwner != "" || operation.AppendSink != "" {
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
	case "", "/health", "/healthz", "/metrics", "/livez", "/startupz":
		return false
	}
	if strings.HasPrefix(path, "/internal/") || strings.HasPrefix(path, "/callbacks/") {
		return false
	}
	return strings.HasPrefix(path, "/")
}

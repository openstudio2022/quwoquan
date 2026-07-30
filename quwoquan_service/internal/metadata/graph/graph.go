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
	RuntimeEntrypoints []ast.RuntimeEntrypoint       `json:"runtimeEntrypoints"`
	Projections        []ast.Projection              `json:"projections"`
	BusinessObjectMaps []ast.BusinessObjectMap       `json:"businessObjectMaps"`
	ReadinessEvidence  []ast.ObjectReadinessEvidence `json:"readinessEvidence"`
	ObjectReadiness    []ObjectReadiness             `json:"objectReadiness"`
	Sources            []ast.SourceDigest            `json:"sources"`
	Documents          []ast.SourceDocument          `json:"documents"`
	Governance         ast.MetadataGovernance        `json:"-"`
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

func Build(catalog *ast.Catalog) *ContractGraph {
	result := &ContractGraph{
		Objects:    append([]ast.Object{}, catalog.Objects...),
		Operations: append([]ast.Operation{}, catalog.Operations...),
		RuntimeEntrypoints: append(
			[]ast.RuntimeEntrypoint{},
			catalog.RuntimeEntrypoints...,
		),
		Projections: append([]ast.Projection{}, catalog.Projections...),
		BusinessObjectMaps: append(
			[]ast.BusinessObjectMap{},
			catalog.BusinessObjectMaps...,
		),
		ReadinessEvidence: append(
			[]ast.ObjectReadinessEvidence{},
			catalog.ReadinessEvidence...,
		),
		Sources:    append([]ast.SourceDigest{}, catalog.Sources...),
		Documents:  append([]ast.SourceDocument{}, catalog.Documents...),
		Governance: catalog.Governance,
	}
	sort.Slice(result.Objects, func(i, j int) bool {
		return result.Objects[i].ID < result.Objects[j].ID
	})
	sort.Slice(result.Operations, func(i, j int) bool {
		return result.Operations[i].ID < result.Operations[j].ID
	})
	sort.Slice(result.RuntimeEntrypoints, func(i, j int) bool {
		return result.RuntimeEntrypoints[i].ID < result.RuntimeEntrypoints[j].ID
	})
	sort.Slice(result.Projections, func(i, j int) bool {
		return result.Projections[i].ID < result.Projections[j].ID
	})
	for index := range result.Projections {
		sort.Strings(result.Projections[index].FieldNames)
		sort.Strings(result.Projections[index].SourceEntities)
		sort.Strings(result.Projections[index].SourceEvents)
	}
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
	evidenceCountByObject := make(map[string]int, len(contractGraph.ReadinessEvidence))
	for _, evidence := range contractGraph.ReadinessEvidence {
		evidenceByObject[evidence.ObjectID] = evidence
		evidenceCountByObject[evidence.ObjectID]++
	}
	operationsByObject := map[string][]ast.Operation{}
	for _, operation := range contractGraph.Operations {
		operationsByObject[operation.ObjectID] = append(operationsByObject[operation.ObjectID], operation)
	}
	runtimeEntrypointsByObject := map[string][]ast.RuntimeEntrypoint{}
	for _, entrypoint := range contractGraph.RuntimeEntrypoints {
		runtimeEntrypointsByObject[entrypoint.ObjectID] = append(
			runtimeEntrypointsByObject[entrypoint.ObjectID],
			entrypoint,
		)
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
		runtimeEntrypoints := runtimeEntrypointsByObject[object.ID]
		contractReady := modeled && objectContractReady(
			object,
			operations,
			runtimeEntrypoints,
			missing,
		)
		evidence, hasEvidence := evidenceByObject[object.ID]
		if evidenceCountByObject[object.ID] > 1 {
			missing["readiness.evidence.duplicate"] = struct{}{}
			hasEvidence = false
		}
		implemented := contractReady && hasEvidence && implementationEvidenceReady(
			object,
			operations,
			runtimeEntrypoints,
			evidence,
			missing,
		)
		if contractReady && evidenceCountByObject[object.ID] == 0 {
			missing["readiness.evidence"] = struct{}{}
		}
		commercialReady := implemented && commercialEvidenceReady(
			operations,
			evidence,
			missing,
		)
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
	runtimeEntrypoints []ast.RuntimeEntrypoint,
	missing map[string]struct{},
) bool {
	if len(operations) != 0 && len(runtimeEntrypoints) != 0 {
		missing["entrypoint.dual_track"] = struct{}{}
		return false
	}
	if len(operations) == 0 {
		if len(runtimeEntrypoints) == 1 {
			entrypoint := runtimeEntrypoints[0]
			if entrypoint.RuntimeKind != "middleware" ||
				entrypoint.Phase != "post_authorization_pre_owner_proxy" ||
				entrypoint.ApplicationKind != ast.OperationKindSession ||
				entrypoint.Facet == "" ||
				entrypoint.FacadeMethod == "" ||
				entrypoint.SessionOwner != object.Name {
				missing["runtime_entrypoint.application"] = struct{}{}
				return false
			}
			return true
		}
		if len(runtimeEntrypoints) > 1 {
			missing["runtime_entrypoint.unique"] = struct{}{}
			return false
		}
		// append_only_fact 允许零公开 operation：服务端内生事实（如已读回执、
		// 投递 attempt）由所属聚合命令在事务内追加，写入语义由
		// 对象本地 events/operations 的 append-only 关系表达。
		if object.Kind == ast.ObjectKindProjection ||
			object.Kind == ast.ObjectKindExternalReference ||
			object.Kind == ast.ObjectKindAppendOnlyFact {
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
	runtimeEntrypoints []ast.RuntimeEntrypoint,
	evidence ast.ObjectReadinessEvidence,
	missing map[string]struct{},
) bool {
	ready := true
	require := func(name string, values []ast.EvidenceArtifact) {
		if !evidenceArtifactsReady(values) {
			missing["implementation."+name] = struct{}{}
			ready = false
		}
	}
	if strings.TrimSpace(evidence.SourcePath) == "" {
		missing["implementation.evidence_provenance"] = struct{}{}
		ready = false
	}
	expectedOperationIDs := make([]string, 0, len(operations))
	for _, operation := range operations {
		expectedOperationIDs = append(expectedOperationIDs, operation.ID)
	}
	for _, entrypoint := range runtimeEntrypoints {
		expectedOperationIDs = append(expectedOperationIDs, entrypoint.ID)
	}
	if !sameStringSet(evidence.OperationIDs, expectedOperationIDs) {
		missing["implementation.operation_coverage"] = struct{}{}
		ready = false
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
	operations []ast.Operation,
	evidence ast.ObjectReadinessEvidence,
	missing map[string]struct{},
) bool {
	ready := true
	if !evidenceArtifactsReady(evidence.UserAcceptance) {
		missing["commercial.user_acceptance"] = struct{}{}
		ready = false
	}
	for _, operation := range operations {
		if operation.Commercial.Status != "ready" {
			missing["commercial.operation."+operation.LocalID] = struct{}{}
			ready = false
		}
	}
	environments := map[string]bool{}
	for _, environment := range evidence.Environments {
		if evidenceArtifactReady(environment.Artifact) {
			environments[environment.Name] = true
		}
	}
	for _, required := range []string{"alpha", "beta", "gamma", "prod"} {
		if !environments[required] {
			missing["commercial.environment."+required] = struct{}{}
			ready = false
		}
	}
	return ready
}

func evidenceArtifactsReady(values []ast.EvidenceArtifact) bool {
	if len(values) == 0 {
		return false
	}
	for _, value := range values {
		if !evidenceArtifactReady(value) {
			return false
		}
	}
	return true
}

func evidenceArtifactReady(value ast.EvidenceArtifact) bool {
	if strings.TrimSpace(value.Path) == "" || len(value.SHA256) != 64 {
		return false
	}
	for _, character := range value.SHA256 {
		if (character < '0' || character > '9') &&
			(character < 'a' || character > 'f') {
			return false
		}
	}
	return true
}

func sameStringSet(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	values := make(map[string]struct{}, len(left))
	for _, value := range left {
		if _, exists := values[value]; exists {
			return false
		}
		values[value] = struct{}{}
	}
	for _, value := range right {
		if _, exists := values[value]; !exists {
			return false
		}
	}
	return true
}

func (g *ContractGraph) Coverage() Coverage {
	result := Coverage{
		Sources:            len(g.Sources),
		Documents:          len(g.Documents),
		Objects:            len(g.Objects),
		Operations:         len(g.Operations),
		RuntimeEntrypoints: len(g.RuntimeEntrypoints),
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
	case "", "/health", "/healthz", "/readyz", "/metrics", "/livez", "/startupz":
		return false
	}
	if strings.HasPrefix(path, "/internal/") || strings.HasPrefix(path, "/callbacks/") {
		return false
	}
	return strings.HasPrefix(path, "/")
}

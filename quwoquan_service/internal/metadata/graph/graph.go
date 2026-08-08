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
	ReadinessCases     []ast.ReadinessCaseContract   `json:"readinessCases"`
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

// publicationDuty 是对象级的「事务性事件发布义务」派生结果。
type publicationDuty struct {
	required bool
}

// derivePublicationDuties 按每个对象自己声明的领域事件投递保证派生发布义务。
// 分类口径见 ast.ClassifyEventDelivery：只有全部事件都是自留/瞬时语义时才不要求 seam。
//
// 这里不再带出「未知取值 / 缺键」触发原因：`delivery_semantics` 由
// `_schemas/events.schema.json` 的 enum 与 required 强制，两类情况都已不可能通过校验，
// 留着就是留一个永远为空的维度。分类函数仍对未知取值 fail-safe 到要求侧，防的是绕过
// schema 的调用路径，不是可发生的契约状态。
func derivePublicationDuties(packets []ast.ObjectGovernance) map[string]publicationDuty {
	duties := map[string]publicationDuty{}
	for _, packet := range packets {
		duty := duties[packet.ObjectID]
		for _, event := range packet.Events {
			if ast.ClassifyEventDelivery(event.DeliverySemantics).RequiresReliablePublication() {
				duty.required = true
			}
		}
		duties[packet.ObjectID] = duty
	}
	return duties
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
		ReadinessCases: make(
			[]ast.ReadinessCaseContract,
			len(catalog.ReadinessCases),
		),
		ReadinessEvidence: append(
			[]ast.ObjectReadinessEvidence{},
			catalog.ReadinessEvidence...,
		),
		Sources:    append([]ast.SourceDigest{}, catalog.Sources...),
		Documents:  append([]ast.SourceDocument{}, catalog.Documents...),
		Governance: catalog.Governance,
	}
	for index, readinessCase := range catalog.ReadinessCases {
		result.ReadinessCases[index] = readinessCase
		result.ReadinessCases[index].Executions = append(
			[]ast.ReadinessExecutionRequirement(nil),
			readinessCase.Executions...,
		)
	}
	deriveClientContracts(result)
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
	sort.Slice(result.ReadinessCases, func(i, j int) bool {
		left, right := result.ReadinessCases[i], result.ReadinessCases[j]
		if left.ObjectID != right.ObjectID {
			return left.ObjectID < right.ObjectID
		}
		if left.CaseID != right.CaseID {
			return left.CaseID < right.CaseID
		}
		if left.Producer != right.Producer {
			return left.Producer < right.Producer
		}
		if left.Layer != right.Layer {
			return left.Layer < right.Layer
		}
		if left.Target.Kind != right.Target.Kind {
			return left.Target.Kind < right.Target.Kind
		}
		return left.Target.ID < right.Target.ID
	})
	for index := range result.ReadinessCases {
		executions := result.ReadinessCases[index].Executions
		sort.Slice(executions, func(i, j int) bool {
			left, right := executions[i], executions[j]
			if left.Environment != right.Environment {
				return left.Environment < right.Environment
			}
			if left.Platform != right.Platform {
				return left.Platform < right.Platform
			}
			if left.DeviceClass != right.DeviceClass {
				return left.DeviceClass < right.DeviceClass
			}
			if left.Provider != right.Provider {
				return left.Provider < right.Provider
			}
			return left.DigestBinding < right.DigestBinding
		})
	}
	for index := range result.ReadinessEvidence {
		evidence := &result.ReadinessEvidence[index]
		sort.Strings(evidence.OperationIDs)
		for _, artifacts := range [][]ast.EvidenceArtifact{
			evidence.Service.Domain,
			evidence.Service.Store,
			evidence.Service.Reader,
			evidence.Service.Transport,
			evidence.Service.LocalContract,
			evidence.Service.APIIntegration,
			evidence.App.Domain,
			evidence.App.Application,
			evidence.App.Adapters,
			evidence.App.Presentation,
			evidence.App.LocalContract,
			evidence.App.APIIntegration,
			evidence.App.UserAcceptance,
			evidence.Ops.EnvironmentAcceptance,
			evidence.Ops.RollbackRunner,
			evidence.Ops.ReplayRunner,
		} {
			sortEvidenceArtifacts(artifacts)
		}
		sortStorageEvidence(evidence.Service.Outbox)
		sortStorageEvidence(evidence.PublicationDelivery)
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

func sortStorageEvidence(values []ast.StorageEvidence) {
	sort.Slice(values, func(i, j int) bool {
		if values[i].Storage != values[j].Storage {
			return values[i].Storage < values[j].Storage
		}
		return values[i].Artifact.Path < values[j].Artifact.Path
	})
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
	// 领域事件的**投递语义**是 outbox 必需性的唯一来源，见 implementationEvidenceReady。
	publicationDuties := derivePublicationDuties(contractGraph.Governance.Objects)
	runtimeEntrypointsByObject := map[string][]ast.RuntimeEntrypoint{}
	for _, entrypoint := range contractGraph.RuntimeEntrypoints {
		runtimeEntrypointsByObject[entrypoint.ObjectID] = append(
			runtimeEntrypointsByObject[entrypoint.ObjectID],
			entrypoint,
		)
	}
	readinessCasesByObject := map[string][]ast.ReadinessCaseContract{}
	for _, readinessCase := range contractGraph.ReadinessCases {
		readinessCasesByObject[readinessCase.ObjectID] = append(
			readinessCasesByObject[readinessCase.ObjectID], readinessCase,
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
		duty := publicationDuties[object.ID]
		implemented := contractReady && hasEvidence && implementationEvidenceReady(
			object,
			operations,
			runtimeEntrypoints,
			readinessCasesByObject[object.ID],
			duty.required,
			evidence,
			missing,
		)
		if contractReady && evidenceCountByObject[object.ID] == 0 {
			missing["readiness.evidence"] = struct{}{}
		}
		// 反方向缺陷与「有没有发布义务」无关：任何对象的实现树里出现「事务性写入一张全仓
		// 无人声明的关系」，都意味着有一张表在契约外承重。它与「声明了但没观测到写入」
		// 修法不同（补声明 vs 补实现），所以是独立维度，且不参与 implemented 判定——
		// 它是契约覆盖缺陷，不是本对象的实现缺陷。
		if len(evidence.UndeclaredStorageWrites) != 0 {
			missing["contract.storage_declaration_missing"] = struct{}{}
		}
		// Static ContractGraph never consumes environment execution history.
		// Commercial closure is evaluated separately from a current
		// readiness.ReadinessResultBundle. Keep the policy and missing dynamic
		// input visible, but never advance beyond implemented here.
		commercialReady := false
		for _, operation := range operations {
			if operation.Commercial.Status != "ready" {
				missing["commercial.operation."+operation.LocalID] = struct{}{}
			}
		}
		if implemented {
			missing["commercial.result_bundle"] = struct{}{}
		}
		stage := "modeled"
		switch {
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

// requirePublicationSeam 把「事务性事件发布 seam 是否成立」拆成三条**互斥**缺口，一个对象
// 一次只拿到一条原因，三条的关闭方式各不相同：
//
//   - `contract.storage_publication_unannotated`：该对象声明了存储但没标注 `publication_role`，
//     判别位缺失，连「哪张表是发件箱」都无法回答。未标注不许被当成「不发布」静默豁免。
//     关闭方式：契约侧补标注。
//   - `contract.storage_publication_undeclared`：标注齐全，但没有任何一张存储被标注为发布
//     seam——契约明确说自己没有发件箱，却又声明了要求可靠投递的领域事件，两边相互否定。
//     关闭方式：补声明归属，或把事件的 `channel` 改成自留语义。
//   - `implementation.outbox`：归属声明齐全，代码里也不存在这张关系，属真缺口——
//     「声明了一张没人写、甚至根本不存在的表」。关闭方式：补实现或撤声明。
//   - `blindspot.publication_write_tracking`：关系名在服务里被绑定过，但写入发生在 Go AST
//     跟不动的地方（构造参数注入的集合句柄、调用方传入的事务上下文）。它是**维度盲点**
//     不是缺口：把跟不动的地方报成缺口，等于让人去补一份本来就存在的实现。
//   - `blindspot.python_store_invisible`：实现是 Python，但受支持的 PyMongo AST 形状仍
//     无法证明事务写入。既不判达标也不把写入误报成缺口；一旦写入已经证明，后续缺失的
//     delivery 就是正常结构缺口，不能继续借 Python 身份隐藏。
//
// 反方向的 `contract.storage_declaration_missing`（有事务性写入但全仓无声明位）不在这里
// 判：它与本对象是否有发布义务无关，任何对象都要报，见 deriveObjectReadiness。
//
// 归属与真实性必须合成，任何一半单独都会判错，理由见 load/publication_evidence.go 的说明。
func requirePublicationSeam(
	evidence ast.ObjectReadinessEvidence,
	missing map[string]struct{},
) bool {
	if len(evidence.PublicationStores) == 0 {
		if len(evidence.UnannotatedStores) != 0 {
			missing["contract.storage_publication_unannotated"] = struct{}{}
		} else {
			missing["contract.storage_publication_undeclared"] = struct{}{}
		}
		return false
	}
	unresolved := map[string]struct{}{}
	for _, storage := range evidence.UnresolvedPublicationWrites {
		unresolved[storage] = struct{}{}
	}
	proven := map[string]struct{}{}
	for _, binding := range evidence.Service.Outbox {
		if strings.TrimSpace(binding.Artifact.SHA256) != "" &&
			strings.TrimSpace(binding.Artifact.Path) != "" {
			proven[binding.Storage] = struct{}{}
		}
	}
	ready := true
	// 声明了多张发布 seam 时逐张判：少一张就是少一条发布链，不能被另一张的证据盖过去。
	for _, storage := range evidence.PublicationStores {
		if _, ok := proven[storage]; ok {
			continue
		}
		ready = false
		switch {
		case evidence.PythonImplementation:
			missing["blindspot.python_store_invisible"] = struct{}{}
		case containsKey(unresolved, storage):
			missing["blindspot.publication_write_tracking"] = struct{}{}
		default:
			missing["implementation.outbox"] = struct{}{}
		}
	}
	// 投递实现只对事务性发件箱要求：事务性事件表按定义没有具名消费者。
	delivered := map[string]struct{}{}
	for _, artifact := range evidence.PublicationDelivery {
		delivered[artifact.Storage] = struct{}{}
	}
	for _, storage := range evidence.DeliveryStores {
		if _, ok := delivered[storage]; ok {
			continue
		}
		if _, unproven := proven[storage]; !unproven {
			// 连写入都没证明的存储不再叠加投递缺口：一个对象一次只拿一条可执行的原因。
			continue
		}
		ready = false
		switch {
		case containsValue(evidence.UnresolvedPublicationDelivery, storage):
			missing["blindspot.publication_delivery_tracking"] = struct{}{}
		default:
			missing["implementation.publication_delivery"] = struct{}{}
		}
	}
	return ready
}

func containsValue(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func containsKey(values map[string]struct{}, key string) bool {
	_, ok := values[key]
	return ok
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
	if !lifecycleEventConsumersReady(object) {
		missing["lifecycle.event_consumer"] = struct{}{}
		return false
	}
	if len(operations) == 0 {
		if len(runtimeEntrypoints) >= 1 {
			if len(runtimeEntrypoints) > 1 {
				missing["runtime_entrypoint.unique"] = struct{}{}
				return false
			}
			entrypoint := runtimeEntrypoints[0]
			if entrypoint.Facet == "" ||
				entrypoint.FacadeMethod == "" ||
				entrypoint.ObjectOwner != object.Name ||
				!runtimeEntrypointMatchesObject(entrypoint, object) {
				missing["runtime_entrypoint.application"] = struct{}{}
				return false
			}
			return true
		}
		// 非 HTTP projection 的入口不是伪造的 operation/runtime_entrypoint，
		// 而是 object.yaml#lifecycle 唯一 authored 的 typed projector consumer。
		// loader 已把每个 facet+method 解析到对象自身 application/adapters 中的
		// 唯一生产实现，并绑定 repo-relative path + SHA256；graph 必须逐条消费这份
		// 编译证据，不能把 consumer 的声明存在本身当成实现，也不能要求作者再复制
		// 一份 runtime_entrypoints 形成双轨。
		if lifecycleProjectorEntrypointsReady(object) {
			return true
		}
		if object.Kind == ast.ObjectKindProjection && object.Lifecycle != nil &&
			len(object.Lifecycle.EventConsumers) > 0 {
			missing["lifecycle.event_consumer"] = struct{}{}
			return false
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
			ownerCount := 0
			for _, owner := range []string{
				operation.AggregateOwner,
				operation.AppendSink,
				operation.LifecycleOwner,
			} {
				if owner != "" {
					ownerCount++
				}
			}
			if ownerCount != 1 {
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

func lifecycleProjectorEntrypointsReady(object ast.Object) bool {
	if object.Kind != ast.ObjectKindProjection || object.Lifecycle == nil ||
		len(object.Lifecycle.EventConsumers) == 0 ||
		strings.TrimSpace(object.Lifecycle.Checkpoint) == "" ||
		strings.TrimSpace(object.Lifecycle.Rebuild) == "" ||
		strings.TrimSpace(object.Lifecycle.Tombstone) == "" ||
		strings.TrimSpace(object.Lifecycle.Idempotency) == "" ||
		!lifecycleEventConsumersReady(object) {
		return false
	}
	for _, consumer := range object.Lifecycle.EventConsumers {
		if consumer.Kind != "projector" || consumer.Implementation == nil ||
			!evidenceArtifactReady(*consumer.Implementation) {
			return false
		}
	}
	return true
}

func runtimeEntrypointApplicationReady(
	object ast.Object,
	entrypoint ast.RuntimeEntrypoint,
) bool {
	return entrypoint.Facet != "" && entrypoint.FacadeMethod != "" &&
		entrypoint.ObjectOwner == object.Name &&
		runtimeEntrypointMatchesObject(entrypoint, object)
}

func runtimeEntrypointMatchesObject(
	entrypoint ast.RuntimeEntrypoint,
	object ast.Object,
) bool {
	switch entrypoint.RuntimeKind {
	case "middleware":
		return object.Kind == ast.ObjectKindRuntimeSession &&
			entrypoint.Phase == "post_authorization_pre_owner_proxy" &&
			entrypoint.ApplicationKind == ast.OperationKindSession
	case "projector":
		return object.Kind == ast.ObjectKindProjection &&
			entrypoint.Phase == "event_projection" &&
			entrypoint.ApplicationKind == ast.OperationKindCommand &&
			lifecycleConsumerMatchesEntrypoint(object, entrypoint)
	case "event_handler":
		return (object.Kind == ast.ObjectKindAggregateRoot ||
			object.Kind == ast.ObjectKindProcessManager) &&
			entrypoint.Phase == "event_command" &&
			entrypoint.ApplicationKind == ast.OperationKindCommand &&
			lifecycleConsumerMatchesEntrypoint(object, entrypoint)
	case "subscription":
		return object.Kind == ast.ObjectKindAppendOnlyFact &&
			entrypoint.Phase == "event_ingest" &&
			entrypoint.ApplicationKind == ast.OperationKindCommand &&
			lifecycleConsumerMatchesEntrypoint(object, entrypoint)
	case "internal_port":
		return object.Kind == ast.ObjectKindAppendOnlyFact &&
			entrypoint.Phase == "transactional_append" &&
			entrypoint.ApplicationKind == ast.OperationKindCommand &&
			len(entrypoint.SourceObjects) > 0 && entrypoint.Idempotency != ""
	case "external_port":
		return object.Kind == ast.ObjectKindExternalReference &&
			entrypoint.Phase == "outbound_invocation" &&
			len(entrypoint.SourceObjects) > 0 && entrypoint.Idempotency != ""
	default:
		return false
	}
}

func lifecycleEventConsumersReady(object ast.Object) bool {
	lifecycle := object.Lifecycle
	if lifecycle == nil {
		return true
	}
	if (len(lifecycle.SourceEvents) == 0) != (len(lifecycle.EventConsumers) == 0) {
		return false
	}
	seenSources := map[string]struct{}{}
	for _, sourceEvent := range lifecycle.SourceEvents {
		if !ast.IsCanonicalEventRef(sourceEvent) {
			return false
		}
		if _, duplicate := seenSources[sourceEvent]; duplicate {
			return false
		}
		seenSources[sourceEvent] = struct{}{}
	}
	seenConsumers := map[string]struct{}{}
	for _, consumer := range lifecycle.EventConsumers {
		if consumer.Name == "" || consumer.Facet == "" || consumer.Method == "" ||
			consumer.Idempotency == "" ||
			(consumer.Kind != "projector" && consumer.Kind != "event_handler" &&
				consumer.Kind != "subscription") {
			return false
		}
		// event_handler 的宿主可以是 aggregate_root 或 process_manager；saga 靠消费
		// 领域事件推进状态机，与 validate.eventConsumerOwnerKinds 保持同一闭集。
		expectedKinds := map[string][]ast.ObjectKind{
			"projector":     {ast.ObjectKindProjection},
			"event_handler": {ast.ObjectKindAggregateRoot, ast.ObjectKindProcessManager},
			"subscription":  {ast.ObjectKindAppendOnlyFact},
		}[consumer.Kind]
		matched := false
		for _, expected := range expectedKinds {
			if object.Kind == expected {
				matched = true
				break
			}
		}
		if !matched {
			return false
		}
		if _, duplicate := seenConsumers[consumer.Name]; duplicate {
			return false
		}
		seenConsumers[consumer.Name] = struct{}{}
	}
	return true
}

func lifecycleConsumerMatchesEntrypoint(
	object ast.Object,
	entrypoint ast.RuntimeEntrypoint,
) bool {
	if !lifecycleEventConsumersReady(object) || object.Lifecycle == nil {
		return false
	}
	for _, consumer := range object.Lifecycle.EventConsumers {
		if consumer.Name == entrypoint.LocalID && consumer.Kind == entrypoint.RuntimeKind &&
			consumer.Facet == entrypoint.Facet && consumer.Method == entrypoint.FacadeMethod {
			return true
		}
	}
	return false
}

func implementationEvidenceReady(
	object ast.Object,
	operations []ast.Operation,
	runtimeEntrypoints []ast.RuntimeEntrypoint,
	readinessCases []ast.ReadinessCaseContract,
	publishesDomainEvents bool,
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
	// Reader is the existing producer-separated slot for the Cloud application
	// layer. Every root kind owns an application seam; Domain is a distinct
	// obligation only for kinds that own domain state/rules.
	require("service.reader", evidence.Service.Reader)
	if objectRequiresDomainEvidence(object.Kind) {
		require("service.domain", evidence.Service.Domain)
	}
	if objectRequiresStoreEvidence(object.Kind) {
		require("service.store", evidence.Service.Store)
	}
	if object.Kind == ast.ObjectKindExternalReference &&
		!evidenceArtifactsReady(evidence.Service.Store) &&
		!evidenceArtifactsReady(evidence.Service.Transport) {
		missing["implementation.service.store_or_transport"] = struct{}{}
		ready = false
	}
	if objectHasTransportIngress(operations, runtimeEntrypoints) {
		require("service.transport", evidence.Service.Transport)
	}
	require("service.local_contract", evidence.Service.LocalContract)
	require("service.api_integration", evidence.Service.APIIntegration)
	hasCommand := false
	hasClient := false
	for _, operation := range operations {
		hasCommand = hasCommand || operation.Kind == ast.OperationKindCommand
		hasClient = hasClient || operation.ClientContract != nil
	}
	// outbox 的必需性由对象自己声明的领域事件**投递保证**派生，既不由 kind 派生，也不由
	// 「是否声明了事件」一刀切：发件箱存在的唯一理由是「状态已提交、事件却可能丢失」这一
	// 跨边界后果。声明 `events: []` 的聚合没有可发布的东西（`user.invitation` 的 events.yaml
	// 甚至写着「仓内没有 invitation outbox/publisher，禁止声明虚假 producer-consumer 链」）；
	// 声明了 `not_published` / `best_effort_ephemeral` 的聚合，事件是自留事实或尽力而为的
	// 瞬时信号，为它们建发件箱与 relay 只会造出永远没有下游的空转 relay。两种情形都是「为
	// 门禁写代码」，规则不能与契约相互否定。
	//
	// 这不是放宽：分类只认自留/瞬时语义为豁免（见 ast.ClassifyEventDelivery），而
	// `delivery_semantics` 的取值域由 schema enum 强制，所以把 `transactional_outbox` 敲错
	// 会在 schema 层直接失败，不会换来一个达标；消费侧也无法订阅未声明的事件（validate 的
	// CONTRACT.EVENT.UNKNOWN_PRODUCER 与 projector 的 source_events 解析都会拦住）。聚合
	// 完全没有 events.yaml（既没声明也没否认）由
	// `quwoquan_ops/gate/verify_object_evidence_closure.py` 在契约侧报独立缺口。
	if hasCommand && publishesDomainEvents &&
		(object.Kind == ast.ObjectKindAggregateRoot ||
			object.Kind == ast.ObjectKindProcessManager) {
		if !requirePublicationSeam(evidence, missing) {
			ready = false
		}
	}
	if hasClient {
		require("app.application", evidence.App.Application)
		require("app.adapters", evidence.App.Adapters)
		require("app.local_contract", evidence.App.LocalContract)
		require("app.api_integration", evidence.App.APIIntegration)
	}
	// A participant consumes the owning page through public application ports;
	// it does not create a second presentation root. Only the object encoded by
	// the canonical source_path physical location owns presentation and UAT.
	if evidence.App.PageOwned {
		require("app.presentation", evidence.App.Presentation)
		require("app.user_acceptance", evidence.App.UserAcceptance)
	}
	// Ops evidence is only a static runner entrypoint. It is required when the
	// object declares an Ops-owned dynamic case, but it never carries a status
	// and therefore can advance the static graph only as far as implemented.
	needEnvironmentRunner := false
	needRollbackRunner := false
	needReplayRunner := false
	for _, readinessCase := range readinessCases {
		if readinessCase.Producer != ast.ReadinessProducerOps {
			continue
		}
		switch readinessCase.Layer {
		case ast.ReadinessLayerEnvironmentAcceptance:
			needEnvironmentRunner = true
		case ast.ReadinessLayerRollback:
			needRollbackRunner = true
		case ast.ReadinessLayerReplay:
			needReplayRunner = true
		}
	}
	if needEnvironmentRunner {
		require("ops.environment_acceptance", evidence.Ops.EnvironmentAcceptance)
	}
	if needRollbackRunner {
		require("ops.rollback_runner", evidence.Ops.RollbackRunner)
	}
	if needReplayRunner {
		require("ops.replay_runner", evidence.Ops.ReplayRunner)
	}
	return ready
}

func objectRequiresDomainEvidence(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindProcessManager,
		ast.ObjectKindRuntimeSession:
		return true
	default:
		return false
	}
}

func objectRequiresStoreEvidence(kind ast.ObjectKind) bool {
	return objectRequiresDomainEvidence(kind) || kind == ast.ObjectKindProjection
}

func objectHasTransportIngress(
	operations []ast.Operation,
	runtimeEntrypoints []ast.RuntimeEntrypoint,
) bool {
	if len(operations) != 0 {
		return true
	}
	for _, entrypoint := range runtimeEntrypoints {
		// external_port is the object's outbound implementation seam. It may
		// physically live in adapters, but it is not an inbound transport.
		if entrypoint.RuntimeKind != "external_port" {
			return true
		}
	}
	return false
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

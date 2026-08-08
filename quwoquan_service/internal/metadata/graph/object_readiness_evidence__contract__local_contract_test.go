package graph_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

const syntheticDigest = "0123456789abcdef0123456789abcdef" +
	"0123456789abcdef0123456789abcdef"

func syntheticArtifact(path string) []ast.EvidenceArtifact {
	return []ast.EvidenceArtifact{{Path: path, SHA256: syntheticDigest}}
}

// syntheticCatalog 构造一个 contract-ready 的 aggregate_root，用来锁定 readiness
// stage 在 evidence 出现/缺失时的跃迁，不依赖仓库现状。
func syntheticCatalog(withClientContract bool) *ast.Catalog {
	operation := ast.Operation{
		ID:               "demo.demo_object.UpdateDemoObject",
		LocalID:          "UpdateDemoObject",
		Domain:           "demo",
		ObjectID:         "demo.demo_object",
		Method:           "POST",
		PathTemplate:     "/demo/objects/{demoObjectId}",
		Kind:             ast.OperationKindCommand,
		KindExplicit:     true,
		Facet:            "DemoObjectCommandFacet",
		FacadeMethod:     "updateDemoObject",
		AggregateOwner:   "DemoObject",
		ActorRequirement: "persona",
		AuthMode:         "required",
		Principal:        "persona",
		OwnershipPolicy:  "object_owner",
		Commercial:       ast.CommercialBinding{Status: "ready", Explicit: true},
		Reliability: ast.ReliabilityPolicy{
			TimeoutMilliseconds: 1200,
			Cancellation:        "supported",
			RetryMode:           "idempotent",
			MaxAttempts:         2,
			Idempotency:         "client_token",
		},
		ErrorCodes: []string{"DEMO.USER.demo_object_not_found"},
		Privacy: ast.PrivacyPolicy{
			RequestClassification:  "SENSITIVE",
			ResponseClassification: "SENSITIVE",
			LogPolicy:              "metadata_only",
		},
		Telemetry: ast.TelemetryPolicy{Metric: "demo_object_update", Trace: true},
		SLO: ast.SLOPolicy{
			LatencyP95Milliseconds: 500,
			AvailabilityPercent:    99.9,
		},
	}
	if withClientContract {
		operation.ClientContract = &ast.ClientContract{
			DartImport:      "package:quwoquan_cloud_contracts/demo.dart",
			ResponseType:    "DemoObject",
			ResponseDecoder: "DemoObject.fromJson",
		}
	}
	return &ast.Catalog{
		Objects: []ast.Object{{
			ID:           "demo.demo_object",
			Domain:       "demo",
			Name:         "DemoObject",
			Kind:         ast.ObjectKindAggregateRoot,
			KindExplicit: true,
			SourcePath:   "demo/demo_context/demo_object/object.yaml",
		}},
		Operations: []ast.Operation{operation},
		// 声明一条领域事件：这决定 outbox 证据是否被要求（见
		// TestOutboxRequirementFollowsDeclaredDomainEvents）。
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "demo.demo_object",
			Domain:   "demo",
			Events: []ast.EventDefinition{{
				ObjectID:          "demo.demo_object",
				Name:              "DemoObjectUpdated",
				DeliverySemantics: "transactional_outbox",
			}},
		}}},
		BusinessObjectMaps: []ast.BusinessObjectMap{{
			Domain: "demo",
			Objects: []ast.BusinessObjectBoundary{{
				CanonicalObject: "DemoObject",
				BoundedContext:  "demo_context",
				ObjectKind:      ast.ObjectKindAggregateRoot,
			}},
		}},
	}
}

// implementationEvidence 是派生 loader 输出形态的最小等价物：SourcePath 是对象实现
// 根，OperationIDs 与 contract 完全一致。
func implementationEvidence() ast.ObjectReadinessEvidence {
	return ast.ObjectReadinessEvidence{
		ObjectID:     "demo.demo_object",
		OperationIDs: []string{"demo.demo_object.UpdateDemoObject"},
		SourcePath: "quwoquan_service/services/demo-service/internal/demo_context/" +
			"demo_object",
		Service: ast.ServiceStructureEvidence{
			Domain:         syntheticArtifact("demo/domain/demo_object.go"),
			Store:          syntheticArtifact("demo/infrastructure/persistence/store.go"),
			Outbox:         publicationEvidenceArtifact("demo_objects_outbox"),
			Reader:         syntheticArtifact("demo/application/demo_facet.go"),
			Transport:      syntheticArtifact("demo/adapters/inbound/http/handler.go"),
			LocalContract:  syntheticArtifact("demo/tests/local_contract/demo.go"),
			APIIntegration: syntheticArtifact("demo/tests/api_integration/demo.go"),
		},
		// 发布 seam 的归属由 `storage.yaml` 的 `publication_role` 表达，证据绑定到存储名。
		PublicationStores: []string{"demo_objects_outbox"},
	}
}

func publicationEvidenceArtifact(storage string) []ast.StorageEvidence {
	return []ast.StorageEvidence{{
		Storage: storage,
		Artifact: ast.EvidenceArtifact{
			Path:   "demo/infrastructure/persistence/store.go",
			SHA256: syntheticDigest,
		},
	}}
}

func readinessFor(t *testing.T, catalog *ast.Catalog, objectID string) graph.ObjectReadiness {
	t.Helper()
	contractGraph := graph.Build(catalog)
	for _, readiness := range contractGraph.ObjectReadiness {
		if readiness.ObjectID == objectID {
			return readiness
		}
	}
	t.Fatalf("object %s has no derived readiness", objectID)
	return graph.ObjectReadiness{}
}

func requireMissing(t *testing.T, readiness graph.ObjectReadiness, want ...string) {
	t.Helper()
	sort.Strings(want)
	if strings.Join(readiness.Missing, "|") != strings.Join(want, "|") {
		t.Fatalf("missing=%v, want %v (stage=%s)", readiness.Missing, want, readiness.Stage)
	}
}

func TestStaticStructurePromotesToImplementedButNeverCommercialReady(t *testing.T) {
	t.Parallel()

	catalog := syntheticCatalog(false)
	before := readinessFor(t, catalog, "demo.demo_object")
	if before.Stage != "contract-ready" {
		t.Fatalf("stage=%s before evidence, want contract-ready", before.Stage)
	}
	requireMissing(t, before, "readiness.evidence")

	catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{implementationEvidence()}
	after := readinessFor(t, catalog, "demo.demo_object")
	if after.Stage != "implemented" || !after.Implemented || after.CommercialReady {
		t.Fatalf("readiness=%+v, static structure must stop at implemented", after)
	}
	requireMissing(t, after, "commercial.result_bundle")
}

func TestPureCloudObjectAllowsEmptyAppStructure(t *testing.T) {
	t.Parallel()

	catalog := syntheticCatalog(false)
	evidence := implementationEvidence()
	if len(evidence.App.Domain) != 0 || len(evidence.App.Application) != 0 ||
		len(evidence.App.Adapters) != 0 || len(evidence.App.Presentation) != 0 ||
		len(evidence.App.LocalContract) != 0 || len(evidence.App.APIIntegration) != 0 ||
		len(evidence.App.UserAcceptance) != 0 || evidence.App.PageParticipant ||
		evidence.App.PageOwned {
		t.Fatalf("synthetic pure-cloud object unexpectedly has App evidence: %+v", evidence.App)
	}
	catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}
	readiness := readinessFor(t, catalog, "demo.demo_object")
	if readiness.Stage != "implemented" || !readiness.Implemented || readiness.CommercialReady {
		t.Fatalf("readiness=%+v, pure-cloud object with empty App structure must be implemented only", readiness)
	}
	requireMissing(t, readiness, "commercial.result_bundle")
}

func TestMissingServiceLayerEvidenceKeepsObjectContractReady(t *testing.T) {
	t.Parallel()

	for name, mutate := range map[string]func(*ast.ObjectReadinessEvidence){
		"implementation.service.domain": func(e *ast.ObjectReadinessEvidence) {
			e.Service.Domain = nil
		},
		"implementation.service.store": func(e *ast.ObjectReadinessEvidence) {
			e.Service.Store = nil
		},
		"implementation.service.reader": func(e *ast.ObjectReadinessEvidence) {
			e.Service.Reader = nil
		},
		"implementation.outbox": func(e *ast.ObjectReadinessEvidence) {
			e.Service.Outbox = nil
		},
		"implementation.service.transport": func(e *ast.ObjectReadinessEvidence) {
			e.Service.Transport = nil
		},
		"implementation.service.local_contract": func(e *ast.ObjectReadinessEvidence) {
			e.Service.LocalContract = nil
		},
		"implementation.service.api_integration": func(e *ast.ObjectReadinessEvidence) {
			e.Service.APIIntegration = nil
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			catalog := syntheticCatalog(false)
			evidence := implementationEvidence()
			mutate(&evidence)
			catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}
			readiness := readinessFor(t, catalog, "demo.demo_object")
			if readiness.Stage != "contract-ready" {
				t.Fatalf("stage=%s, want contract-ready when %s is absent", readiness.Stage, name)
			}
			requireMissing(t, readiness, name)
		})
	}
}

// outbox 证据的必需性跟随对象自己的 `events.yaml` 声明，而不是 kind。发件箱的唯一职责
// 是把已声明的领域事件与状态变更同事务发布；声明 `events: []` 的聚合没有可发布的事件，
// 按 kind 一律要求只会逼出一个空发件箱。声明恢复后要求立即重新生效。
func TestOutboxRequirementFollowsDeclaredDomainEvents(t *testing.T) {
	t.Parallel()

	catalog := syntheticCatalog(false)
	catalog.Governance = ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
		ObjectID: "demo.demo_object",
		Domain:   "demo",
		Events:   nil,
	}}}
	evidence := implementationEvidence()
	evidence.Service.Outbox = nil
	catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}

	readiness := readinessFor(t, catalog, "demo.demo_object")
	if readiness.Stage != "implemented" {
		t.Fatalf("stage=%s missing=%v, 未声明领域事件的聚合不应因缺发件箱停在 contract-ready",
			readiness.Stage, readiness.Missing)
	}
}

// 发件箱要求按 `delivery_semantics` 的投递保证判定，不按「是否声明了事件」一刀切，也不看
// 当前有没有 consumer。值域由 schema enum 强制，所以笔误、topic 名和二义命名都不再是可以
// 到达这里的状态；分类函数对未知取值仍 fail-safe 到要求侧，防的是绕过 schema 的调用路径。
func TestOutboxRequirementFollowsEventDeliverySemantics(t *testing.T) {
	t.Parallel()

	for name, expectation := range map[string]struct {
		deliverySemantics string
		wantRequired      bool
	}{
		"聚合自留的事实不要求":   {deliverySemantics: "not_published"},
		"允许丢失的瞬时信号不要求": {deliverySemantics: "best_effort_ephemeral"},
		"事务性发件箱要求":     {deliverySemantics: "transactional_outbox", wantRequired: true},
		"零消费者的事务性事件表同样要求": {
			deliverySemantics: "transactional_event_log", wantRequired: true,
		},
		"直投 durable stream 要求": {
			deliverySemantics: "durable_stream",
			wantRequired:      true,
		},
		"跨边界同步调用要求": {
			deliverySemantics: "synchronous_call",
			wantRequired:      true,
		},
		// schema 拦得住的状态，规则侧仍不得把它变成豁免路径。
		"未知取值不得豁免": {
			deliverySemantics: "outbox", wantRequired: true,
		},
		"缺取值不得豁免": {
			deliverySemantics: "", wantRequired: true,
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			catalog := syntheticCatalog(false)
			catalog.Governance = ast.MetadataGovernance{
				Objects: []ast.ObjectGovernance{{
					ObjectID: "demo.demo_object",
					Domain:   "demo",
					Events: []ast.EventDefinition{{
						ObjectID:          "demo.demo_object",
						Name:              "DemoObjectUpdated",
						DeliverySemantics: expectation.deliverySemantics,
					}},
				}},
			}
			evidence := implementationEvidence()
			evidence.Service.Outbox = nil
			catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}

			readiness := readinessFor(t, catalog, "demo.demo_object")
			required := false
			for _, item := range readiness.Missing {
				if item == "implementation.outbox" {
					required = true
				}
			}
			if required != expectation.wantRequired {
				t.Fatalf("delivery_semantics=%q 要求发件箱=%v, want %v (missing=%v)",
					expectation.deliverySemantics, required,
					expectation.wantRequired, readiness.Missing)
			}
		})
	}
}

// 发布 seam 不成立有三种互不相同的原因，关闭方式各不相同（补标注 / 补声明 / 补实现），
// 所以必须是三条互斥缺口，一个对象一次只拿到一条原因。合并成一条就等于把「不知道」
// 和「知道没有」混为一谈。
func TestPublicationSeamGapsAreMutuallyExclusiveByClosureAction(t *testing.T) {
	t.Parallel()

	for name, expectation := range map[string]struct {
		mutate func(*ast.ObjectReadinessEvidence)
		want   string
	}{
		"未标注 publication_role": {
			mutate: func(evidence *ast.ObjectReadinessEvidence) {
				evidence.Service.Outbox = nil
				evidence.PublicationStores = nil
				evidence.UnannotatedStores = []string{"demo_objects", "demo_objects_outbox"}
			},
			want: "contract.storage_publication_unannotated",
		},
		"标注齐全但没有发布型存储": {
			mutate: func(evidence *ast.ObjectReadinessEvidence) {
				evidence.Service.Outbox = nil
				evidence.PublicationStores = nil
				evidence.UnannotatedStores = nil
			},
			want: "contract.storage_publication_undeclared",
		},
		"声明了发布型存储但没有观测到事务性追加": {
			mutate: func(evidence *ast.ObjectReadinessEvidence) {
				evidence.Service.Outbox = nil
			},
			want: "implementation.outbox",
		},
		// 声明多张发布 seam 时逐张要证据：少一张就是少一条发布链。
		"多张发布型存储只证明了一张": {
			mutate: func(evidence *ast.ObjectReadinessEvidence) {
				evidence.PublicationStores = []string{
					"demo_objects_outbox", "demo_object_events",
				}
			},
			want: "implementation.outbox",
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			catalog := syntheticCatalog(false)
			evidence := implementationEvidence()
			expectation.mutate(&evidence)
			catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}

			readiness := readinessFor(t, catalog, "demo.demo_object")
			if readiness.Stage != "contract-ready" {
				t.Fatalf("stage=%s, want contract-ready；发布 seam 不成立不得晋级", readiness.Stage)
			}
			requireMissing(t, readiness, expectation.want)
		})
	}
}

func TestClientExposedObjectRequiresAppApplicationAdaptersAndTests(t *testing.T) {
	t.Parallel()

	catalog := syntheticCatalog(true)
	catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{implementationEvidence()}
	readiness := readinessFor(t, catalog, "demo.demo_object")
	requireMissing(t, readiness,
		"implementation.app.adapters",
		"implementation.app.api_integration",
		"implementation.app.application",
		"implementation.app.local_contract",
	)

	evidence := implementationEvidence()
	evidence.App.Application = syntheticArtifact(
		"quwoquan_app/lib/demo/demo_context/demo_object/application/facade.dart")
	evidence.App.Adapters = syntheticArtifact(
		"quwoquan_app/lib/demo/demo_context/demo_object/adapters/remote.dart")
	evidence.App.LocalContract = syntheticArtifact(
		"quwoquan_app/test/local_contract/demo/demo_object_test.dart")
	evidence.App.APIIntegration = syntheticArtifact(
		"quwoquan_app/test/api_integration/demo/demo_object_test.dart")
	catalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{evidence}
	promoted := readinessFor(t, catalog, "demo.demo_object")
	if promoted.Stage != "implemented" || promoted.CommercialReady {
		t.Fatalf(
			"stage=%s commercialReady=%v missing=%v, want static implemented",
			promoted.Stage,
			promoted.CommercialReady,
			promoted.Missing,
		)
	}
	requireMissing(t, promoted, "commercial.result_bundle")
}

// 多对象页面参与者只经公开 application port 参与，不会因参与关系伪造第二个
// presentation owner。只有 canonical source_path 归属的 PageOwned 对象要求 presentation + UAT。
func TestPageParticipantDoesNotRequirePresentationButPageOwnerDoes(t *testing.T) {
	t.Parallel()

	participant := implementationEvidence()
	participant.App.PageParticipant = true
	participantCatalog := syntheticCatalog(false)
	participantCatalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{participant}
	participantReadiness := readinessFor(t, participantCatalog, "demo.demo_object")
	if participantReadiness.Stage != "implemented" {
		t.Fatalf("participant readiness=%+v, page participant must not require presentation", participantReadiness)
	}
	requireMissing(t, participantReadiness, "commercial.result_bundle")

	owner := implementationEvidence()
	owner.App.PageParticipant = true
	owner.App.PageOwned = true
	ownerCatalog := syntheticCatalog(false)
	ownerCatalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{owner}
	ownerReadiness := readinessFor(t, ownerCatalog, "demo.demo_object")
	if ownerReadiness.Stage != "contract-ready" {
		t.Fatalf("owner readiness=%+v, page owner without presentation/UAT must not be implemented", ownerReadiness)
	}
	requireMissing(t, ownerReadiness,
		"implementation.app.presentation",
		"implementation.app.user_acceptance",
	)

	owner.App.Presentation = syntheticArtifact(
		"quwoquan_app/lib/demo/demo_context/demo_object/presentation/page.dart")
	owner.App.UserAcceptance = syntheticArtifact(
		"quwoquan_app/integration_test/user_acceptance/demo_object_test.dart")
	ownerCatalog.ReadinessEvidence = []ast.ObjectReadinessEvidence{owner}
	implemented := readinessFor(t, ownerCatalog, "demo.demo_object")
	if implemented.Stage != "implemented" || implemented.CommercialReady {
		t.Fatalf("owner readiness=%+v, page owner with structure evidence must stop at implemented", implemented)
	}
	requireMissing(t, implemented, "commercial.result_bundle")
}

// repositoryRoot 与 contractsview 使用同一物理锚点：内部包文件位置 → service root →
// repo root。派生 evidence 需要仓库源码树，而 metadata 视图在 .qwq_output 下。
func repositoryRoot(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve repository root")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", ".."))
	return filepath.Dir(serviceRoot)
}

// TestDerivedEvidenceClosureOverRepository 是本轮的定量证据：它在真实仓库上运行派生
// loader，报告 evidence packet 数、readiness stage 分布与 missing 分布。设置
// QWQ_EVIDENCE_CLOSURE_OUTPUT 时把编译结果写到该路径，供
// `quwoquan_ops/gate/verify_object_evidence_closure.py --graph` 消费。
func TestDerivedEvidenceClosureOverRepository(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRoot(t)
	catalog, err := load.Load(contractsview.Build(t), load.WithRepoRoot(repoRoot))
	if err != nil {
		t.Fatalf("load metadata with derived evidence: %v", err)
	}
	contractGraph := graph.Build(catalog)

	packetsByObject := map[string]int{}
	for _, evidence := range contractGraph.ReadinessEvidence {
		packetsByObject[evidence.ObjectID]++
		if evidence.SourcePath == "" {
			t.Fatalf("%s: derived evidence must carry an implementation root", evidence.ObjectID)
		}
		if filepath.IsAbs(evidence.SourcePath) {
			t.Fatalf("%s: evidence sourcePath must be repository relative, got %q",
				evidence.ObjectID, evidence.SourcePath)
		}
	}
	for objectID, count := range packetsByObject {
		if count != 1 {
			t.Fatalf("%s has %d evidence packets, derivation must emit exactly one", objectID, count)
		}
	}
	if len(contractGraph.ReadinessEvidence) == 0 {
		t.Fatal("derived evidence must not be empty for the current repository")
	}

	stages := map[string]int{}
	missing := map[string]int{}
	implemented := make([]string, 0, len(contractGraph.ObjectReadiness))
	for _, readiness := range contractGraph.ObjectReadiness {
		stages[readiness.Stage]++
		for _, item := range readiness.Missing {
			missing[item]++
		}
		if readiness.Implemented {
			implemented = append(implemented, readiness.ObjectID)
		}
	}
	if missing["readiness.evidence.duplicate"] != 0 {
		t.Fatalf("derived evidence produced duplicate packets for %d object(s)",
			missing["readiness.evidence.duplicate"])
	}
	for _, key := range []string{
		"implementation.operation_coverage",
		"implementation.evidence_provenance",
	} {
		if missing[key] != 0 {
			t.Fatalf("%d object(s) report %s: derivation must satisfy it by construction",
				missing[key], key)
		}
	}
	if len(implemented) == 0 {
		t.Fatal("derived evidence promoted no object to implemented; the wiring is inert")
	}

	t.Logf("objects=%d evidencePackets=%d objectsWithoutPacket=%d",
		len(contractGraph.Objects),
		len(contractGraph.ReadinessEvidence),
		len(contractGraph.Objects)-len(contractGraph.ReadinessEvidence))
	t.Logf("stages=%s", sortedCountReport(stages))
	t.Logf("missing=%s", sortedCountReport(missing))
	t.Logf("implemented(%d)=%s", len(implemented), strings.Join(implemented, ","))

	if output := strings.TrimSpace(os.Getenv("QWQ_EVIDENCE_CLOSURE_OUTPUT")); output != "" {
		payload, marshalErr := json.MarshalIndent(contractGraph, "", " ")
		if marshalErr != nil {
			t.Fatalf("marshal contract graph: %v", marshalErr)
		}
		if err := os.MkdirAll(filepath.Dir(output), 0o755); err != nil {
			t.Fatalf("create evidence closure output directory: %v", err)
		}
		if err := os.WriteFile(output, payload, 0o644); err != nil {
			t.Fatalf("write evidence closure output: %v", err)
		}
		t.Logf("wrote derived contract graph to %s", output)
	}
}

func sortedCountReport(counts map[string]int) string {
	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool {
		if counts[keys[i]] != counts[keys[j]] {
			return counts[keys[i]] > counts[keys[j]]
		}
		return keys[i] < keys[j]
	})
	report := make([]string, 0, len(keys))
	for _, key := range keys {
		report = append(report, key+"="+strconv.Itoa(counts[key]))
	}
	return strings.Join(report, " ")
}

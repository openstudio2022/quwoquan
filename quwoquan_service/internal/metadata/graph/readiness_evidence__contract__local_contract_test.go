// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-001
package graph

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestCoverageReportsStaticReadinessOnlyThroughImplemented(t *testing.T) {
	t.Parallel()

	contractGraph := &ContractGraph{
		Objects: []ast.Object{{ID: "test.one"}, {ID: "test.two"}, {ID: "test.three"}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{
			{ObjectID: "test.two"},
			{ObjectID: "test.two"},
		},
		ObjectReadiness: []ObjectReadiness{
			{ObjectID: "test.one", Stage: "modeled", Modeled: true},
			{
				ObjectID: "test.two", Stage: "contract-ready", Modeled: true,
				ContractReady: true,
			},
			{
				ObjectID: "test.three", Stage: "implemented", Modeled: true,
				ContractReady: true, Implemented: true,
			},
		},
	}

	coverage := contractGraph.Coverage()
	if coverage.ReadinessEvidencePackets != 2 || coverage.ReadinessEvidenceObjects != 1 {
		t.Fatalf("evidence coverage=%+v, want two packets bound to one object", coverage)
	}
	if coverage.ReadinessModeled != 3 || coverage.ReadinessContractReady != 2 ||
		coverage.ReadinessImplemented != 1 || coverage.ReadinessCommercialReady != 0 {
		t.Fatalf("cumulative readiness=%+v", coverage)
	}
	if coverage.ObjectsByReadiness["modeled"] != 1 ||
		coverage.ObjectsByReadiness["contract-ready"] != 1 ||
		coverage.ObjectsByReadiness["implemented"] != 1 {
		t.Fatalf("exclusive stage distribution=%v", coverage.ObjectsByReadiness)
	}
	if coverage.ObjectsByReadiness["commercial-ready"] != 0 {
		t.Fatalf("static graph reported commercial-ready stage: %v", coverage.ObjectsByReadiness)
	}
}

func TestCoverageExcludesInfrastructureProbesFromPublicOperations(t *testing.T) {
	t.Parallel()

	for _, path := range []string{
		"/health", "/healthz", "/readyz", "/metrics", "/livez", "/startupz",
	} {
		if isPublicTransportPath(path) {
			t.Errorf("infrastructure probe %q counted as a public business operation", path)
		}
	}
	if !isPublicTransportPath("/content/posts") {
		t.Fatal("public business route was excluded from public operations")
	}
}

func TestImplementationEvidenceRequiresExactOperationsAndContentDigests(t *testing.T) {
	t.Parallel()

	operation := ast.Operation{
		ID: "test.sample.CreateSample", LocalID: "CreateSample",
		Kind: ast.OperationKindCommand,
	}
	evidence := completeImplementationEvidence(operation.ID)
	missing := map[string]struct{}{}
	if !implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		nil,
		true,
		evidence,
		missing,
	) {
		t.Fatalf("complete evidence rejected: %v", missing)
	}

	evidence.OperationIDs = nil
	missing = map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		nil,
		true,
		evidence,
		missing,
	) {
		t.Fatal("evidence without operation coverage was accepted")
	}
	if _, exists := missing["implementation.operation_coverage"]; !exists {
		t.Fatalf("missing=%v, want operation coverage failure", missing)
	}

	evidence = completeImplementationEvidence(operation.ID)
	evidence.Service.LocalContract[0].SHA256 = "not-a-content-digest"
	missing = map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		nil,
		true,
		evidence,
		missing,
	) {
		t.Fatal("evidence with an invalid digest was accepted")
	}
	if _, exists := missing["implementation.service.local_contract"]; !exists {
		t.Fatalf("missing=%v, want local contract digest failure", missing)
	}
}

// outbox 的必需性由对象自己的领域事件声明派生，不由 kind 派生。声明了事件的聚合必须有
// 发件箱；`events: []` 的聚合没有可发布的东西，要求它造一个空发件箱只会制造假实现。
func TestOutboxEvidenceFollowsDeclaredDomainEvents(t *testing.T) {
	t.Parallel()

	operation := ast.Operation{
		ID: "test.sample.CreateSample", LocalID: "CreateSample",
		Kind: ast.OperationKindCommand,
	}
	evidence := completeImplementationEvidence(operation.ID)
	evidence.Service.Outbox = nil

	missing := map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		nil,
		true,
		evidence,
		missing,
	) {
		t.Fatal("聚合声明了领域事件却没有发件箱证据，必须拒绝")
	}
	if _, exists := missing["implementation.outbox"]; !exists {
		t.Fatalf("missing=%v, want implementation.outbox", missing)
	}

	missing = map[string]struct{}{}
	if !implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot},
		[]ast.Operation{operation},
		nil,
		nil,
		false,
		evidence,
		missing,
	) {
		t.Fatalf("聚合未声明任何领域事件时不应要求发件箱: %v", missing)
	}
	if _, exists := missing["implementation.outbox"]; exists {
		t.Fatalf("missing=%v, 未声明事件的聚合不得记 outbox 缺口", missing)
	}
}

func TestAppendOnlyFactRequiresARealStoreForImplementedStage(t *testing.T) {
	t.Parallel()

	entrypoint := ast.RuntimeEntrypoint{ID: "test.sample.AppendSample"}
	evidence := completeImplementationEvidence(entrypoint.ID)
	evidence.Service.Store = nil
	missing := map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAppendOnlyFact}, nil,
		[]ast.RuntimeEntrypoint{entrypoint}, nil, false, evidence, missing,
	) {
		t.Fatal("append-only fact without storage evidence was promoted to implemented")
	}
	if _, exists := missing["implementation.service.store"]; !exists {
		t.Fatalf("missing=%v, want append-only service.store", missing)
	}
}

func TestDeclaredOpsCasesRequireStaticRunnerEntrypointsOnly(t *testing.T) {
	t.Parallel()

	operation := ast.Operation{
		ID: "test.sample.CreateSample", LocalID: "CreateSample",
		Kind: ast.OperationKindCommand,
	}
	cases := []ast.ReadinessCaseContract{
		{Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerEnvironmentAcceptance},
		{Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerRollback},
		{Producer: ast.ReadinessProducerOps, Layer: ast.ReadinessLayerReplay},
	}
	evidence := completeImplementationEvidence(operation.ID)
	missing := map[string]struct{}{}
	if implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot}, []ast.Operation{operation},
		nil, cases, false, evidence, missing,
	) {
		t.Fatal("declared Ops cases without runner entrypoints were promoted to implemented")
	}
	for _, key := range []string{
		"implementation.ops.environment_acceptance",
		"implementation.ops.rollback_runner",
		"implementation.ops.replay_runner",
	} {
		if _, exists := missing[key]; !exists {
			t.Fatalf("missing=%v, want %s", missing, key)
		}
	}

	evidence.Ops.EnvironmentAcceptance = []ast.EvidenceArtifact{validEvidenceArtifact("env.py")}
	evidence.Ops.RollbackRunner = []ast.EvidenceArtifact{validEvidenceArtifact("rollback.py")}
	evidence.Ops.ReplayRunner = []ast.EvidenceArtifact{validEvidenceArtifact("replay.py")}
	missing = map[string]struct{}{}
	if !implementationEvidenceReady(
		ast.Object{Kind: ast.ObjectKindAggregateRoot}, []ast.Operation{operation},
		nil, cases, false, evidence, missing,
	) {
		t.Fatalf("complete static runner entrypoints rejected: %v", missing)
	}
}

func TestDuplicateEvidenceCannotPromoteObject(t *testing.T) {
	t.Parallel()

	evidence := completeImplementationEvidence("test.sample.ProjectSample")
	contractGraph := Build(&ast.Catalog{
		Objects: []ast.Object{{
			ID: "test.sample", Domain: "test", Name: "Sample",
			Kind: ast.ObjectKindProjection, KindExplicit: true,
			Lifecycle: &ast.LifecycleDefinition{
				SourceEvents: []string{"test.sample_source.SampleObserved"},
				Checkpoint: "sample_sequence", Rebuild: "replay_sample_events",
				Tombstone: "delete_sample_keep_checkpoint",
				EventConsumers: []ast.LifecycleEventConsumer{{
					Name: "ProjectSample", Kind: "projector", Facet: "SampleProjector",
					Method: "apply", Idempotency: "aggregate_version",
				}},
			},
		}},
		RuntimeEntrypoints: []ast.RuntimeEntrypoint{{
			ID: "test.sample.ProjectSample", LocalID: "ProjectSample",
			Domain: "test", ObjectID: "test.sample", RuntimeKind: "projector",
			Phase: "event_projection", ApplicationKind: ast.OperationKindCommand,
			Facet: "SampleProjector", FacadeMethod: "apply", ObjectOwner: "Sample",
		}},
		BusinessObjectMaps: []ast.BusinessObjectMap{{
			Domain:  "test",
			Objects: []ast.BusinessObjectBoundary{{CanonicalObject: "Sample"}},
		}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{evidence, evidence},
	})

	readiness := contractGraph.ObjectReadiness[0]
	if readiness.Implemented || readiness.Stage != "contract-ready" {
		t.Fatalf("duplicate evidence promoted object: %+v", readiness)
	}
	if len(readiness.Missing) != 1 || readiness.Missing[0] != "readiness.evidence.duplicate" {
		t.Fatalf("missing=%v, want duplicate evidence failure", readiness.Missing)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-002
//
// 端侧对象目录搬迁期内 readiness 证据仍如实派生：装载不中断、不写占位证据，云侧证据同时
// 从领域服务与 control-plane 两处对象层根解析，端侧缺失路径记为无证据并由
// `objectReadiness.missing` 如实暴露。静态图不携带环境结果，因此最高只能到 implemented。
// 断言以「缺失即暴露」的条件形式表达，所以端侧搬迁推进时它不会失效。
func TestMigratingAppTreeStillDerivesTruthfulEvidence(t *testing.T) {
	t.Parallel()

	repoRoot := contractsview.RepositoryRoot(t)
	catalog, err := load.Load(contractsview.Build(t), load.WithRepoRoot(repoRoot))
	if err != nil {
		t.Fatalf("端侧目录搬迁中不得 fail-fast 中断 metadata 装载: %v", err)
	}
	contractGraph := Build(catalog)
	if len(contractGraph.ReadinessEvidence) == 0 {
		t.Fatal("派生器没有产出任何 evidence packet，接线是空转的")
	}

	controlPlanePackets := 0
	clientContractObjects := map[string]struct{}{}
	for _, operation := range contractGraph.Operations {
		if operation.ClientContract != nil {
			clientContractObjects[operation.ObjectID] = struct{}{}
		}
	}
	evidenceByObject := map[string]ast.ObjectReadinessEvidence{}
	for _, evidence := range contractGraph.ReadinessEvidence {
		evidenceByObject[evidence.ObjectID] = evidence
		if strings.HasPrefix(evidence.SourcePath, "quwoquan_service/control-plane/") {
			controlPlanePackets++
		}
		// 占位证据禁令：Service/App/Ops 三个 producer 的每条 artifact 都必须指向
		// 仓库里真实存在的文件。StorageEvidence 仅多一条存储关系，artifact 仍是 {path, sha256}。
		for _, artifact := range staticEvidenceArtifacts(evidence) {
			if _, statErr := os.Stat(filepath.Join(repoRoot, artifact.Path)); statErr != nil {
				t.Fatalf("%s: evidence 指向不存在的文件 %s，禁止占位证据",
					evidence.ObjectID, artifact.Path)
			}
		}
	}
	if controlPlanePackets == 0 {
		t.Fatal("没有任何 control-plane 对象层根被解析：platform_ops 上下文会被误判为无证据")
	}

	for _, readiness := range contractGraph.ObjectReadiness {
		evidence, hasEvidence := evidenceByObject[readiness.ObjectID]
		if !hasEvidence {
			continue
		}
		missing := map[string]struct{}{}
		for _, item := range readiness.Missing {
			missing[item] = struct{}{}
		}
		_, hasClient := clientContractObjects[readiness.ObjectID]
		if hasClient {
			for key, absent := range map[string]bool{
				"implementation.app.application":     len(evidence.App.Application) == 0,
				"implementation.app.adapters":        len(evidence.App.Adapters) == 0,
				"implementation.app.local_contract":  len(evidence.App.LocalContract) == 0,
				"implementation.app.api_integration": len(evidence.App.APIIntegration) == 0,
			} {
				if absent {
					if _, exposed := missing[key]; !exposed {
						t.Fatalf("%s 缺端侧结构证据却没有暴露 %s: %v",
							readiness.ObjectID, key, readiness.Missing)
					}
				}
			}
		}
		if evidence.App.PageOwned {
			for key, absent := range map[string]bool{
				"implementation.app.presentation":    len(evidence.App.Presentation) == 0,
				"implementation.app.user_acceptance": len(evidence.App.UserAcceptance) == 0,
			} {
				if absent {
					if _, exposed := missing[key]; !exposed {
						t.Fatalf("%s 缺 page-owner 证据却没有暴露 %s: %v",
							readiness.ObjectID, key, readiness.Missing)
					}
				}
			}
		} else if evidence.App.PageParticipant {
			for _, key := range []string{
				"implementation.app.presentation", "implementation.app.user_acceptance",
			} {
				if _, exposed := missing[key]; exposed {
					t.Fatalf("%s 仅是 page participant 却被要求 %s: %v",
						readiness.ObjectID, key, readiness.Missing)
				}
			}
		}
		if readiness.CommercialReady {
			t.Fatalf("%s 被静态 ContractGraph 升到 commercial-ready", readiness.ObjectID)
		}
		if readiness.Implemented {
			if _, exposed := missing["commercial.result_bundle"]; !exposed {
				t.Fatalf("%s implemented 静态图未暴露 commercial.result_bundle: %v",
					readiness.ObjectID, readiness.Missing)
			}
		}
		for _, item := range readiness.Missing {
			if strings.HasPrefix(item, "commercial.environment.") || item == "commercial.user_acceptance" {
				t.Fatalf("%s 仍携带旧静态环境缺口 %s", readiness.ObjectID, item)
			}
		}
	}
}

func completeImplementationEvidence(operationIDs ...string) ast.ObjectReadinessEvidence {
	return ast.ObjectReadinessEvidence{
		ObjectID:     "test.sample",
		OperationIDs: operationIDs,
		Service: ast.ServiceStructureEvidence{
			Domain: []ast.EvidenceArtifact{validEvidenceArtifact("domain.go")},
			Store:  []ast.EvidenceArtifact{validEvidenceArtifact("store.go")},
			// 发布 seam 证据是「存储名 → 写入位置」绑定：归属声明与事务性追加缺一不可。
			Outbox: []ast.StorageEvidence{
				publicationArtifact("store.go", "sample_outbox"),
			},
			Transport:      []ast.EvidenceArtifact{validEvidenceArtifact("handler.go")},
			LocalContract:  []ast.EvidenceArtifact{validEvidenceArtifact("local.xml")},
			APIIntegration: []ast.EvidenceArtifact{validEvidenceArtifact("api.xml")},
		},
		PublicationStores: []string{"sample_outbox"},
		SourcePath:        "evidence/object.json",
	}
}

func validEvidenceArtifact(path string) ast.EvidenceArtifact {
	return ast.EvidenceArtifact{Path: path, SHA256: strings.Repeat("a", 64)}
}

func publicationArtifact(path string, storage string) ast.StorageEvidence {
	return ast.StorageEvidence{Storage: storage, Artifact: validEvidenceArtifact(path)}
}

func staticEvidenceArtifacts(evidence ast.ObjectReadinessEvidence) []ast.EvidenceArtifact {
	artifacts := make([]ast.EvidenceArtifact, 0)
	for _, values := range [][]ast.EvidenceArtifact{
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
		artifacts = append(artifacts, values...)
	}
	for _, binding := range evidence.Service.Outbox {
		artifacts = append(artifacts, binding.Artifact)
	}
	for _, binding := range evidence.PublicationDelivery {
		artifacts = append(artifacts, binding.Artifact)
	}
	return artifacts
}

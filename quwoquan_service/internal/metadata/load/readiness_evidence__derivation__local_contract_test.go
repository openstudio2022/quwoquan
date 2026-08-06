package load_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/load"
)

// syntheticRepo 是派生规则的最小物理真相源：一个服务、一个 context、一个对象，
// 端云与 Ops 三棵树都按目标形态摆放。测试只断言派生规则本身，不依赖仓库现状。
type syntheticRepo struct {
	root        string
	metadataDir string
}

func newSyntheticRepo(t *testing.T, kind ast.ObjectKind) syntheticRepo {
	t.Helper()
	repo := syntheticRepo{
		root:        t.TempDir(),
		metadataDir: t.TempDir(),
	}
	serviceRoot := filepath.Join(
		repo.root, "quwoquan_service", "services", "demo-service",
	)
	objectRoot := filepath.Join(serviceRoot, "internal", "demo_context", "demo_object")

	repo.write(t, filepath.Join(serviceRoot, "contracts", "domain.yaml"), "domain: demo\n")
	// 发布 seam 的归属只由对象自己 `storage.yaml` 的 `publication_role` 表达；文件名与
	// 目录位置都不表达归属。
	repo.write(
		t,
		filepath.Join(serviceRoot, "contracts", "demo_context", "demo_object", "storage.yaml"),
		"backend: postgres\nrole: authoritative\n"+
			"tables:\n"+
			"  demo_objects:\n    publication_role: not_published\n"+
			"  demo_object_outbox:\n    publication_role: transactional_outbox\n",
	)
	repo.write(t, filepath.Join(objectRoot, "domain", "demo_object.go"), "package domain\n")
	repo.write(
		t,
		filepath.Join(objectRoot, "application", "demo_facet.go"),
		"package application\n",
	)
	// 真实性由「服务内对这张存储的事务性追加」证明：函数持有事务句柄并写入该关系。
	// 文件名故意不含 outbox，与 gathering 把发件箱追加内联在聚合 store 里的真实形态一致。
	repo.write(
		t,
		filepath.Join(objectRoot, "infrastructure", "persistence", "postgres_store.go"),
		"package persistence\n\nimport (\n\t\"context\"\n\n"+
			"\t\"github.com/jackc/pgx/v5\"\n)\n\n"+
			"func appendEvent(ctx context.Context, tx pgx.Tx, payload []byte) error {\n"+
			"\t_, err := tx.Exec(ctx, "+
			"`INSERT INTO demo_object_outbox(id, payload) VALUES ($1, $2)`, payload)\n"+
			"\treturn err\n}\n",
	)
	repo.write(
		t,
		filepath.Join(objectRoot, "adapters", "inbound", "http", "handler.go"),
		"package http\n",
	)
	// production 扫描必须排除同层的测试文件与测试替身。
	repo.write(
		t,
		filepath.Join(objectRoot, "domain", "demo_object_test.go"),
		"package domain\n",
	)
	repo.write(
		t,
		filepath.Join(objectRoot, "infrastructure", "testsupport", "fake_store.go"),
		"package testsupport\n",
	)

	repo.write(
		t,
		filepath.Join(
			serviceRoot, "tests", "local_contract", "demo_context", "demo_object",
			"demo__local_contract_test.go",
		),
		"package local_contract\n",
	)
	repo.write(
		t,
		filepath.Join(
			serviceRoot, "tests", "api_integration", "demo_context", "demo_object",
			"demo__api_integration_test.go",
		),
		"package api_integration\n",
	)

	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_app", "lib", "service", "demo_service",
			"demo_context", "demo_object", "domain", "demo_object.dart",
		),
		"// domain model\n",
	)
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_app", "lib", "service", "demo_service",
			"demo_context", "demo_object", "application", "demo_object_facade.dart",
		),
		"// application facade\n",
	)
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_app", "lib", "service", "demo_service",
			"demo_context", "demo_object", "adapters", "demo_object_remote.dart",
		),
		"// remote adapter\n",
	)
	for _, layer := range []string{"local_contract", "api_integration", "user_acceptance"} {
		repo.write(
			t,
			filepath.Join(
				repo.root, "quwoquan_app", "test", layer, "service", "demo_service",
				"demo_context", "demo_object", "demo__"+layer+"_test.dart",
			),
			"// "+layer+" entrypoint\n",
		)
	}
	for _, layer := range []string{"environment_acceptance", "rollback", "replay"} {
		repo.write(
			t,
			filepath.Join(
				repo.root, "quwoquan_ops", "tests", "acceptance", layer, "demo",
				"demo_context", "demo_object", "demo__"+layer+"_test.py",
			),
			"# "+layer+" runner\n",
		)
	}
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_app", "lib", "service", "demo_service",
			"demo_context", "demo_object", "presentation", "demo_object_page.dart",
		),
		"// page\n",
	)
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_service", "contracts", "metadata", "_shared",
			"page_object_contract.yaml",
		),
		"source_path_root: quwoquan_app\n"+
			"pages:\n"+
			"  - page_id: demo.object_page\n"+
			"    source_path: lib/service/demo_service/demo_context/demo_object/presentation/"+
			"demo_object_page.dart\n"+
			"    object_ids: [demo.demo_object]\n"+
			"  - page_id: demo.missing_page\n"+
			"    source_path: lib/service/demo_service/demo_context/demo_object/presentation/absent.dart\n"+
			"    object_ids: [demo.demo_object]\n",
	)

	repo.write(
		t,
		filepath.Join(repo.metadataDir, "demo", "demo_context", "context.yaml"),
		"role: core\n"+
			"access:\n"+
			"  child_objects: aggregate_root_only\n"+
			"  commands: aggregate_facade_only\n"+
			"  cross_context: public_contract_only\n"+
			"  queries: named_reader_slice_only\n",
	)
	repo.write(
		t,
		filepath.Join(repo.metadataDir, "demo", "demo_context", "demo_object", "object.yaml"),
		"kind: "+string(kind)+"\n"+
			"identity:\n"+
			"  fields: [demoObjectId]\n"+
			"access:\n"+
			"  commands: aggregate_facade_only\n"+
			"  queries: named_reader_slice_only\n"+
			"  cross_context: public_contract_only\n",
	)
	return repo
}

func (repo syntheticRepo) write(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("create %s: %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func (repo syntheticRepo) load(t *testing.T, options ...load.Option) *ast.Catalog {
	t.Helper()
	catalog, err := load.Load(repo.metadataDir, options...)
	if err != nil {
		t.Fatalf("load metadata: %v", err)
	}
	return catalog
}

func onlyEvidence(t *testing.T, catalog *ast.Catalog) ast.ObjectReadinessEvidence {
	t.Helper()
	if len(catalog.ReadinessEvidence) != 1 {
		t.Fatalf("evidence packets=%d, want exactly one per object", len(catalog.ReadinessEvidence))
	}
	return catalog.ReadinessEvidence[0]
}

func evidenceByObject(
	t *testing.T,
	catalog *ast.Catalog,
	objectID string,
) ast.ObjectReadinessEvidence {
	t.Helper()
	for _, evidence := range catalog.ReadinessEvidence {
		if evidence.ObjectID == objectID {
			return evidence
		}
	}
	t.Fatalf("readiness evidence for %s not found: %+v", objectID, catalog.ReadinessEvidence)
	return ast.ObjectReadinessEvidence{}
}

func artifactPaths(values []ast.EvidenceArtifact) []string {
	paths := make([]string, 0, len(values))
	for _, value := range values {
		paths = append(paths, value.Path)
	}
	return paths
}

func requireArtifacts(t *testing.T, field string, got []ast.EvidenceArtifact, want ...string) {
	t.Helper()
	gotPaths := artifactPaths(got)
	if strings.Join(gotPaths, "|") != strings.Join(want, "|") {
		t.Fatalf("%s=%v, want %v", field, gotPaths, want)
	}
	for _, artifact := range got {
		if len(artifact.SHA256) != 64 {
			t.Fatalf("%s artifact %s digest=%q, want 64 hex characters", field, artifact.Path, artifact.SHA256)
		}
		for _, character := range artifact.SHA256 {
			if (character < '0' || character > '9') && (character < 'a' || character > 'f') {
				t.Fatalf("%s artifact %s digest is not lowercase hex: %q", field, artifact.Path, artifact.SHA256)
			}
		}
	}
}

func requireStorageArtifacts(
	t *testing.T,
	field string,
	got []ast.StorageEvidence,
	wantStorage string,
	wantPaths ...string,
) {
	t.Helper()
	artifacts := make([]ast.EvidenceArtifact, 0, len(got))
	for _, binding := range got {
		if binding.Storage != wantStorage {
			t.Fatalf("%s storage=%q, want %q", field, binding.Storage, wantStorage)
		}
		artifacts = append(artifacts, binding.Artifact)
	}
	requireArtifacts(t, field, artifacts, wantPaths...)
}

// 不带 WithRepoRoot 时 Load 只读 YAML，不做任何物理派生。fail-closed 的边界在 CLI：
// `tools/qwq_contract` 的每个会走 Load 的子命令都要求 `--repo-root`，见
// TestLoadBearingSubcommandsRejectMissingRepoRoot。
func TestLoadWithoutRepoRootDerivesNoEvidence(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	catalog := repo.load(t)
	if len(catalog.ReadinessEvidence) != 0 {
		t.Fatalf("evidence=%+v, want none without an explicit repository root", catalog.ReadinessEvidence)
	}
}

func TestDerivedEvidenceBindsPhysicalLayersAndTests(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

	if evidence.ObjectID != "demo.demo_object" {
		t.Fatalf("objectId=%q", evidence.ObjectID)
	}
	objectRoot := "quwoquan_service/services/demo-service/internal/demo_context/demo_object"
	if evidence.SourcePath != objectRoot {
		t.Fatalf("sourcePath=%q, want the object implementation root %q", evidence.SourcePath, objectRoot)
	}
	requireArtifacts(t, "service.domain", evidence.Service.Domain,
		objectRoot+"/domain/demo_object.go")
	requireArtifacts(t, "service.reader", evidence.Service.Reader,
		objectRoot+"/application/demo_facet.go")
	requireArtifacts(t, "service.store", evidence.Service.Store,
		objectRoot+"/infrastructure/persistence/postgres_store.go")
	requireArtifacts(t, "service.transport", evidence.Service.Transport,
		objectRoot+"/adapters/inbound/http/handler.go")
	// 发布 seam 证据是「存储名 → 写入位置」的绑定：归属来自 storage.yaml 的
	// `publication_role`，写入位置来自服务内的事务性追加。
	requireStorageArtifacts(t, "service.outbox", evidence.Service.Outbox,
		"demo_object_outbox",
		objectRoot+"/infrastructure/persistence/postgres_store.go")
	if strings.Join(evidence.PublicationStores, "|") != "demo_object_outbox" {
		t.Fatalf("publicationStores=%v, want [demo_object_outbox]", evidence.PublicationStores)
	}
	if len(evidence.UnannotatedStores) != 0 {
		t.Fatalf("unannotatedStores=%v, want empty", evidence.UnannotatedStores)
	}
	requireArtifacts(t, "service.localContract", evidence.Service.LocalContract,
		"quwoquan_service/services/demo-service/tests/local_contract/demo_context/"+
			"demo_object/demo__local_contract_test.go")
	requireArtifacts(t, "service.apiIntegration", evidence.Service.APIIntegration,
		"quwoquan_service/services/demo-service/tests/api_integration/demo_context/"+
			"demo_object/demo__api_integration_test.go")
	requireArtifacts(t, "app.domain", evidence.App.Domain,
		"quwoquan_app/lib/service/demo_service/demo_context/demo_object/domain/demo_object.dart")
	requireArtifacts(t, "app.application", evidence.App.Application,
		"quwoquan_app/lib/service/demo_service/demo_context/demo_object/application/demo_object_facade.dart")
	requireArtifacts(t, "app.adapters", evidence.App.Adapters,
		"quwoquan_app/lib/service/demo_service/demo_context/demo_object/adapters/demo_object_remote.dart")
	// 契约认领了两个页面，其中一个不在磁盘上：认领成立，证据只包含真实存在的页面。
	if !evidence.App.PageParticipant || !evidence.App.PageOwned {
		t.Fatalf("pageParticipant=%v pageOwned=%v, want both true for the physical owner",
			evidence.App.PageParticipant, evidence.App.PageOwned)
	}
	requireArtifacts(t, "app.presentation", evidence.App.Presentation,
		"quwoquan_app/lib/service/demo_service/demo_context/demo_object/presentation/demo_object_page.dart")
	requireArtifacts(t, "app.localContract", evidence.App.LocalContract,
		"quwoquan_app/test/local_contract/service/demo_service/demo_context/demo_object/"+
			"demo__local_contract_test.dart")
	requireArtifacts(t, "app.apiIntegration", evidence.App.APIIntegration,
		"quwoquan_app/test/api_integration/service/demo_service/demo_context/demo_object/"+
			"demo__api_integration_test.dart")
	requireArtifacts(t, "app.userAcceptance", evidence.App.UserAcceptance,
		"quwoquan_app/test/user_acceptance/service/demo_service/demo_context/demo_object/"+
			"demo__user_acceptance_test.dart")
	requireArtifacts(t, "ops.environmentAcceptance", evidence.Ops.EnvironmentAcceptance,
		"quwoquan_ops/tests/acceptance/environment_acceptance/demo/demo_context/demo_object/"+
			"demo__environment_acceptance_test.py")
	requireArtifacts(t, "ops.rollbackRunner", evidence.Ops.RollbackRunner,
		"quwoquan_ops/tests/acceptance/rollback/demo/demo_context/demo_object/"+
			"demo__rollback_test.py")
	requireArtifacts(t, "ops.replayRunner", evidence.Ops.ReplayRunner,
		"quwoquan_ops/tests/acceptance/replay/demo/demo_context/demo_object/"+
			"demo__replay_test.py")
}

func TestDerivedEvidenceUsesApplicationBehaviorForProjection(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindProjection)
	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

	objectRoot := "quwoquan_service/services/demo-service/internal/demo_context/demo_object"
	requireArtifacts(t, "service.domain", evidence.Service.Domain,
		objectRoot+"/application/demo_facet.go")
}

func TestDerivedEvidenceKeepsPageClaimWhenPageFileIsAbsent(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	if err := os.Remove(filepath.Join(
		repo.root, "quwoquan_app", "lib", "service", "demo_service",
		"demo_context", "demo_object", "presentation", "demo_object_page.dart",
	)); err != nil {
		t.Fatalf("remove page file: %v", err)
	}
	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

	if !evidence.App.PageParticipant || !evidence.App.PageOwned {
		t.Fatalf(
			"pageParticipant=%v pageOwned=%v, want ownership requirement to survive missing bytes",
			evidence.App.PageParticipant,
			evidence.App.PageOwned,
		)
	}
	if len(evidence.App.Presentation) != 0 {
		t.Fatalf("presentation=%v, want no artifact for a page that is not on disk",
			artifactPaths(evidence.App.Presentation))
	}
}

func TestDerivedEvidenceLeavesUnclaimedObjectWithoutPageRequirement(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_service", "contracts", "metadata", "_shared",
			"page_object_contract.yaml",
		),
		"source_path_root: quwoquan_app\npages: []\n",
	)
	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

	if evidence.App.PageParticipant || evidence.App.PageOwned ||
		len(evidence.App.Presentation) != 0 {
		t.Fatalf(
			"pageParticipant=%v pageOwned=%v presentation=%v, want no page requirement",
			evidence.App.PageParticipant,
			evidence.App.PageOwned,
			artifactPaths(evidence.App.Presentation),
		)
	}
}

func TestDerivedEvidenceSeparatesPageParticipantFromPhysicalOwner(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	serviceRoot := filepath.Join(
		repo.root, "quwoquan_service", "services", "demo-service",
	)
	repo.write(
		t,
		filepath.Join(
			serviceRoot, "internal", "demo_context", "demo_participant",
			"application", "participant_reader.go",
		),
		"package application\n",
	)
	repo.write(
		t,
		filepath.Join(
			repo.metadataDir, "demo", "demo_context", "demo_participant", "object.yaml",
		),
		"kind: projection\n"+
			"identity:\n"+
			"  fields: [demoParticipantId]\n"+
			"access:\n"+
			"  commands: aggregate_facade_only\n"+
			"  queries: named_reader_slice_only\n"+
			"  cross_context: public_contract_only\n",
	)
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_service", "contracts", "metadata", "_shared",
			"page_object_contract.yaml",
		),
		"source_path_root: quwoquan_app\n"+
			"pages:\n"+
			"  - page_id: demo.object_page\n"+
			"    source_path: lib/service/demo_service/demo_context/demo_object/presentation/"+
			"demo_object_page.dart\n"+
			"    object_ids: [demo.demo_participant]\n",
	)

	catalog := repo.load(t, load.WithRepoRoot(repo.root))
	owner := evidenceByObject(t, catalog, "demo.demo_object")
	participant := evidenceByObject(t, catalog, "demo.demo_participant")

	if owner.App.PageParticipant || !owner.App.PageOwned {
		t.Fatalf("physical owner flags: participant=%v owned=%v, want false/true",
			owner.App.PageParticipant, owner.App.PageOwned)
	}
	requireArtifacts(t, "owner.app.presentation", owner.App.Presentation,
		"quwoquan_app/lib/service/demo_service/demo_context/demo_object/presentation/demo_object_page.dart")
	if !participant.App.PageParticipant || participant.App.PageOwned {
		t.Fatalf("page participant flags: participant=%v owned=%v, want true/false",
			participant.App.PageParticipant, participant.App.PageOwned)
	}
	if len(participant.App.Presentation) != 0 {
		t.Fatalf("participant presentation=%v, want empty: participation must not imply ownership",
			artifactPaths(participant.App.Presentation))
	}
}

func TestDerivedEvidenceAllowsCloudOnlyObjectWithEmptyAppEvidence(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	// 纯云对象既没有 App operation/page owner，也没有 App/Ops 物理树。loader 必须
	// 派生空 producer packet，而不是要求占位目录或拒绝整个 catalog。
	repo.write(
		t,
		filepath.Join(
			repo.root, "quwoquan_service", "contracts", "metadata", "_shared",
			"page_object_contract.yaml",
		),
		"source_path_root: quwoquan_app\npages: []\n",
	)
	if err := os.RemoveAll(filepath.Join(repo.root, "quwoquan_app")); err != nil {
		t.Fatalf("remove app tree: %v", err)
	}
	if err := os.RemoveAll(filepath.Join(repo.root, "quwoquan_ops")); err != nil {
		t.Fatalf("remove ops tree: %v", err)
	}
	evidence := onlyEvidence(t, repo.load(t, load.WithRepoRoot(repo.root)))

	if len(evidence.App.Domain) != 0 || len(evidence.App.Application) != 0 ||
		len(evidence.App.Adapters) != 0 || len(evidence.App.Presentation) != 0 ||
		len(evidence.App.LocalContract) != 0 || len(evidence.App.APIIntegration) != 0 ||
		len(evidence.App.UserAcceptance) != 0 || evidence.App.PageParticipant ||
		evidence.App.PageOwned {
		t.Fatalf("app evidence=%+v, want an empty producer packet for a cloud-only object", evidence.App)
	}
	if len(evidence.Service.Domain) == 0 || len(evidence.Service.Transport) == 0 {
		t.Fatalf("service evidence must survive an absent app tree: %+v", evidence.Service)
	}
	if len(evidence.Ops.EnvironmentAcceptance) != 0 ||
		len(evidence.Ops.RollbackRunner) != 0 || len(evidence.Ops.ReplayRunner) != 0 {
		t.Fatalf("ops evidence=%+v, want empty after removing the Ops tree", evidence.Ops)
	}
}

func TestDerivedEvidenceSkipsObjectsWithoutImplementationRoot(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	if err := os.RemoveAll(filepath.Join(
		repo.root, "quwoquan_service", "services", "demo-service", "internal",
	)); err != nil {
		t.Fatalf("remove internal tree: %v", err)
	}
	catalog := repo.load(t, load.WithRepoRoot(repo.root))
	if len(catalog.ReadinessEvidence) != 0 {
		t.Fatalf("evidence=%+v, want no packet when the object has no implementation root", catalog.ReadinessEvidence)
	}
}

func TestDerivedEvidenceRejectsMultipleImplementationOwners(t *testing.T) {
	t.Parallel()

	repo := newSyntheticRepo(t, ast.ObjectKindAggregateRoot)
	rivalRoot := filepath.Join(
		repo.root, "quwoquan_service", "services", "rival-service",
	)
	repo.write(t, filepath.Join(rivalRoot, "contracts", "domain.yaml"), "domain: demo\n")
	repo.write(
		t,
		filepath.Join(
			rivalRoot, "internal", "demo_context", "demo_object", "domain", "clone.go",
		),
		"package domain\n",
	)

	if _, err := load.Load(repo.metadataDir, load.WithRepoRoot(repo.root)); err == nil {
		t.Fatal("two services owning the same object implementation root must fail the load")
	}
}

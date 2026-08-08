package load

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

const (
	contractViewTestSpecRef = "specs/feature-tree/" +
		"runtime/demo/spec.md#gwt-001"
	contractViewTestRunner = "quwoquan_service/services/demo-service/tests/api_integration/demo_context/demo_object/demo__api_integration_test.go"
)

type contractViewFixture struct {
	root             string
	metadataDir      string
	viewOperations   string
	sourceOperations string
}

func newContractViewFixture(t *testing.T) contractViewFixture {
	t.Helper()
	root := t.TempDir()
	fixture := contractViewFixture{
		root: root,
		metadataDir: filepath.Join(
			root, ".qwq_output", "env", "repo", "local",
			"test-contract-views", "cache", "run", "metadata",
		),
		sourceOperations: filepath.Join(
			root, "quwoquan_service", "services", "demo-service", "contracts",
			"demo_context", "demo_object", "operations.yaml",
		),
	}
	fixture.viewOperations = filepath.Join(
		fixture.metadataDir, "demo", "demo_context", "demo_object", "operations.yaml",
	)
	writeContractViewFixtureFile(t, fixture.sourceOperations, "api_routes: []\n")
	writeContractViewFixtureFile(t, fixture.viewOperations, "api_routes: []\n")
	writeContractViewFixtureFile(
		t,
		filepath.Join(root, "specs", "feature-tree", "runtime", "demo", "spec.md"),
		"# Demo\n\n<a id=\"gwt-001\"></a>\n### GWT-001\n",
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(root, filepath.FromSlash(contractViewTestRunner)),
		"// spec_ref: "+contractViewTestSpecRef+"\n"+
			"// readiness_case: demo-ready\npackage demo_object_test\n",
	)
	writeContractViewFixtureManifest(t, fixture, filepath.ToSlash(strings.TrimPrefix(
		fixture.sourceOperations,
		root+string(filepath.Separator),
	)))
	return fixture
}

func TestContractViewProvenanceKeepsSnapshotBytesAndCanonicalReadinessOwner(t *testing.T) {
	fixture := newContractViewFixture(t)
	provenance, err := loadContractViewProvenance(fixture.metadataDir)
	if err != nil {
		t.Fatalf("load contract view provenance: %v", err)
	}
	if err := validateReadinessRunnerSource(
		fixture.root,
		fixture.viewOperations,
		contractViewTestRunner,
		ast.Object{ID: "demo.demo_object", Domain: "demo"},
		ast.ReadinessProducerService,
		ast.ReadinessLayerAPIIntegration,
		contractViewTestSpecRef,
		"demo-ready",
		provenance,
	); err != nil {
		t.Fatalf("validate canonical readiness owner: %v", err)
	}

	// A writer may advance the canonical source after the view was built. The
	// running test must keep its byte snapshot while retaining canonical owner
	// identity from the manifest.
	writeContractViewFixtureFile(t, fixture.sourceOperations, "api_routes:\n  - operation: LaterWrite\n")
	provenance, err = loadContractViewProvenance(fixture.metadataDir)
	if err != nil {
		t.Fatalf("reload immutable view after canonical source advanced: %v", err)
	}
	viewBytes, err := os.ReadFile(fixture.viewOperations)
	if err != nil {
		t.Fatalf("read snapshot operations: %v", err)
	}
	if string(viewBytes) != "api_routes: []\n" {
		t.Fatalf("snapshot followed a later source write: %q", viewBytes)
	}
}

func TestContractViewProvenanceSuppliesLifecycleImplementationRoot(t *testing.T) {
	fixture := newContractViewFixture(t)
	provenance, err := loadContractViewProvenance(fixture.metadataDir)
	if err != nil {
		t.Fatalf("load contract view provenance: %v", err)
	}
	if got := lifecycleImplementationRepoRoot(settings{contractView: provenance}); got != fixture.root {
		t.Fatalf("lifecycle implementation root = %q, want %q", got, fixture.root)
	}

	explicitRoot := filepath.Join(fixture.root, "explicit-repository")
	if got := lifecycleImplementationRepoRoot(settings{
		repoRoot: explicitRoot, contractView: provenance,
	}); got != explicitRoot {
		t.Fatalf("explicit lifecycle implementation root = %q, want %q", got, explicitRoot)
	}
	if got := lifecycleImplementationRepoRoot(settings{}); got != "" {
		t.Fatalf("metadata-only lifecycle implementation root = %q, want empty", got)
	}
}

func TestLoadBindsLifecycleImplementationFromContractViewProvenance(t *testing.T) {
	fixture := newLifecycleContractViewFixture(t, true)
	catalog, err := Load(fixture.metadataDir)
	if err != nil {
		t.Fatalf("load repository-backed contract view: %v", err)
	}
	consumer := catalog.Objects[0].Lifecycle.EventConsumers[0]
	if consumer.Implementation == nil ||
		!strings.HasSuffix(consumer.Implementation.Path, "/application/handler.go") ||
		len(consumer.Implementation.SHA256) != 64 {
		t.Fatalf("lifecycle implementation was not provenance-bound: %+v", consumer)
	}
}

func TestLoadContractViewProvenanceRejectsMissingLifecycleImplementation(t *testing.T) {
	fixture := newLifecycleContractViewFixture(t, false)
	_, err := Load(fixture.metadataDir)
	if err == nil || !strings.Contains(
		err.Error(),
		"requires one concrete or interface facet DemoLifecycleHandler",
	) {
		t.Fatalf("Load error=%v, want missing lifecycle implementation", err)
	}
}

func TestContractViewProvenanceFailsClosedOnSnapshotDrift(t *testing.T) {
	fixture := newContractViewFixture(t)
	writeContractViewFixtureFile(t, fixture.viewOperations, "api_routes:\n  - operation: Tampered\n")
	_, err := loadContractViewProvenance(fixture.metadataDir)
	if err == nil || !strings.Contains(err.Error(), "drifted from its byte snapshot") {
		t.Fatalf("provenance error=%v, want snapshot drift", err)
	}
	_, err = SourceDocuments(
		fixture.metadataDir,
		[]string{"demo/demo_context/demo_object/operations.yaml"},
	)
	if err == nil || !strings.Contains(err.Error(), "drifted from its byte snapshot") {
		t.Fatalf("SourceDocuments error=%v, want snapshot drift", err)
	}
}

func TestContractViewProvenanceFailsClosedOnFileInventoryDrift(t *testing.T) {
	fixture := newContractViewFixture(t)
	writeContractViewFixtureFile(
		t,
		filepath.Join(fixture.metadataDir, "demo", "unexpected.yaml"),
		"unexpected: true\n",
	)
	_, err := loadContractViewProvenance(fixture.metadataDir)
	if err == nil || !strings.Contains(err.Error(), "file inventory differs from provenance") {
		t.Fatalf("provenance error=%v, want file inventory drift", err)
	}
}

func TestContractViewProvenanceFailsClosedWhenCanonicalSourceDisappears(t *testing.T) {
	fixture := newContractViewFixture(t)
	if err := os.Remove(fixture.sourceOperations); err != nil {
		t.Fatalf("remove canonical source fixture: %v", err)
	}
	_, err := loadContractViewProvenance(fixture.metadataDir)
	if err == nil || !strings.Contains(err.Error(), "resolve canonical source") {
		t.Fatalf("provenance error=%v, want unavailable canonical source", err)
	}
}

func TestContractViewProvenanceRejectsDisposableViewWithoutManifest(t *testing.T) {
	root := t.TempDir()
	metadataDir := filepath.Join(
		root, ".qwq_output", "env", "repo", "local",
		"service-contract-view", "cache", "run", "metadata",
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(metadataDir, "demo", "demo_context", "demo_object", "object.yaml"),
		"kind: aggregate_root\n",
	)
	_, err := Load(metadataDir)
	if err == nil || !strings.Contains(err.Error(), "missing "+contractViewProvenanceFilename) {
		t.Fatalf("Load error=%v, want missing provenance", err)
	}
}

func TestContractViewProvenanceRejectsNonObjectLocalReadinessOwner(t *testing.T) {
	fixture := newContractViewFixture(t)
	foreign := filepath.Join(
		fixture.root, "quwoquan_service", "services", "demo-service", "contracts",
		"shared", "operations.yaml",
	)
	writeContractViewFixtureFile(t, foreign, "api_routes: []\n")
	writeContractViewFixtureManifest(t, fixture, filepath.ToSlash(strings.TrimPrefix(
		foreign,
		fixture.root+string(filepath.Separator),
	)))
	provenance, err := loadContractViewProvenance(fixture.metadataDir)
	if err != nil {
		t.Fatalf("load structurally valid provenance: %v", err)
	}
	err = validateReadinessRunnerSource(
		fixture.root,
		fixture.viewOperations,
		contractViewTestRunner,
		ast.Object{ID: "demo.demo_object", Domain: "demo"},
		ast.ReadinessProducerService,
		ast.ReadinessLayerAPIIntegration,
		contractViewTestSpecRef,
		"demo-ready",
		provenance,
	)
	if err == nil || !strings.Contains(err.Error(), "not a canonical object-local Cloud contract") {
		t.Fatalf("readiness owner error=%v, want canonical object-local rejection", err)
	}
}

func writeContractViewFixtureManifest(
	t *testing.T,
	fixture contractViewFixture,
	sourcePath string,
) {
	t.Helper()
	viewPayload, err := os.ReadFile(fixture.viewOperations)
	if err != nil {
		t.Fatalf("read view operations: %v", err)
	}
	sourcePayload, err := os.ReadFile(filepath.Join(fixture.root, filepath.FromSlash(sourcePath)))
	if err != nil {
		t.Fatalf("read source operations: %v", err)
	}
	viewSHA := sha256.Sum256(viewPayload)
	sourceSHA := sha256.Sum256(sourcePayload)
	viewRelative := "demo/demo_context/demo_object/operations.yaml"
	viewDigest := sha256.New()
	_, _ = viewDigest.Write([]byte(viewRelative))
	_, _ = viewDigest.Write([]byte{0})
	_, _ = viewDigest.Write([]byte(hex.EncodeToString(viewSHA[:])))
	_, _ = viewDigest.Write([]byte{'\n'})
	document := contractViewProvenanceDocument{
		SchemaVersion: contractViewProvenanceVersion,
		ViewDigest:    hex.EncodeToString(viewDigest.Sum(nil)),
		Sources: []contractViewProvenanceSource{{
			Path: sourcePath, SHA256: hex.EncodeToString(sourceSHA[:]),
		}},
		Files: []contractViewProvenanceFile{{
			Path: viewRelative, SHA256: hex.EncodeToString(viewSHA[:]),
			SourcePaths: []string{sourcePath},
		}},
	}
	payload, err := json.Marshal(document)
	if err != nil {
		t.Fatalf("encode contract view provenance: %v", err)
	}
	writeContractViewFixtureFile(
		t,
		filepath.Join(fixture.metadataDir, contractViewProvenanceFilename),
		string(payload),
	)
}

func newLifecycleContractViewFixture(
	t *testing.T,
	withImplementation bool,
) contractViewFixture {
	t.Helper()
	root := t.TempDir()
	metadataDir := filepath.Join(
		root, ".qwq_output", "env", "repo", "local",
		"test-contract-views", "cache", "run", "metadata",
	)
	viewRelative := "demo/demo_context/demo_object/object.yaml"
	sourceRelative := "quwoquan_service/services/demo-service/contracts/" +
		"demo_context/demo_object/object.yaml"
	viewContextRelative := "demo/demo_context/context.yaml"
	sourceContextRelative := "quwoquan_service/services/demo-service/contracts/" +
		"demo_context/context.yaml"
	objectYAML := `kind: aggregate_root
description: Demo aggregate for provenance-bound lifecycle implementation tests.
identity:
  fields: [id]
  version_source: store_commit
access:
  commands: aggregate_facade
  queries: named_reader
  cross_context: public_contract_only
relationships: []
lifecycle:
  event_consumers:
  - name: HandleDemoLifecycle
    kind: event_handler
    facet: DemoLifecycleHandler
    method: handle
    idempotency: event_id
`
	writeContractViewFixtureFile(
		t,
		filepath.Join(root, filepath.FromSlash(sourceRelative)),
		objectYAML,
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(metadataDir, filepath.FromSlash(viewRelative)),
		objectYAML,
	)
	contextYAML := `role: core
access:
  commands: aggregate_facade_only
  queries: named_reader_slice_only
  child_objects: aggregate_root_only
  cross_context: public_contract_only
`
	writeContractViewFixtureFile(
		t,
		filepath.Join(root, filepath.FromSlash(sourceContextRelative)),
		contextYAML,
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(metadataDir, filepath.FromSlash(viewContextRelative)),
		contextYAML,
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(
			root, "quwoquan_service", "services", "demo-service", "contracts", "domain.yaml",
		),
		"domain: demo\n",
	)
	writeContractViewFixtureFile(
		t,
		filepath.Join(
			root, "quwoquan_service", "services", "demo-service", "internal",
			"demo_context", "demo_object", "application", "other.go",
		),
		"package application\nfunc Other() {}\n",
	)
	if withImplementation {
		writeContractViewFixtureFile(
			t,
			filepath.Join(
				root, "quwoquan_service", "services", "demo-service", "internal",
				"demo_context", "demo_object", "application", "handler.go",
			),
			"package application\n"+
				"type DemoLifecycleHandler struct{}\n"+
				"func (*DemoLifecycleHandler) Handle() error { return nil }\n",
		)
	}
	writeContractViewManifest(
		t,
		root,
		metadataDir,
		map[string]string{
			viewContextRelative: sourceContextRelative,
			viewRelative:        sourceRelative,
		},
	)
	return contractViewFixture{root: root, metadataDir: metadataDir}
}

func writeContractViewManifest(
	t *testing.T,
	root,
	metadataDir string,
	fileSources map[string]string,
) {
	t.Helper()
	viewPaths := make([]string, 0, len(fileSources))
	for viewPath := range fileSources {
		viewPaths = append(viewPaths, viewPath)
	}
	sort.Strings(viewPaths)
	viewDigest := sha256.New()
	document := contractViewProvenanceDocument{
		SchemaVersion: contractViewProvenanceVersion,
	}
	for _, viewRelative := range viewPaths {
		sourceRelative := fileSources[viewRelative]
		viewPayload, err := os.ReadFile(filepath.Join(metadataDir, filepath.FromSlash(viewRelative)))
		if err != nil {
			t.Fatalf("read view file: %v", err)
		}
		sourcePayload, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(sourceRelative)))
		if err != nil {
			t.Fatalf("read source file: %v", err)
		}
		viewSHA := sha256.Sum256(viewPayload)
		sourceSHA := sha256.Sum256(sourcePayload)
		viewSHAHex := hex.EncodeToString(viewSHA[:])
		document.Sources = append(document.Sources, contractViewProvenanceSource{
			Path: sourceRelative, SHA256: hex.EncodeToString(sourceSHA[:]),
		})
		document.Files = append(document.Files, contractViewProvenanceFile{
			Path: viewRelative, SHA256: viewSHAHex,
			SourcePaths: []string{sourceRelative},
		})
		_, _ = viewDigest.Write([]byte(viewRelative))
		_, _ = viewDigest.Write([]byte{0})
		_, _ = viewDigest.Write([]byte(viewSHAHex))
		_, _ = viewDigest.Write([]byte{'\n'})
	}
	sort.Slice(document.Sources, func(left, right int) bool {
		return document.Sources[left].Path < document.Sources[right].Path
	})
	document.ViewDigest = hex.EncodeToString(viewDigest.Sum(nil))
	payload, err := json.Marshal(document)
	if err != nil {
		t.Fatalf("encode contract view provenance: %v", err)
	}
	writeContractViewFixtureFile(
		t,
		filepath.Join(metadataDir, contractViewProvenanceFilename),
		string(payload),
	)
}

func writeContractViewFixtureFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir %s: %v", path, err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

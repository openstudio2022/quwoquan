package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestLifecycleImplementationResolvesConcreteGoFacet(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "application", "projector.go"), `package application
type DemoLifecycleProjector struct{}
func (*DemoLifecycleProjector) ApplyEvent() error { return nil }
`)
	artifact := resolveLifecycleFixture(t, root, objectRoot, ast.LifecycleEventConsumer{
		Name: "ProjectDemo", Facet: "DemoLifecycleProjector", Method: "applyEvent",
	})
	if artifact.Path != "quwoquan_service/services/demo-service/internal/demo_context/demo_object/application/projector.go" ||
		len(artifact.SHA256) != 64 {
		t.Fatalf("implementation artifact=%+v", artifact)
	}
}

func TestLifecycleImplementationResolvesUniqueGoInterfaceImplementer(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "application", "port.go"), `package application
type DemoLifecycleHandler interface { HandleEvent() error }
`)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", "inbound", "stream", "consumer.go"), `package stream
type Consumer struct{}
func (*Consumer) HandleEvent() error { return nil }
`)
	artifact := resolveLifecycleFixture(t, root, objectRoot, ast.LifecycleEventConsumer{
		Name: "HandleDemo", Facet: "DemoLifecycleHandler", Method: "handleEvent",
	})
	if !strings.HasSuffix(artifact.Path, "/adapters/inbound/stream/consumer.go") {
		t.Fatalf("interface implementation artifact=%+v", artifact)
	}
}

func TestLifecycleImplementationRejectsMissingOrAmbiguousFacet(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	consumer := ast.LifecycleEventConsumer{
		Name: "ProjectDemo", Facet: "DemoLifecycleProjector", Method: "apply",
	}
	index, err := buildLifecycleSourceIndex(objectRoot)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := resolveLifecycleImplementation(
		root,
		lifecycleImplementationObject(),
		consumer,
		index,
	); err == nil || !strings.Contains(err.Error(), "requires one concrete or interface facet") {
		t.Fatalf("missing facet error=%v", err)
	}
	writeLifecycleFixture(t, filepath.Join(objectRoot, "application", "first.go"), `package application
type DemoLifecycleProjector struct{}
func (*DemoLifecycleProjector) Apply() error { return nil }
`)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", "second.go"), `package adapters
type DemoLifecycleProjector struct{}
func (*DemoLifecycleProjector) Apply() error { return nil }
`)
	index, err = buildLifecycleSourceIndex(objectRoot)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := resolveLifecycleImplementation(
		root,
		lifecycleImplementationObject(),
		consumer,
		index,
	); err == nil || !strings.Contains(err.Error(), "found 2") {
		t.Fatalf("ambiguous facet error=%v", err)
	}
}

func TestLifecycleImplementationResolvesPythonClassAndSnakeCaseMethod(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "application", "projector.py"), `class RecommendationModelRuntimeCoordinator:
    def apply_release_event(self, event):
        return event
`)
	artifact := resolveLifecycleFixture(t, root, objectRoot, ast.LifecycleEventConsumer{
		Name: "ApplyRelease", Facet: "RecommendationModelRuntimeCoordinator", Method: "applyReleaseEvent",
	})
	if !strings.HasSuffix(artifact.Path, "/application/projector.py") {
		t.Fatalf("Python implementation artifact=%+v", artifact)
	}
}

func TestLifecycleImplementationResolvesInheritedPythonConsumerToSubclass(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", "base.py"), `class DurableProjectionConsumer:
    def process_once(self):
        return 0
`)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", "content_consumer.py"), `class ContentBehaviorConsumer(DurableProjectionConsumer):
    def _process(self, event):
        return event
`)
	artifact := resolveLifecycleFixture(t, root, objectRoot, ast.LifecycleEventConsumer{
		Name: "ProjectBehavior", Facet: "ContentBehaviorConsumer", Method: "processOnce",
	})
	if !strings.HasSuffix(artifact.Path, "/adapters/content_consumer.py") {
		t.Fatalf("inherited Python implementation artifact=%+v", artifact)
	}
}

func lifecycleImplementationFixture(t *testing.T) (string, string) {
	t.Helper()
	root := t.TempDir()
	objectRoot := filepath.Join(
		root,
		"quwoquan_service",
		"services",
		"demo-service",
		"internal",
		"demo_context",
		"demo_object",
	)
	if err := os.MkdirAll(objectRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	return root, objectRoot
}

func writeLifecycleFixture(t *testing.T, path string, body string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
}

func resolveLifecycleFixture(
	t *testing.T,
	root string,
	objectRoot string,
	consumer ast.LifecycleEventConsumer,
) *ast.EvidenceArtifact {
	t.Helper()
	index, err := buildLifecycleSourceIndex(objectRoot)
	if err != nil {
		t.Fatal(err)
	}
	artifact, err := resolveLifecycleImplementation(
		root,
		lifecycleImplementationObject(),
		consumer,
		index,
	)
	if err != nil {
		t.Fatal(err)
	}
	return artifact
}

func lifecycleImplementationObject() ast.Object {
	return ast.Object{
		ID: "demo.demo_object", Domain: "demo", Name: "DemoObject",
		SourcePath: "demo/demo_context/demo_object/object.yaml",
	}
}

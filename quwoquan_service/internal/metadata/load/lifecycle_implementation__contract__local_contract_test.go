package load

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestLifecycleEntrypointBinderResolvesAllFiveProjectionConsumers(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	consumers := []ast.LifecycleEventConsumer{
		{Name: "ProjectPost", Kind: "projector", Facet: "PostConsumer", Method: "processOnce"},
		{Name: "ProjectPool", Kind: "projector", Facet: "PoolConsumer", Method: "processOnce"},
		{Name: "ProjectPersona", Kind: "projector", Facet: "PersonaConsumer", Method: "processOnce"},
		{Name: "ProjectAccount", Kind: "projector", Facet: "AccountConsumer", Method: "processOnce"},
		{Name: "ProjectGathering", Kind: "projector", Facet: "GatheringConsumer", Method: "processOnce"},
	}
	for index, consumer := range consumers {
		writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", consumer.Name+".go"), `package adapters
type `+consumer.Facet+` struct{}
func (*`+consumer.Facet+`) ProcessOnce() error { return nil }
`)
		consumers[index].Idempotency = "aggregate_version"
	}
	catalog := lifecycleEntrypointCatalog(ast.ObjectKindProjection, consumers)
	var errs []error
	bindLifecycleEntrypointImplementations(catalog, root, &errs)
	if len(errs) != 0 {
		t.Fatalf("bind lifecycle entrypoints: %v", errs)
	}
	for _, consumer := range catalog.Objects[0].Lifecycle.EventConsumers {
		if consumer.Implementation == nil ||
			consumer.Implementation.Path == "" ||
			len(consumer.Implementation.SHA256) != 64 {
			t.Fatalf("unresolved consumer: %+v", consumer)
		}
	}
}

func TestLifecycleEntrypointBinderRejectsMissingOrAmbiguousProjectionImplementation(t *testing.T) {
	tests := map[string]func(t *testing.T, objectRoot string){
		"missing": func(t *testing.T, objectRoot string) {},
		"ambiguous": func(t *testing.T, objectRoot string) {
			for _, name := range []string{"first.go", "second.go"} {
				writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", name), `package adapters
type DemoLifecycleProjector struct{}
func (*DemoLifecycleProjector) ProcessOnce() error { return nil }
`)
			}
		},
	}
	for name, prepare := range tests {
		name, prepare := name, prepare
		t.Run(name, func(t *testing.T) {
			root, objectRoot := lifecycleImplementationFixture(t)
			prepare(t, objectRoot)
			catalog := lifecycleEntrypointCatalog(
				ast.ObjectKindProjection,
				[]ast.LifecycleEventConsumer{{
					Name: "ProjectDemo", Kind: "projector",
					Facet: "DemoLifecycleProjector", Method: "processOnce",
					Idempotency: "aggregate_version",
				}},
			)
			var errs []error
			bindLifecycleEntrypointImplementations(catalog, root, &errs)
			if len(errs) == 0 || catalog.Objects[0].Lifecycle.EventConsumers[0].Implementation != nil {
				t.Fatalf("invalid implementation accepted: errors=%v consumer=%+v", errs,
					catalog.Objects[0].Lifecycle.EventConsumers[0])
			}
		})
	}
}

func TestLifecycleEntrypointBinderAlsoBindsAggregateConsumers(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "application", "handler.go"), `package application
type DemoLifecycleHandler struct{}
func (*DemoLifecycleHandler) Handle() error { return nil }
`)
	catalog := lifecycleEntrypointCatalog(
		ast.ObjectKindAggregateRoot,
		[]ast.LifecycleEventConsumer{{
			Name: "HandleDemo", Kind: "event_handler",
			Facet: "DemoLifecycleHandler", Method: "handle",
			Idempotency: "event_id",
		}},
	)
	var errs []error
	bindLifecycleEntrypointImplementations(catalog, root, &errs)
	consumer := catalog.Objects[0].Lifecycle.EventConsumers[0]
	if len(errs) != 0 || consumer.Implementation == nil ||
		!strings.HasSuffix(consumer.Implementation.Path, "/application/handler.go") {
		t.Fatalf("aggregate lifecycle implementation not bound: errors=%v consumer=%+v", errs, consumer)
	}
}

func TestLifecycleEntrypointBinderDoesNotSkipObjectsWithHTTPEntrypoints(t *testing.T) {
	root, objectRoot := lifecycleImplementationFixture(t)
	writeLifecycleFixture(t, filepath.Join(objectRoot, "adapters", "consumer.go"), `package adapters
type DemoLifecycleProjector struct{}
func (*DemoLifecycleProjector) Apply() error { return nil }
`)
	catalog := lifecycleEntrypointCatalog(
		ast.ObjectKindProjection,
		[]ast.LifecycleEventConsumer{{
			Name: "ProjectDemo", Kind: "projector",
			Facet: "DemoLifecycleProjector", Method: "apply",
			Idempotency: "aggregate_version",
		}},
	)
	catalog.Operations = []ast.Operation{{
		ID: "demo.demo_object.GetDemo", ObjectID: "demo.demo_object",
	}}
	var errs []error
	bindLifecycleEntrypointImplementations(catalog, root, &errs)
	consumer := catalog.Objects[0].Lifecycle.EventConsumers[0]
	if len(errs) != 0 || consumer.Implementation == nil ||
		!strings.HasSuffix(consumer.Implementation.Path, "/adapters/consumer.go") {
		t.Fatalf("HTTP object lifecycle implementation not bound: errors=%v consumer=%+v", errs, consumer)
	}
}

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

func TestLifecycleImplementationRejectsEmptyGoAndPythonMarkers(t *testing.T) {
	for _, testCase := range []struct {
		name   string
		path   string
		body   string
		facet  string
		method string
	}{
		{
			name: "empty Go method", path: "application/empty.go",
			body: `package application
type EmptyHandler struct{}
func (*EmptyHandler) Handle() {}
`,
			facet: "EmptyHandler", method: "handle",
		},
		{
			name: "Python pass marker", path: "adapters/empty.py",
			body: `class EmptyHandler:
    def handle(self):
        pass
`,
			facet: "EmptyHandler", method: "handle",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			root, objectRoot := lifecycleImplementationFixture(t)
			writeLifecycleFixture(t, filepath.Join(objectRoot, testCase.path), testCase.body)
			index, err := buildLifecycleSourceIndex(objectRoot)
			if err != nil {
				t.Fatal(err)
			}
			_, err = resolveLifecycleImplementation(
				root,
				lifecycleImplementationObject(),
				ast.LifecycleEventConsumer{
					Name: "HandleDemo", Facet: testCase.facet, Method: testCase.method,
				},
				index,
			)
			if err == nil || !strings.Contains(err.Error(), "exactly one owning production source") {
				t.Fatalf("empty lifecycle marker was accepted: %v", err)
			}
		})
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
	writeLifecycleFixture(
		t,
		filepath.Join(root, "quwoquan_service", "services", "demo-service", "contracts", "domain.yaml"),
		"domain: demo\n",
	)
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

func lifecycleEntrypointCatalog(
	kind ast.ObjectKind,
	consumers []ast.LifecycleEventConsumer,
) *ast.Catalog {
	object := lifecycleImplementationObject()
	object.Kind = kind
	object.Lifecycle = &ast.LifecycleDefinition{
		SourceEvents:   []string{"content.post.PostPublished"},
		EventConsumers: consumers,
	}
	return &ast.Catalog{Objects: []ast.Object{object}}
}

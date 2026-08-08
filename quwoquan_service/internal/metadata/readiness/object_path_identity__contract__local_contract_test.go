package readiness

import (
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"

	"gopkg.in/yaml.v3"
)

func TestCurrentServiceRosterDerivesExactRunnerRootsWithoutARegistry(t *testing.T) {
	current := currentRepositoryObjectRoster(t)
	identities, err := currentObjectPathIdentities(current)
	if err != nil {
		t.Fatalf("derive current object paths: %v", err)
	}
	if len(identities) == 0 || len(identities) != len(current.Objects) {
		t.Fatalf("identities=%d objects=%d, want the dynamically scanned current roster", len(identities), len(current.Objects))
	}

	ids := make([]string, 0, len(identities))
	for objectID := range identities {
		ids = append(ids, objectID)
	}
	sort.Strings(ids)
	var implemented int
	for _, objectID := range ids {
		identity := identities[objectID]
		if len(identity.serviceRoot) == 0 {
			continue
		}
		implemented++
		serviceRunner := strings.Join(append(
			append([]string(nil), identity.serviceRoot...),
			"tests", "local_contract", identity.context, identity.object,
			"roster__local_contract_test.go",
		), "/")
		if !validProducerRunnerSourcePath(
			serviceRunner, identity, ProducerService, LayerLocalContract,
		) {
			t.Fatalf("%s: canonical service runner rejected: %s", objectID, serviceRunner)
		}
		wrongCloudRoot := append([]string(nil), identity.serviceRoot...)
		wrongCloudRoot[len(wrongCloudRoot)-1] = "not-the-owner"
		wrongServiceRunner := strings.Join(append(
			wrongCloudRoot, "tests", "local_contract", identity.context,
			identity.object, "roster__local_contract_test.go",
		), "/")
		if validProducerRunnerSourcePath(
			wrongServiceRunner, identity, ProducerService, LayerLocalContract,
		) {
			t.Fatalf("%s: wrong Cloud service owner accepted: %s", objectID, wrongServiceRunner)
		}
		appRunner := strings.Join([]string{
			"quwoquan_app", "test", "api_integration", "service",
			identity.appServiceRoot, identity.context, identity.object,
			"roster__api_integration_test.dart",
		}, "/")
		if !validProducerRunnerSourcePath(
			appRunner, identity, ProducerApp, LayerAPIIntegration,
		) {
			t.Fatalf("%s: canonical App runner rejected: %s", objectID, appRunner)
		}
		wrongService := strings.Replace(
			appRunner, "/service/"+identity.appServiceRoot+"/",
			"/service/not_the_owner/", 1,
		)
		if validProducerRunnerSourcePath(
			wrongService, identity, ProducerApp, LayerAPIIntegration,
		) {
			t.Fatalf("%s: wrong App service owner accepted: %s", objectID, wrongService)
		}
	}
	if implemented == 0 {
		t.Fatal("current service roster has no loader-derived implementation roots")
	}
}

func TestObjectReadinessRejectsCrossCuttingAndRunnerShellPaths(t *testing.T) {
	identity := objectPathIdentity{
		domain:         "content",
		context:        "content",
		object:         "post",
		serviceRoot:    []string{"quwoquan_service", "services", "content-service"},
		appServiceRoot: "content_service",
	}
	for _, testCase := range []struct {
		path     string
		producer Producer
		layer    Layer
	}{
		{"quwoquan_app/test/local_contract/runtime/transport/post_test.dart", ProducerApp, LayerLocalContract},
		{"quwoquan_app/test/local_contract/design_system/post_test.dart", ProducerApp, LayerLocalContract},
		{"quwoquan_app/test/support/service/content_service/content/post/post_test.dart", ProducerApp, LayerLocalContract},
		{"quwoquan_app/test/local_contract/journeys/content_publish/post_test.dart", ProducerApp, LayerLocalContract},
		{"quwoquan_app/test/user_acceptance/patrol/test_bundle.dart", ProducerApp, LayerUserAcceptance},
	} {
		if validProducerRunnerSourcePath(
			testCase.path, identity, testCase.producer, testCase.layer,
		) {
			t.Fatalf("non-object runner was accepted as object evidence: %s", testCase.path)
		}
	}

	journey := "quwoquan_app/test/user_acceptance/journeys/content_publish/content_publish__user_acceptance_test.dart"
	if !validProducerRunnerSourcePath(journey, identity, ProducerApp, LayerUserAcceptance) {
		t.Fatalf("canonical production-Remote Journey runner rejected: %s", journey)
	}
	if validProducerRunnerSourcePath(
		"quwoquan_app/test/user_acceptance/journeys/content_publish/helper.dart",
		identity, ProducerApp, LayerUserAcceptance,
	) {
		t.Fatal("Journey helper without a test suffix was accepted as execution evidence")
	}
}

func TestObjectPathIdentityFailsClosedOnEvidenceDrift(t *testing.T) {
	current := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "content.post", Domain: "content",
			SourcePath: "content/content/post/object.yaml",
		}},
		ReadinessEvidence: []ast.ObjectReadinessEvidence{{
			ObjectID:   "content.post",
			SourcePath: "quwoquan_service/services/content-service/internal/content/other_object",
		}},
	}
	if _, err := currentObjectPathIdentities(current); err == nil {
		t.Fatal("evidence object-root drift was accepted")
	}

	current.ReadinessEvidence[0].SourcePath = "quwoquan_service/services/content-service/internal/content/post"
	current.ReadinessEvidence = append(current.ReadinessEvidence, current.ReadinessEvidence[0])
	if _, err := currentObjectPathIdentities(current); err == nil {
		t.Fatal("duplicate evidence packet was accepted")
	}
}

func currentRepositoryObjectRoster(t *testing.T) *graph.ContractGraph {
	t.Helper()
	root := readinessRepositoryRoot(t)
	patterns := []string{
		filepath.Join(root, "quwoquan_service", "services", "*", "contracts", "domain.yaml"),
		filepath.Join(root, "quwoquan_service", "control-plane", "*", "contracts", "domain.yaml"),
	}
	current := &graph.ContractGraph{}
	for _, pattern := range patterns {
		domainPaths, err := filepath.Glob(pattern)
		if err != nil {
			t.Fatalf("glob domain contracts: %v", err)
		}
		for _, domainPath := range domainPaths {
			data, err := os.ReadFile(domainPath)
			if err != nil {
				t.Fatalf("read %s: %v", domainPath, err)
			}
			var document struct {
				Domain string `yaml:"domain"`
			}
			if err := yaml.Unmarshal(data, &document); err != nil || document.Domain == "" {
				t.Fatalf("decode %s: domain=%q err=%v", domainPath, document.Domain, err)
			}
			contractsRoot := filepath.Dir(domainPath)
			serviceRoot := filepath.Dir(contractsRoot)
			objectPaths, err := filepath.Glob(filepath.Join(contractsRoot, "*", "*", "object.yaml"))
			if err != nil {
				t.Fatalf("glob objects under %s: %v", contractsRoot, err)
			}
			for _, objectPath := range objectPaths {
				object := filepath.Base(filepath.Dir(objectPath))
				context := filepath.Base(filepath.Dir(filepath.Dir(objectPath)))
				objectID := document.Domain + "." + object
				current.Objects = append(current.Objects, ast.Object{
					ID: objectID, Domain: document.Domain,
					SourcePath: strings.Join([]string{
						document.Domain, context, object, "object.yaml",
					}, "/"),
				})
				implementationRoot := filepath.Join(serviceRoot, "internal", context, object)
				if info, err := os.Stat(implementationRoot); err == nil && info.IsDir() {
					relative, err := filepath.Rel(root, implementationRoot)
					if err != nil {
						t.Fatalf("relativize %s: %v", implementationRoot, err)
					}
					current.ReadinessEvidence = append(
						current.ReadinessEvidence,
						ast.ObjectReadinessEvidence{
							ObjectID: objectID, SourcePath: filepath.ToSlash(relative),
						},
					)
				}
			}
		}
	}
	return current
}

func readinessRepositoryRoot(t *testing.T) string {
	t.Helper()
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test source")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "quwoquan_service", "contracts", "metadata", "README.md")); err != nil {
		t.Fatalf("resolve repository root %s: %v", root, err)
	}
	return root
}

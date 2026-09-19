package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/testsupport/contractsview"
)

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func TestSharedRequestValueFourRealDomainsAndResponseEnvelope(t *testing.T) {
	verifyClientPresentationEmitterBoundary(t)
	preservePresentationManifest(t)
	metadataDir := contractsview.Build(t)
	if err := initializeMetadataSourceForServiceOutput(metadataDir); err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(activeMetadataSource.Graph().Operations)
	if err != nil {
		t.Fatal(err)
	}
	var operations []appExposedOperation
	if err := json.Unmarshal(raw, &operations); err != nil {
		t.Fatal(err)
	}
	selected := map[string]appExposedOperation{}
	for i, op := range operations {
		if op.ClientContract == nil {
			continue
		}
		if op.Domain != "content" && op.Domain != "circle" && op.Domain != "search" && op.Domain != "gateway" {
			continue
		}
		if _, ok := selected[op.Domain]; ok {
			continue
		}
		op.CanonicalOperationID = activeMetadataSource.Graph().Operations[i].ID
		op.LocalOperationID = activeMetadataSource.Graph().Operations[i].LocalID
		_, dependencies, err := loadOperationRequestModel(op, op.RequestEntity)
		if err != nil {
			t.Fatal(err)
		}
		if _, ok := dependencies["ClientContentPresentationContract"]; ok {
			selected[op.Domain] = op
		}
	}
	if len(selected) != 4 {
		t.Fatalf("expected 4 real capability domains, got %v", selected)
	}
	lock := appContractLock{}
	for _, domain := range []string{"content", "circle", "search", "gateway"} {
		op := selected[domain]
		t.Log(op.CanonicalOperationID, op.RequestEntity, op.ResponseEntity)
		lock.AppExposedOperations = append(lock.AppExposedOperations, op)
	}
	app := t.TempDir()
	beginGeneratedManifest(app, "four-domain-shared-request")
	searchContract, err := readSearchContract(filepath.Join(metadataDir, "_shared/search_contract.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	searchObjects, err := readSearchObjects(filepath.Join(metadataDir, "_shared/search_objects.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if err := writeCanonicalSearchMetadata(app, searchContract, searchObjects); err != nil {
		t.Fatal(err)
	}
	if err := generateCanonicalSearchClientModels(metadataDir, app); err != nil {
		t.Fatal(err)
	}
	provided, err := generateDomainOperationContracts(metadataDir, app, lock)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := writeGeneratedOperationRequests(app, lock, provided); err != nil {
		t.Fatal(err)
	}
	if err := writeClientPresentationContractDart(app, metadataDir); err != nil {
		t.Fatal(err)
	}
	src := filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src")
	shared := readGeneratedTestFile(t, filepath.Join(src, "generated/shared_operation_types.g.dart"))
	if strings.Count(shared, "final class ClientContentPresentationContract {") != 1 {
		t.Fatal("missing unique shared capability DTO")
	}
	enums := readGeneratedTestFile(t, filepath.Join(src, "generated/shared_operation_enums.g.dart"))
	for _, name := range []string{"ContentType", "ListObjectKind", "ContentUiSurface", "FeedPresentationRecipe"} {
		if strings.Count(enums, "enum "+name+" {") != 1 {
			t.Fatal("missing unique shared enum", name)
		}
	}
	var runner strings.Builder
	for _, domain := range []string{"content", "circle", "search", "gateway"} {
		owner := readGeneratedTestFile(t, filepath.Join(src, domain, domain+"_operation_contracts.g.dart"))
		if !strings.Contains(owner, `export "../generated/shared_operation_types.g.dart";`) {
			t.Fatal("owner does not export shared request value", domain)
		}
		part := readGeneratedTestFile(t, filepath.Join(src, "generated/requests", domain, domain+"_operation_contracts.g.requests.g.dart"))
		if strings.Contains(part, "class ClientContentPresentationContract {") {
			t.Fatal("request retained duplicate", domain)
		}
		fmt.Fprintf(&runner, "import 'package:quwoquan_cloud_contracts/src/%s/%s_operation_contracts.g.dart';\n", domain, domain)
	}
	helperPath := runtimeTransportSharedOutputPath(app, "client_content_presentation_contract.g.dart")
	fmt.Fprintf(&runner, "import 'file://%s';\n", helperPath)
	// 无 prefix 同时导入四 owner；Dart 编译可发现 ambiguous import 和 nominal type 不同源。
	runner.WriteString("import 'package:quwoquan_cloud_contracts/src/generated/shared_operation_types.g.dart';\nvoid assignments(ClientContentPresentationContract value, ListItemPresentationEnvelope envelope) {\n")
	for _, domain := range []string{"content", "circle", "search", "gateway"} {
		fmt.Fprintf(&runner, "  final %s request%s = throw UnimplementedError();\n  final ClientContentPresentationContract? same%s = request%s.clientPresentationContract;\n", selected[domain].RequestEntity, domain, domain, domain)
	}
	runner.WriteString("  final ContentType? type = envelope.contentType;\n  final List<ContentType> types = value.contentTypes;\n  final ListObjectKind kind = envelope.objectKind;\n  final List<ListObjectKind> kinds = value.listObjectKinds;\n  final ContentUiSurface surface = envelope.openSurface;\n  final List<ContentUiSurface> surfaces = value.openSurfaces;\n  final FeedPresentationRecipe? recipe = envelope.presentationRecipe;\n  final List<FeedPresentationRecipe> recipes = value.presentationRecipes;\n}\n")
	runner.WriteString(`void main() {
 final value = compiledContentPresentationContract;
 final requests = <Object>[
  ContentDiscoveryFeedQuery(clientPresentationContract: value),
  CircleFeedQuery(circleId: 'circle', clientPresentationContract: value),
  CanonicalSearchQuery(query: 'content', clientPresentationContract: value),
  SearchPageInput(query: 'content', clientPresentationContract: value),
 ];
 final envelope = ListItemPresentationEnvelope(objectKind: value.listObjectKinds.first, contentType: value.contentTypes.first, openSurface: value.openSurfaces.first, presentationRecipe: value.presentationRecipes.first);
 if (requests.length != 4 || envelope.contentType != value.contentTypes.first) throw StateError('typed assignment failed');
 validateClientContentPresentationContract(value);
}
`)
	// 只复制当前生成器依赖的已有纯 Dart 支持文件；主线真实 generated 不写入。
	copySharedRequestDartSupport(t, src)
	if err := os.WriteFile(filepath.Join(src, "check.dart"), []byte(runner.String()), 0644); err != nil {
		t.Fatal(err)
	}
	packages, err := filepath.Abs("../../../quwoquan_app/.dart_tool/package_config.json")
	if err != nil {
		t.Fatal(err)
	}
	configBytes, err := os.ReadFile(packages)
	if err != nil {
		t.Fatal(err)
	}
	var config map[string]any
	if err := json.Unmarshal(configBytes, &config); err != nil {
		t.Fatal(err)
	}
	for _, item := range config["packages"].([]any) {
		entry := item.(map[string]any)
		uri := entry["rootUri"].(string)
		if entry["name"] == "quwoquan_cloud_contracts" {
			entry["rootUri"] = "file://" + filepath.Dir(filepath.Dir(src)) + "/"
		} else if !strings.Contains(uri, ":") {
			entry["rootUri"] = "file://" + filepath.Clean(filepath.Join(filepath.Dir(packages), uri)) + "/"
		}
	}
	configBytes, err = json.Marshal(config)
	if err != nil {
		t.Fatal(err)
	}
	privatePackages := filepath.Join(app, "package_config.json")
	if err := os.WriteFile(privatePackages, configBytes, 0644); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("dart", "--packages="+privatePackages, "check.dart")
	cmd.Dir = src
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("four domain typed assignments: %v\n%s", err, out)
	}
}

func TestSharedRequestValueRejectsCanonicalShapeDrift(t *testing.T) {
	canonical := map[string]requestModelSpec{"Shared": {Name: "Shared", Fields: []fieldDef{{Name: "values", Type: "[]enum", EnumRef: "ContentType", Constraints: []string{"NOT_NULL"}, MaxItems: 32}}}}
	drift := canonical["Shared"]
	drift.Fields = append([]fieldDef(nil), drift.Fields...)
	drift.Fields[0].MaxItems = 64
	spec := &domainOperationContractSpec{OwnerImport: "../content/content_operation_contracts.g.dart", Models: map[string]requestModelSpec{}}
	if err := mergeRequestValueDependencies(spec, map[string]requestModelSpec{"Shared": drift}, canonical); err == nil {
		t.Fatal("canonical request shape drift accepted")
	}
	if len(spec.Models) != 0 {
		t.Fatal("drift partly published")
	}
}

func copySharedRequestDartSupport(t *testing.T, src string) {
	t.Helper()
	for _, name := range []string{"operation_request_payload.dart", "canonical_sha256_digest.dart"} {
		data, err := os.ReadFile(filepath.Join("../../../quwoquan_app/packages/quwoquan_cloud_contracts/lib/src", name))
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(src, name), data, 0644); err != nil {
			t.Fatal(err)
		}
	}
}

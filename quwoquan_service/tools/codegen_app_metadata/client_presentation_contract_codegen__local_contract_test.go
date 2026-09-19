package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/tools/internal/presentationcontract"
)

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func TestClientPresentationDartUsesActualCloudModelAndManifest(t *testing.T) {
	preservePresentationManifest(t)
	root, err := filepath.Abs("../../contracts/metadata")
	if err != nil {
		t.Fatal(err)
	}
	if err := initializeMetadataDocumentSource(root, []string{"_shared/types.yaml"}); err != nil {
		t.Fatal(err)
	}
	raw, err := readMetadataDocument(filepath.Join(root, "_shared/types.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	model, err := presentationcontract.Load(raw)
	if err != nil {
		t.Fatal(err)
	}
	models, err := loadCanonicalSharedValueModels()
	if err != nil {
		t.Fatal(err)
	}
	values, err := loadCanonicalSharedEnumValues()
	if err != nil {
		t.Fatal(err)
	}
	spec := domainOperationContractSpec{OwnerImport: "../generated/shared_operation_types.g.dart", Models: map[string]requestModelSpec{presentationcontract.TypeName: models[presentationcontract.TypeName]}, EnumMembers: map[string][]canonicalRequestEnumMember{}}
	if err := collectDomainEnumMembers(spec.EnumMembers, models[presentationcontract.TypeName], values); err != nil {
		t.Fatal(err)
	}
	actualModel, err := renderDomainOperationContract(spec)
	if err != nil {
		t.Fatal(err)
	}
	app := t.TempDir()
	beginGeneratedManifest(app, "presentation-golden")
	ownerPath := filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src/generated/shared_operation_types.g.dart")
	writeFile(ownerPath, actualModel)
	// 复用实际 canonical digest 格式 helper；不手写模型或 enum 假体。
	digestHelper, err := os.ReadFile("../../../quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/canonical_sha256_digest.dart")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(filepath.Dir(filepath.Dir(ownerPath)), "canonical_sha256_digest.dart"), digestHelper, 0644); err != nil {
		t.Fatal(err)
	}
	if err := writeClientPresentationContractDart(app, root); err != nil {
		t.Fatal(err)
	}
	helperPath := runtimeTransportSharedOutputPath(app, "client_content_presentation_contract.g.dart")
	helper, err := os.ReadFile(helperPath)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(helper), "class ClientContentPresentationContract") {
		t.Fatal("helper introduced duplicate DTO")
	}
	// 临时执行环境只替换 package 定位，模型与摘要 helper 内容均为真实 writer 产物。
	helperText := strings.ReplaceAll(string(helper), "package:quwoquan_cloud_contracts/src/generated/shared_operation_types.g.dart", "file://"+ownerPath)
	if err := os.WriteFile(helperPath, []byte(helperText), 0644); err != nil {
		t.Fatal(err)
	}
	fixture, err := model.GoldenFixture()
	if err != nil {
		t.Fatal(err)
	}
	runDir := filepath.Dir(helperPath)
	if err := os.WriteFile(filepath.Join(runDir, "golden.json"), fixture, 0644); err != nil {
		t.Fatal(err)
	}
	runner := "import 'file://" + ownerPath + "';\n" + actualDartGoldenRunner
	if err := os.WriteFile(filepath.Join(runDir, "test.dart"), []byte(runner), 0644); err != nil {
		t.Fatal(err)
	}
	packages, err := filepath.Abs("../../../quwoquan_app/.dart_tool/package_config.json")
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("dart", "--packages="+packages, "test.dart")
	cmd.Dir = runDir
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("actual cloud DTO golden: %v\n%s", err, output)
	}
	manifest := filepath.Join(app, "manifest.json")
	if err := writeGeneratedManifest(manifest); err != nil {
		t.Fatal(err)
	}
	manifestBytes, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(manifestBytes), "client_content_presentation_contract.g.dart") {
		t.Fatal("manifest missed runtime helper")
	}
	if strings.Contains(string(manifestBytes), ".golden.json") {
		t.Fatal("test fixture leaked into runtime manifest")
	}
	if _, err := os.Stat(runtimeTransportSharedOutputPath(app, "client_content_presentation_contract.golden.json")); !os.IsNotExist(err) {
		t.Fatal("production writer still emits test fixture", err)
	}
}

func TestClientPresentationOwnerResolvesRequestPart(t *testing.T) {
	app := t.TempDir()
	preservePresentationManifest(t)
	beginGeneratedManifest(app, "part-owner")
	part := filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src/generated/requests/content/content_operation_contracts.g.requests.g.dart")
	writeFile(part, "part of '../../../content/content_operation_contracts.g.dart';\nfinal class ClientContentPresentationContract {}")
	// 删除本轮临时磁盘产物，证明 owner 接线完全不依赖回读。
	if err := os.Remove(part); err != nil {
		t.Fatal(err)
	}
	owner, err := clientPresentationDartOwner()
	if err != nil || owner != "package:quwoquan_cloud_contracts/src/content/content_operation_contracts.g.dart" {
		t.Fatalf("part owner: %q %v", owner, err)
	}
	writeFile(filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src/generated/duplicate.dart"), "final class ClientContentPresentationContract {}")
	if _, err := clientPresentationDartOwner(); err == nil {
		t.Fatal("duplicate DTO owners accepted")
	}
}

func TestClientPresentationOwnerMemoryIsRoundScoped(t *testing.T) {
	preservePresentationManifest(t)
	app := t.TempDir()
	beginGeneratedManifest(app, "owner-memory")
	path := filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src/generated/shared_operation_types.g.dart")
	recordGeneratedFile(path, []byte("final class ClientContentPresentationContract {}"))
	owner, err := clientPresentationDartOwner()
	if err != nil || owner != "package:quwoquan_cloud_contracts/src/generated/shared_operation_types.g.dart" {
		t.Fatalf("in-memory owner %q: %v", owner, err)
	}
	manifest := filepath.Join(app, "manifest.json")
	if err := writeGeneratedManifest(manifest); err != nil {
		t.Fatal(err)
	}
	bytes, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(bytes), "final class") || strings.Contains(string(bytes), "Content\"") {
		t.Fatal("memory bytes leaked into manifest schema")
	}
	beginGeneratedManifest(app, "next-round")
	if _, err := clientPresentationDartOwner(); err == nil {
		t.Fatal("previous round owner reused")
	}
}

func verifyClientPresentationEmitterBoundary(t *testing.T) {
	t.Helper()
	verifier, err := filepath.Abs("../../../quwoquan_app/scripts/runtime/codegen/verify_app_generated_manifest.py")
	if err != nil {
		t.Fatal(err)
	}
	// 执行现有真实门禁；不 mock 根、source 内容或扫描白名单。
	cmd := exec.Command("python3", "-B", "-c", `import importlib.util, sys
spec = importlib.util.spec_from_file_location("app_emitter_boundary", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.verify_emitter_boundary()
`, verifier)
	cmd.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("canonical App emitter source boundary: %v\n%s", err, output)
	}
}

func TestClientPresentationEmitterBoundary(t *testing.T) {
	verifyClientPresentationEmitterBoundary(t)
}

func TestClientPresentationGoldenCanonicalRetirement(t *testing.T) {
	preservePresentationManifest(t)
	app := t.TempDir()
	beginGeneratedManifest(app, "golden-retirement")
	path := runtimeTransportSharedOutputPath(app, "client_content_presentation_contract.golden.json")
	sibling := runtimeTransportSharedOutputPath(app, "unrelated.json")
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{path, sibling} {
		if err := os.WriteFile(p, []byte("[]"), 0644); err != nil {
			t.Fatal(err)
		}
	}
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("retired exact fixture remains", err)
	}
	if _, err := os.Stat(sibling); err != nil {
		t.Fatal("unrelated JSON was removed", err)
	}
	if err := removeUntrackedGeneratedOutputs(); err != nil {
		t.Fatal("cleanup is not idempotent", err)
	}
	// 目录/链接不能被当成历史 regular-file 产物删除，也不能越过目标写入边界。
	if err := os.Symlink(sibling, path); err != nil {
		t.Fatal(err)
	}
	if err := removeUntrackedGeneratedOutputs(); err == nil {
		t.Fatal("symlink retirement accepted")
	}
	if _, err := os.Stat(sibling); err != nil {
		t.Fatal("symlink target changed", err)
	}
}

func preservePresentationManifest(t *testing.T) {
	t.Helper()
	root, graph, outputs := generatedManifestAppRoot, generatedManifestGraph, generatedManifestOutputs
	source, metadataRoot, lock, sha := activeMetadataSource, activeMetadataRoot, activeContractLock, activeContractSHA256
	pending, bindings := pendingEnumFieldBindings, enumFieldBindings
	t.Cleanup(func() {
		generatedManifestAppRoot, generatedManifestGraph, generatedManifestOutputs = root, graph, outputs
		activeMetadataSource, activeMetadataRoot, activeContractLock, activeContractSHA256 = source, metadataRoot, lock, sha
		pendingEnumFieldBindings, enumFieldBindings = pending, bindings
	})
}

const actualDartGoldenRunner = `import 'dart:convert';
import 'dart:io';
import 'client_content_presentation_contract.g.dart';
void check(bool value){if(!value)throw StateError('golden mismatch');}
void main(){
 for(final raw in jsonDecode(File('golden.json').readAsStringSync()) as List){
  final item=raw as Map;
  final wire=<String,Object?>{...Map<String,Object?>.from(item['collections'] as Map),'contractDigest':item['digest']};
  final typed=ClientContentPresentationContract.fromWire(wire);
  check(canonicalClientContentPresentationContract(typed)==item['canonical']);
  check(digestClientContentPresentationContract(typed)==item['digest']);
  validateClientContentPresentationContract(typed);
 }
 check(digestClientContentPresentationContract(compiledContentPresentationContract)==compiledContentPresentationContractDigest);
 check(digestClientContentPresentationContract(missingDeclarationContentPresentationContract)==missingDeclarationContentPresentationContractDigest);
 for(final entry in compiledContentPresentationCollections.entries){
  for(final bad in [null,[entry.value.first,entry.value.first],['unknown'],[' '+entry.value.first]]){
   final wire=<String,Object?>{...compiledContentPresentationContract.toWire(),entry.key:bad};
   var rejected=false;try{canonicalClientContentPresentationCollections(wire);}on FormatException{rejected=true;}check(rejected);
  }
 }
}
`

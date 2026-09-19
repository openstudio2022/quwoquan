package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/tools/internal/presentationcontract"
)

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func TestClientPresentationRealTypedTransportGolden(t *testing.T) {
	root, err := filepath.Abs("../../contracts/metadata")
	if err != nil {
		t.Fatal(err)
	}
	source, err := contractcodegen.NewDocumentSource(root, []string{"_shared/types.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	fields, err := loadFields(source, "_shared/types.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := resolveNamedTransportClosure(fields, []string{presentationcontract.TypeName}); err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	ranked := filepath.Join(dir, "ranked")
	if err := os.MkdirAll(filepath.Join(ranked, "models"), 0755); err != nil {
		t.Fatal(err)
	}
	goPath := filepath.Join(dir, "transport.go")
	// 使用真正 ranked transport writer；time import 是现役完整闭包的一部分。
	transport := generateRankedWindowGoTransport(fields, &operationsFile{})
	transport += "\nvar _ = time.Time{}\n"
	if !strings.Contains(transport, "ContentTypes []ContentType") {
		t.Fatal("ranked transport lost typed enum slice")
	}
	writeEnumFixtureFile(t, goPath, []byte(transport))
	if err := writeClientPresentationContractArtifacts(source, ranked, goPath); err != nil {
		t.Fatal(err)
	}
	writeEnumFixtureFile(t, filepath.Join(dir, "go.mod"), []byte("module golden\ngo 1.24\n"))
	writeEnumFixtureFile(t, filepath.Join(dir, "golden_test.go"), []byte(realTypedGoldenRunner))
	cmd := exec.Command("go", "test", ".")
	cmd.Dir = dir
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("real typed golden: %v\n%s", err, output)
	}
	manifest := filepath.Join(dir, "manifest.json")
	if err := writeProvenanceManifest(manifest, []string{ranked, goPath}); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"client_presentation_contract.py", "client_presentation_contract.golden.json", "transport.go"} {
		if !strings.Contains(string(data), name) {
			t.Fatal("manifest missed", name)
		}
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func TestRankedWindowArtifactsOptionalOwnerAndGoOutput(t *testing.T) {
	root := t.TempDir()
	empty, err := contractcodegen.NewDocumentSource(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	absentOutput := filepath.Join(root, "absent", "model")
	if err := generateRankedWindowArtifacts(empty, "recommendation/model", absentOutput, "must-not-write.go"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Dir(absentOutput)); !os.IsNotExist(err) {
		t.Fatal("absent ranked owner emitted artifacts")
	}
	shared, err := os.ReadFile("../../contracts/metadata/_shared/types.yaml")
	if err != nil {
		t.Fatal(err)
	}
	writeEnumFixtureFile(t, filepath.Join(root, "_shared/types.yaml"), shared)
	owner := "recommendation/ranked_recommendation_window"
	writeEnumFixtureFile(t, filepath.Join(root, owner, "fields.yaml"), []byte("types: {}\n"))
	writeEnumFixtureFile(t, filepath.Join(root, owner, "operations.yaml"), []byte("api_routes:\n  - operation: GetCapabilities\n    request_entity: ClientContentPresentationContract\n"))
	source, err := contractcodegen.NewDocumentSource(root, []string{"_shared/types.yaml", owner + "/fields.yaml", owner + "/operations.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	for _, goOutput := range []string{"", "  "} {
		output := filepath.Join(t.TempDir(), "model")
		if err := generateRankedWindowArtifacts(source, "recommendation/model", output, goOutput); err != nil {
			t.Fatal(err)
		}
		helper := filepath.Join(filepath.Dir(output), "ranked_recommendation_window/models/client_presentation_contract.py")
		if _, err := os.Stat(helper); err != nil {
			t.Fatal("Python helper missing when Go absent", err)
		}
	}
	// 不丢失失败分支：owner 存在但 operations 缺失必须失败，不得视为可选 owner 缺席。
	invalid, err := contractcodegen.NewDocumentSource(root, []string{"_shared/types.yaml", owner + "/fields.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	if err := generateRankedWindowArtifacts(invalid, "recommendation/model", filepath.Join(t.TempDir(), "model"), ""); err == nil {
		t.Fatal("incomplete ranked owner accepted")
	}
}

const realTypedGoldenRunner = `package feeddeliverypage
import("encoding/json";"os";"testing")
func TestRealTypedGolden(t *testing.T){
 data,err:=os.ReadFile("ranked/models/client_presentation_contract.golden.json");if err!=nil{t.Fatal(err)}
 var cases []struct{Collections ClientContentPresentationContract;Canonical string;Digest string}
 if err:=json.Unmarshal(data,&cases);err!=nil{t.Fatal(err)}
 for _,c:=range cases{
  raw,err:=CanonicalClientContentPresentationContract(c.Collections);if err!=nil||string(raw)!=c.Canonical{t.Fatalf("canonical mismatch %s %v",raw,err)}
  c.Collections.ContractDigest=c.Digest;if err:=ValidateClientContentPresentationContract(c.Collections);err!=nil{t.Fatal(err)}
  wire,err:=json.Marshal(c.Collections);if err!=nil{t.Fatal(err)}
  if _,err:=DecodeClientContentPresentationContract(wire);err!=nil{t.Fatal(err)}
 }
 invalid:=CompiledContentPresentationContract();invalid.ContentTypes=[]ContentType{"unknown"}
 if _,err:=DigestClientContentPresentationContract(invalid);err==nil{t.Fatal("typed unknown accepted")}
 invalid=CompiledContentPresentationContract();invalid.ContentTypes=append(invalid.ContentTypes,invalid.ContentTypes[0])
 if _,err:=DigestClientContentPresentationContract(invalid);err==nil{t.Fatal("duplicate accepted")}
 for _,bad:=range []string{"null","{}","[]","{\"contentTypes\":[\"unknown\"]}","{\"contentTypes\":[],\"contentTypes\":[]}"}{if _,err:=DecodeClientContentPresentationContract([]byte(bad));err==nil{t.Fatal("invalid JSON accepted")}}
 baseline,err:=DecodeClientContentPresentationContract(nil);if err!=nil||baseline.ContractDigest!=MissingDeclarationContentPresentationContractDigest{t.Fatal("baseline mismatch")}
}
`

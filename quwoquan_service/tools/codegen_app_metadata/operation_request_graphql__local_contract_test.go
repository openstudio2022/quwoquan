package main

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
	"os"
	"os/exec"
	"path/filepath"
	"quwoquan_service/internal/testsupport/contractsview"
	"strings"
	"testing"
)

func TestFullAppAndSpecializedGraphQLGenerationPrivateChain(t *testing.T) {
	root, e := filepath.Abs("../..")
	if e != nil {
		t.Fatal(e)
	}
	temp := t.TempDir()
	app := filepath.Join(temp, "app")
	graphPath := filepath.Join(root, "generated/contract_graph.json")
	graphRaw, e := os.ReadFile(graphPath)
	if e != nil {
		t.Fatal(e)
	}
	accepted := filepath.Join(root, "../quwoquan_app/tool/cloud_codegen/contract_graph.lock.json")
	before, e := os.ReadFile(accepted)
	if e != nil {
		t.Fatal(e)
	}
	var lock map[string]any
	if json.Unmarshal(before, &lock) != nil {
		t.Fatal("lock decode")
	}
	lock["contractGraph"].(map[string]any)["sha256"] = fmt.Sprintf("%x", sha256.Sum256(graphRaw))
	privateRaw, _ := json.Marshal(lock)
	privateLock := filepath.Join(temp, "private-lock.json")
	if e = os.WriteFile(privateLock, privateRaw, 0600); e != nil {
		t.Fatal(e)
	}
	// 复制现役包壳及非生成support，随后由完整production生成器覆盖所有生成输出。
	originalLib := filepath.Join(root, "../quwoquan_app/packages/quwoquan_cloud_contracts/lib")
	if e = filepath.WalkDir(originalLib, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		relative, err := filepath.Rel(originalLib, path)
		if err != nil {
			return err
		}
		target := filepath.Join(app, "packages/quwoquan_cloud_contracts/lib", relative)
		if entry.IsDir() {
			return os.MkdirAll(target, 0700)
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		return os.WriteFile(target, raw, 0600)
	}); e != nil {
		t.Fatal(e)
	}
	view := contractsview.Build(t)
	// 测试私有图仅重建同一canonical sources，避免当前工作图尚未包含descriptor绑定更新。
	generatedGraph := filepath.Join(temp, "graph.json")
	run := func(args ...string) {
		t.Helper()
		cmd := exec.Command("go", args...)
		cmd.Dir = root
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("%v failed: %v\n%s", args, err, out)
		}
	}
	run("run", "./tools/qwq_contract", "generate", "--metadata-dir", view, "--repo-root", filepath.Dir(root), "--profile", "commercial", "--output", generatedGraph, "--go-security-output", filepath.Join(temp, "security.go"))
	graphRaw, e = os.ReadFile(generatedGraph)
	if e != nil {
		t.Fatal(e)
	}
	lock["contractGraph"].(map[string]any)["sha256"] = fmt.Sprintf("%x", sha256.Sum256(graphRaw))
	privateRaw, _ = json.Marshal(lock)
	if e = os.WriteFile(privateLock, privateRaw, 0600); e != nil {
		t.Fatal(e)
	}
	run("run", "./tools/codegen_app_metadata", "--metadata-dir", view, "--contract-graph", generatedGraph, "--contract-graph-lock", privateLock, "--app-dir", app, "--generated-manifest", filepath.Join(app, "manifest.json"))
	run("run", "./tools/codegen_graphql_app_client", "--metadata-dir", view, "--contract-graph", generatedGraph, "--app-lock", privateLock, "--app-dir", app, "--target", "post-collection")
	content, e := os.ReadFile(filepath.Join(app, "packages/quwoquan_cloud_contracts/lib/src/generated/requests/content/content_operation_contracts.g.requests.g.dart"))
	if e != nil {
		t.Fatal(e)
	}
	for _, required := range []string{"GetPostCollectionQuery", "GetPostCollectionManagementQuery", "PostCollectionManagement", "sha256Hash", "first"} {
		if !strings.Contains(string(content), required) {
			t.Fatalf("full generation missing %s", required)
		}
	}
	// 同一临时输出的通用 encoder 与专用 client 必须编码完全相同的 persisted variables。
	configRaw, e := os.ReadFile(filepath.Join(root, "../quwoquan_app/.dart_tool/package_config.json"))
	if e != nil {
		t.Fatal(e)
	}
	var packages map[string]any
	if json.Unmarshal(configRaw, &packages) != nil {
		t.Fatal("package config decode")
	}
	packageConfigBase := filepath.Join(root, "../quwoquan_app/.dart_tool")
	for _, entry := range packages["packages"].([]any) {
		p := entry.(map[string]any)
		uri := p["rootUri"].(string)
		if !strings.Contains(uri, ":") {
			absolute, e := filepath.Abs(filepath.Join(packageConfigBase, uri))
			if e != nil {
				t.Fatal(e)
			}
			p["rootUri"] = "file://" + absolute + "/"
		}
		if p["name"] == "quwoquan_cloud_contracts" {
			p["rootUri"] = "file://" + filepath.Join(app, "packages/quwoquan_cloud_contracts") + "/"
		}
	}
	configRaw, _ = json.Marshal(packages)
	configPath := filepath.Join(temp, "package_config.json")
	if e = os.WriteFile(configPath, configRaw, 0600); e != nil {
		t.Fatal(e)
	}
	script := strings.ReplaceAll(graphqlPrivateEncoderCheck, "CLIENT_URI", "file://"+filepath.Join(app, "lib/runtime/transport/graphql_read/generated/post_collection.g.dart"))
	scriptPath := filepath.Join(temp, "check.dart")
	if e = os.WriteFile(scriptPath, []byte(script), 0600); e != nil {
		t.Fatal(e)
	}
	cmd := exec.Command("dart", "--packages="+configPath, scriptPath)
	cmd.Dir = root
	output, e := cmd.CombinedOutput()
	if e != nil {
		t.Fatalf("same-output Dart encoder chain: %v\n%s", e, output)
	}
	after, e := os.ReadFile(accepted)
	if e != nil || string(before) != string(after) {
		t.Fatal("private generation modified accepted lock")
	}
}

const graphqlPrivateEncoderCheck = `
import 'dart:convert';
import 'CLIENT_URI';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
class Capture implements CloudOperationExecutor {
 Object? response;
 Object? body;
 @override Future<T> send<T>(CloudOperationContract operation,{required CloudOperationInvocationContext context,required CloudOperationResponseDecoder<T> responseDecoder,required CloudOperationRequestEncoder requestEncoder}) async {body=requestEncoder().body;return responseDecoder(response);}
}
Future<void> main() async {
 final executor=Capture();final client=GeneratedPostCollectionGraphQLClient(executor);
 const context=CloudOperationInvocationContext(surfaceId:'postCollection',clientPageId:'test',actor:CloudOperationActorContext());
 final request=GetPostCollectionQuery(collectionId:'c',limit:7,cursor:'after');
 executor.response={'data':{'postCollection':{'collectionId':'c','ownerPersonaId':'p','name':'n','coverAssetId':null,'visibility':'public','version':1,'members':[],'visibleCount':0,'nextCursor':null,'canManage':false}}};
 await client.get(request,context:context);
 final generic=encodeContentPostCollectionGetPostCollectionGeneratedRequest(request).body;
 if(jsonEncode(generic)!=jsonEncode(executor.body))throw StateError('generic and specialized variables differ');
 final management=GetPostCollectionManagementQuery(collectionId:'c');
 executor.response={'data':{'postCollectionManagement':{'collectionId':'c','name':'n','coverAssetId':null,'visibility':'private','version':1,'members':[]}}};
 await client.management(management,context:context);
 final second=encodeContentPostCollectionGetPostCollectionManagementGeneratedRequest(management).body;
 if(jsonEncode(second)!=jsonEncode(executor.body))throw StateError('management variables differ');
}
`

func TestGraphQLRequestVariableClosure(t *testing.T) {
	model := requestModelSpec{Name: "GetPostCollectionQuery", Fields: []fieldDef{{Name: "collectionId", Type: "string", Constraints: []string{"NOT_BLANK"}}, {Name: "limit", Type: "int", Constraints: []string{"NOT_NULL"}}, {Name: "cursor", Type: "string", Constraints: []string{"NULLABLE"}}}}
	doc := `query PostCollection($collectionId: ID!, $first: Int! = 20, $after: String) { postCollection(collectionId:$collectionId,first:$first,after:$after){name} }`
	validate := func(text string, bindings map[string]string, constants map[string]any, m requestModelSpec) error {
		q, e := parser.ParseQuery(&ast.Source{Input: text})
		if e != nil {
			return e
		}
		return validateGraphQLRequestVariables(m, q.Operations[0].VariableDefinitions, bindings, constants)
	}
	bindings := map[string]string{"collectionId": "collectionId", "first": "limit", "after": "cursor"}
	if e := validate(doc, bindings, nil, model); e != nil {
		t.Fatal(e)
	}
	for _, change := range []string{"unbound", "extra", "type", "nullable"} {
		t.Run(change, func(t *testing.T) {
			b := map[string]string{}
			for k, v := range bindings {
				b[k] = v
			}
			text := doc
			switch change {
			case "unbound":
				delete(b, "first")
			case "extra":
				b["unknown"] = "limit"
			case "type":
				text = strings.Replace(text, "$first: Int!", "$first: String!", 1)
			case "nullable":
				text = strings.Replace(text, "$after: String", "$after: String!", 1)
			}
			if validate(text, b, nil, model) == nil {
				t.Fatal("invalid variable binding accepted")
			}
		})
	}
	management := requestModelSpec{Name: "GetPostCollectionManagementQuery", Fields: model.Fields[:1]}
	q := `query PostCollectionManagement($collectionId: ID!, $first: Int! = 100){postCollectionManagement(collectionId:$collectionId){members(first:$first){postId}}}`
	if e := validate(q, map[string]string{"collectionId": "collectionId"}, map[string]any{"first": 100}, management); e != nil {
		t.Fatal(e)
	}
	if validate(q, map[string]string{"collectionId": "collectionId"}, nil, management) == nil {
		t.Fatal("unbound management variable accepted")
	}
	if validate(q, map[string]string{"collectionId": "collectionId"}, map[string]any{"first": "100"}, management) == nil {
		t.Fatal("wrong management constant type accepted")
	}
	for _, bad := range []string{strings.Replace(q, "$collectionId: ID!", "$collectionId: Int!", 1), strings.Replace(q, "$collectionId: ID!", "$collectionId: ID", 1), strings.Replace(q, "$first: Int!", "$extra: Int!, $first: Int!", 1)} {
		if validate(bad, map[string]string{"collectionId": "collectionId"}, map[string]any{"first": 100}, management) == nil {
			t.Fatal("management variable drift accepted")
		}
	}
	if validate(q, map[string]string{"collectionId": "collectionId", "extra": "collectionId"}, map[string]any{"first": 100}, management) == nil {
		t.Fatal("extra management binding accepted")
	}
}

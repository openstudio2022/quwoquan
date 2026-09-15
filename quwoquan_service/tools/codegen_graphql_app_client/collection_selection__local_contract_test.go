package main

// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/spec.md#dom-001
import (
	"encoding/json"
	"github.com/vektah/gqlparser/v2"
	"github.com/vektah/gqlparser/v2/ast"
	"os"
	"os/exec"
	"path/filepath"
	codegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"quwoquan_service/internal/testsupport/contractsview"
	"strings"
	"testing"
)

func TestCollectionPrivateGeneratedDartDecoderRejectsSelectionDrift(t *testing.T) {
	root, e := filepath.Abs("../..")
	if e != nil {
		t.Fatal(e)
	}
	dir := t.TempDir()
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
	// 仅测试私有锁用于运行生成器，不调用 accept、不签发或写入 canonical receipt。
	var lock map[string]any
	if json.Unmarshal(before, &lock) != nil {
		t.Fatal("lock parse")
	}
	binding := lock["contractGraph"].(map[string]any)
	binding["sha256"] = sha256Hex(graphRaw)
	privateRaw, _ := json.Marshal(lock)
	privateLock := filepath.Join(dir, "test-only-lock.json")
	if e = os.WriteFile(privateLock, privateRaw, 0600); e != nil {
		t.Fatal(e)
	}
	options := Options{MetadataDir: contractsview.Build(t), ContractGraphPath: graphPath, AppLockPath: privateLock, RegistryPath: filepath.Join(root, "services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json"), MetadataPath: filepath.Join(root, "services/api-edge/resources/policies/graphql_read/query_metadata.json"), SchemaPath: filepath.Join(root, "services/api-edge/resources/policies/graphql_read/schema.graphqls")}
	generated, _, e := GenerateCollection(options)
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(dir, "client.dart"), generated, 0600); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(dir, "check.dart"), []byte(collectionDecoderCheck), 0600); e != nil {
		t.Fatal(e)
	}
	cmd := exec.Command("dart", "--packages="+filepath.Join(root, "../quwoquan_app/.dart_tool/package_config.json"), filepath.Join(dir, "check.dart"))
	out, e := cmd.CombinedOutput()
	if e != nil {
		t.Fatalf("private generated decoder: %v\n%s", e, out)
	}
	after, e := os.ReadFile(accepted)
	if e != nil || string(before) != string(after) {
		t.Fatal("accepted lock modified by private test")
	}
}

const collectionDecoderCheck = `
import 'dart:convert';
import 'client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
class Execute implements CloudOperationExecutor {
 Object? response;
 @override Future<T> send<T>(CloudOperationContract operation,{required CloudOperationInvocationContext context,required CloudOperationResponseDecoder<T> responseDecoder,required CloudOperationRequestEncoder requestEncoder}) async {return responseDecoder(response);}
}
Future<void> main() async {
 final executor=Execute();final client=GeneratedPostCollectionGraphQLClient(executor);
 const context=CloudOperationInvocationContext(surfaceId:'postCollection',clientPageId:'test',actor:CloudOperationActorContext());
 for(final management in [false,true]) {
 final root=management?'postCollectionManagement':'postCollection';
 final member=management?<String,Object?>{'postId':'p','readable':false,'title':null}:<String,Object?>{'postId':'p','contentType':'video','title':'作品'};
 final data=<String,Object?>{'collectionId':'c','name':'合集','coverAssetId':null,'visibility':'public','version':1,'members':[member],if(!management)...{'ownerPersonaId':'owner','visibleCount':1,'nextCursor':null,'canManage':false}};
 Future<void> run(Map<String,dynamic> value) async {executor.response={'data':{root:value}};if(management){await client.management(GetPostCollectionManagementQuery(collectionId:'c'),context:context);}else{await client.get(GetPostCollectionQuery(collectionId:'c',limit:20),context:context);}}
 await run(Map<String,dynamic>.from(data));
 for(final nested in [false,true]) {for(final mutation in ['delete','extra','rename','type']){
 final value=jsonDecode(jsonEncode(data)) as Map<String,dynamic>;
 final target=nested?(value['members'] as List).first as Map<String,dynamic>:value;
 final name=nested?'title':'name';
 switch(mutation){case 'delete':target.remove(name);break;case 'extra':target['unknown']=true;break;case 'rename':target['wrong']=target.remove(name);break;case 'type':target[name]=true;break;}
 var rejected=false;try{await run(value);}on FormatException{rejected=true;}
 if(!rejected)throw StateError('$root $nested $mutation accepted');
 }}
 for(final badMembers in [null,[null],{'postId':'p'}]){final value=Map<String,dynamic>.from(data)..['members']=badMembers;var rejected=false;try{await run(value);}on FormatException{rejected=true;}if(!rejected)throw StateError('invalid list accepted');}
 }
}
`

func TestCollectionSelectionMatchesCanonicalDecoderFields(t *testing.T) {
	source, err := codegen.NewSource(contractsview.Build(t), validate.ProfileBaseline)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join("..", "..", "services/api-edge/resources/policies/graphql_read/schema.graphqls"))
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ document, response, projection string }{{"post_collection.graphql", "PostCollectionPage", "post_collection_page.yaml"}, {"post_collection_management.graphql", "PostCollectionManagementView", "post_collection_management_view.yaml"}} {
		t.Run(test.response, func(t *testing.T) {
			document, err := os.ReadFile(filepath.Join("..", "..", "services/content-service/contracts/content/post_collection/persisted_queries", test.document))
			if err != nil {
				t.Fatal(err)
			}
			check := func(schemaText, queryText string) error {
				s, e := gqlparser.LoadSchema(&ast.Source{Input: schemaText})
				if e != nil {
					return e
				}
				q, queryErrors := gqlparser.LoadQuery(s, queryText)
				if queryErrors != nil {
					return queryErrors
				}
				return validateCollectionSelection(source, s, q, test.response, test.projection)
			}
			if err = check(string(raw), string(document)); err != nil {
				t.Fatal(err)
			}
			mutations := []struct{ name, schema, query string }{
				{"missing root", string(raw), strings.Replace(string(document), "    name\n", "", 1)},
				{"missing nested", string(raw), strings.Replace(string(document), " title }", " }", 1)},
				{"extra root", strings.Replace(string(raw), "type "+test.response+" {", "type "+test.response+" { extra: String", 1), strings.Replace(string(document), "    name\n", "    name\n    extra\n", 1)},
				{"alias wrong name", string(raw), strings.Replace(string(document), "    name\n", "    other: name\n", 1)},
				{"scalar type", strings.ReplaceAll(string(raw), "version: Int!", "version: String!"), string(document)},
				{"nullable root", strings.ReplaceAll(string(raw), "name: String!", "name: String"), string(document)},
				{"nullable nested", strings.ReplaceAll(string(raw), "postId: ID!", "postId: ID"), string(document)},
				{"nullable list item", strings.ReplaceAll(strings.ReplaceAll(string(raw), "[PostCollectionMemberSummary!]!", "[PostCollectionMemberSummary]!"), "[PostCollectionManagedMember!]!", "[PostCollectionManagedMember]!"), string(document)},
			}
			for _, m := range mutations {
				t.Run(m.name, func(t *testing.T) {
					if check(m.schema, m.query) == nil {
						t.Fatal("selection/decoder drift accepted")
					}
				})
			}
		})
	}
}

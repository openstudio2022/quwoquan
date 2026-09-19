package main

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/openapi"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/design.md
func TestJSONQueryGeneratedBinderRuntime(t *testing.T) {
	source := &graph.ContractGraph{Documents: []ast.SourceDocument{{Path: "sample/context/item/fields.yaml", Content: json.RawMessage(`{"types":{"Request":{"fields":[{"name":"filter","type":"Filter"}]},"Filter":{"fields":[{"name":"label","type":"string","constraints":["MAX_LENGTH_8"]},{"name":"kinds","type":"[]Kind","constraints":["MAX_ITEMS_2"]},{"name":"count","type":"int","constraints":["MIN_0","MAX_5"]}]}},"enums":{"Kind":{"values":["one","two"]}}}`)}}}
	required := true
	route := serviceRouteYAML{Operation: "Lookup", RequestEntity: "Request", RequestBodyKind: "none", RequestBindings: requestBindingsYAML{Query: []requestBindingYAML{{Name: "filter", Field: "filter", Encoding: "json", MaxBytes: 100, Required: &required}}}}
	queries, err := resolveJSONQueries(source, "sample/context/item/operations.yaml", route)
	if err != nil {
		t.Fatal(err)
	}
	route.JSONQueries = queries
	directory := t.TempDir()
	route.Method = "GET"
	route.Path = "/items"
	feed := route
	feed.Operation = "GetFeed"
	feed.Path = "/feed"
	feed.Pagination = paginationYAML{DefaultItems: 10, MaximumItems: 20}
	feed.RequestBindings.Query = append(append([]requestBindingYAML(nil), route.RequestBindings.Query...), requestBindingYAML{Name: "limit", Field: "limit"})
	feedQueries, err := resolveJSONQueries(source, "sample/context/item/operations.yaml", feed)
	if err != nil {
		t.Fatal(err)
	}
	feed.JSONQueries = feedQueries
	if err := generateObjectHTTPScaffold([]serviceRouteYAML{route, feed}, directory, "sample/context/item/operations.yaml"); err != nil {
		t.Fatal(err)
	}
	directory = filepath.Join(directory, "transport")
	for name, content := range map[string]string{"go.mod": "module queryfixture\n\ngo 1.23\n", "binder_test.go": jsonQueryRuntimeTest} {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	command := exec.Command("go", "test", "-count=1", ".")
	command.Dir = directory
	command.Env = append(os.Environ(), "GOWORK=off")
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("generated runtime: %v\n%s", err, output)
	}
	contents, err := os.ReadFile(filepath.Join(directory, "json_query_bindings.go"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(contents), "r.Body") {
		t.Fatal("query binder must not consume body")
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-006
func TestJSONQueryActualPresentationContractsCanonicalDigest(t *testing.T) {
	source := contentTestContractSource(t)
	groups, err := loadServiceRoutes(source, "content-service")
	if err != nil {
		t.Fatal(err)
	}
	circleGroups, err := loadServiceRoutes(source, "circle-service")
	if err != nil {
		t.Fatal(err)
	}
	groups = append(groups, circleGroups...)
	matched := 0
	for _, group := range groups {
		for _, route := range group.Routes {
			if route.RequestEntity != "ContentDiscoveryFeedQuery" && route.RequestEntity != "ContentAuthorPostsQuery" && route.RequestEntity != "ContentPostDetailQuery" && route.RequestEntity != "CircleFeedQuery" {
				continue
			}
			for _, query := range route.JSONQueries {
				if query.Binding.Field != "clientPresentationContract" {
					continue
				}
				matched++
				digest := query.Schema.Properties["contractDigest"]
				if digest == nil || digest.Pattern != "^sha256:[0-9a-f]{64}$" || *digest.MinLength != 71 || *digest.MaxLength != 71 {
					t.Fatalf("%s lacks canonical digest schema: %+v", route.Operation, digest)
				}
				payload := map[string]any{}
				for key, field := range query.Schema.Properties {
					if field.Type == "array" {
						payload[key] = []string{}
					}
				}
				valid := "sha256:" + strings.Repeat("a", 64)
				payload["contractDigest"] = valid
				raw, err := json.Marshal(payload)
				if err != nil {
					t.Fatal(err)
				}
				directory := t.TempDir()
				if err := generateJSONQueryBindings([]serviceRouteYAML{route}, directory); err != nil {
					t.Fatal(err)
				}
				runner := fmt.Sprintf(actualPresentationQueryRunner, string(raw), query.Binding.Name, query.Function, valid)
				for name, content := range map[string]string{"go.mod": "module queryfixture\n\ngo 1.23\n", "binder_test.go": runner} {
					if err := os.WriteFile(filepath.Join(directory, name), []byte(content), 0600); err != nil {
						t.Fatal(err)
					}
				}
				cmd := exec.Command("go", "test", "-count=1", ".")
				cmd.Dir = directory
				cmd.Env = append(os.Environ(), "GOWORK=off")
				if output, err := cmd.CombinedOutput(); err != nil {
					t.Fatalf("%s generated binder: %v\n%s", route.Operation, err, output)
				}
			}
		}
	}
	if matched != 4 {
		t.Fatalf("actual Content+Circle query count=%d, want exactly four", matched)
	}
	snapshots, err := openapi.Generate(source.Graph())
	if err != nil {
		t.Fatal(err)
	}
	for _, domain := range []string{"content", "circle"} {
		found := false
		for _, snapshot := range snapshots {
			if snapshot.Domain == domain { found = strings.Contains(string(snapshot.Content), "pattern: ^sha256:[0-9a-f]{64}$") }
		}
		if !found { t.Fatalf("actual %s OpenAPI lacks digest pattern", domain) }
	}
}

const actualPresentationQueryRunner = `package transport
import("encoding/json";"net/http/httptest";"net/url";"strings";"testing")
func TestActualCanonicalDigest(t *testing.T){
 raw:=%q
 call:=func(value string)error{request:=httptest.NewRequest("GET","/",nil);request.URL.RawQuery=url.Values{%q:{value}}.Encode();_,err:=%s(request);return err}
 if err:=call(raw);err!=nil{t.Fatal(err)}
 for _,digest:=range []string{"",strings.Repeat("a",64),"sha256:"+strings.Repeat("A",64),"sha256:"+strings.Repeat("a",63),"sha256:"+strings.Repeat("a",65),"sha256:"+strings.Repeat("g",64),%q+"\n"}{
  var payload map[string]any;if err:=json.Unmarshal([]byte(raw),&payload);err!=nil{t.Fatal(err)};payload["contractDigest"]=digest;bytes,_:=json.Marshal(payload)
  if err:=call(string(bytes));err==nil{t.Fatal("accepted malformed digest",digest)}
 }
}
`

const jsonQueryRuntimeTest = `package transport
import("net/http/httptest";"net/url";"strings";"testing")
func TestStrict(t *testing.T){
 good:="{\"label\":\"中文\",\"kinds\":[\"one\"],\"count\":2}"
 request:=httptest.NewRequest("GET","/?filter="+url.QueryEscape(good),nil)
 got,err:=BindGeneratedLookupFilterQuery(request);if err!=nil||got.Label!="中文"||got.Count!=2{t.Fatalf("roundtrip: %+v %v",got,err)}
 feed,err:=BindGeneratedGetFeedParams(request);if err!=nil||feed.Filter==nil||feed.Filter.Label!="中文"||feed.Limit!=10{t.Fatalf("feed typed integration: %+v %v",feed,err)}
 for _,raw:=range []string{"", "null","[]","123", "{}",good+" {}",strings.Replace(good,"\"one\"","\"unknown\"",1),strings.Replace(good,"2}","6}",1),strings.Replace(good,"2}","2,\"extra\":true}",1),strings.Replace(good,"中文","123456789",1),strings.Replace(good,"[\"one\"]","[\"one\",\"one\",\"one\"]",1),strings.Repeat(" ",100)+good}{
  req:=httptest.NewRequest("GET","/?filter="+url.QueryEscape(raw),nil);if _,err:=BindGeneratedLookupFilterQuery(req);err==nil{t.Errorf("accepted %q",raw)}
 }
 for _,query:=range []string{"", "filter="+url.QueryEscape(good)+"&filter="+url.QueryEscape(good),"filter=%zz"}{
  req:=httptest.NewRequest("GET","/",nil);req.URL.RawQuery=query;if _,err:=BindGeneratedLookupFilterQuery(req);err==nil{t.Errorf("accepted query %q",query)}
 }
}
`

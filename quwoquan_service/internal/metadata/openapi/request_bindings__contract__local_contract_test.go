package openapi

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"
)

func TestRequestBindingsGeneratePathAndQueryButNeverInjectedParameters(t *testing.T) {
	required := true
	parameters := requestBindingParameters(ast.Operation{
		PathTemplate: "/content/posts/{postId}",
		RequestBindings: &ast.RequestBindings{
			Path:     []ast.RequestBinding{{Name: "postId", Field: "postId"}},
			Query:    []ast.RequestBinding{{Name: "limit", Field: "limit", Required: &required}},
			Injected: []ast.RequestBinding{{Name: "actorId", Field: "actorId"}},
		},
	})
	if len(parameters) != 2 {
		t.Fatalf("parameters=%+v", parameters)
	}
	if parameters[0].Name != "postId" || parameters[0].In != "path" || !parameters[0].Required {
		t.Fatalf("path parameter=%+v", parameters[0])
	}
	if parameters[1].Name != "limit" || parameters[1].In != "query" || !parameters[1].Required {
		t.Fatalf("query parameter=%+v", parameters[1])
	}
}

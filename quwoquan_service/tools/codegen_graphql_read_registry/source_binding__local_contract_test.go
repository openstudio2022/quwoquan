package main

import (
	"encoding/json"
	"strings"
	"testing"

	metadataast "quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/graph"
)

func TestContractGraphOperationIsTheOnlyObjectAuthorizationAndTypeSource(t *testing.T) {
	t.Parallel()
	source := contractcodegen.NewSourceFromGraph("metadata", &graph.ContractGraph{
		Operations: []metadataast.Operation{{
			ID: "content.post.GetPost", ObjectID: "content.post",
			Kind: metadataast.OperationKindQuery, KindExplicit: true,
			Principal: "public", OwnershipPolicy: "visibility_filtered",
			SourcePath: "content/content/post/operations.yaml",
			Commercial: metadataast.CommercialBinding{Status: "ready", Explicit: true},
		}},
	})

	binding, err := deriveOperationBinding(source, "content.post.GetPost")
	if err != nil {
		t.Fatalf("derive operation binding: %v", err)
	}
	if binding.operationType != "query" || len(binding.objectIDs) != 1 ||
		binding.objectIDs[0] != "content.post" || binding.authorization.Principal != "public" ||
		binding.authorization.OwnershipPolicy != "visibility_filtered" {
		t.Fatalf("binding=%+v", binding)
	}
}

func TestObjectOwnedPersistedBindingDriftFailsClosed(t *testing.T) {
	t.Parallel()
	document := []byte("query ContentPostDetail($postId: ID!) { contentPostDetail(postId: $postId) { postId } }\n")
	owner := ownerPersistedQueryBinding{
		Schema: ownerPersistedQuerySchema, CanonicalOperationID: "content.post.GetPost",
		ObjectID: "content.post", Document: "content_post_detail.graphql",
		OperationName: "ContentPostDetail", OperationType: "query",
		SHA256Hash: strings.Repeat("0", 64),
	}
	ownerJSON, err := json.Marshal(owner)
	if err != nil {
		t.Fatal(err)
	}
	source := contractcodegen.NewSourceFromGraph("metadata", &graph.ContractGraph{
		Documents: []metadataast.SourceDocument{{
			Path:    "content/content/post/persisted_queries/content_post_detail.yaml",
			Content: ownerJSON,
		}},
	})
	err = validateOwnerPersistedQuery(
		source,
		metadataEntry{
			Document:             "persisted_queries/content_post_detail.graphql",
			CanonicalOperationID: "content.post.GetPost",
		},
		operationBinding{
			operationType: "query", objectIDs: []string{"content.post"},
			ownerSourceDir: "content/content/post",
		},
		"ContentPostDetail",
		document,
	)
	if err == nil || !strings.Contains(err.Error(), "sha256Hash drift") {
		t.Fatalf("error=%v", err)
	}
}

func TestContractGraphOperationLookupFailsClosed(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name       string
		operations []metadataast.Operation
		want       string
	}{
		{name: "missing", want: "not found"},
		{name: "duplicate", operations: []metadataast.Operation{
			readyQuery("content.post.GetPost"), readyQuery("content.post.GetPost"),
		}, want: "duplicate"},
		{name: "command", operations: []metadataast.Operation{{
			ID: "content.post.GetPost", ObjectID: "content.post",
			Kind: metadataast.OperationKindCommand, KindExplicit: true,
			Commercial: metadataast.CommercialBinding{Status: "ready", Explicit: true},
		}}, want: "query"},
		{name: "commercial blocked", operations: []metadataast.Operation{{
			ID: "content.post.GetPost", ObjectID: "content.post",
			Kind: metadataast.OperationKindQuery, KindExplicit: true,
			Commercial: metadataast.CommercialBinding{Status: "blocked", Explicit: true},
		}}, want: "commercial ready"},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			source := contractcodegen.NewSourceFromGraph("metadata", &graph.ContractGraph{Operations: test.operations})
			_, err := deriveOperationBinding(source, "content.post.GetPost")
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error=%v, want substring %q", err, test.want)
			}
		})
	}
}

func readyQuery(id string) metadataast.Operation {
	return metadataast.Operation{
		ID: id, ObjectID: "content.post", Kind: metadataast.OperationKindQuery,
		KindExplicit: true, Principal: "public", OwnershipPolicy: "visibility_filtered",
		SourcePath: "content/content/post/operations.yaml",
		Commercial: metadataast.CommercialBinding{Status: "ready", Explicit: true},
	}
}

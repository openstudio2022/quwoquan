package graph_test

import (
	"testing"

	contractgraph "quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

func TestRepositoryGetFeedOwnsDeliveryBudgets(t *testing.T) {
	t.Parallel()

	catalog, err := load.Load(contractsview.Build(t))
	if err != nil {
		t.Fatalf("load repository contract packets: %v", err)
	}
	graph := contractgraph.Build(catalog)
	for _, operation := range graph.Operations {
		if operation.ID != "content.post.GetFeed" {
			continue
		}
		if operation.Pagination == nil {
			t.Fatal("content.post.GetFeed pagination budget is missing")
		}
		if operation.Pagination.DefaultItems != 20 ||
			operation.Pagination.MaximumItems != 20 {
			t.Fatalf("content.post.GetFeed pagination = %+v", operation.Pagination)
		}
		if operation.ResponseAdmission == nil ||
			operation.ResponseAdmission.MaximumBodyBytes != 2*1024*1024 {
			t.Fatalf(
				"content.post.GetFeed response admission = %+v",
				operation.ResponseAdmission,
			)
		}
		return
	}
	t.Fatal("content.post.GetFeed operation not found")
}

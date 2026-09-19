package graph_test

import (
	"encoding/json"
	"reflect"
	"testing"

	"quwoquan_service/internal/metadata/ast"
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

// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
func TestRepositoryFeedDeliveryUsesSharedEnvelopeIdentity(t *testing.T) {
	t.Parallel()
	catalog, err := load.Load(contractsview.Build(t))
	if err != nil {
		t.Fatalf("load repository contract packets: %v", err)
	}
	const owner = "content.feed_delivery_page"
	want := []ast.FieldDefinition{
		{Entity: "FeedDeliveryPage", Name: "items", Type: "[]FeedDeliveryListItem"},
		{Entity: "FeedDeliveryPage", Name: "clientPresentationContract", Type: "ClientContentPresentationContract"},
		{Entity: "FeedDeliveryListItem", Name: "envelope", Type: "ListItemPresentationEnvelope"},
		{Entity: "FeedPageDeliveredRecommendationItem", Name: "envelope", Type: "ListItemPresentationEnvelope"},
		{Entity: "FeedPageDeliveredRecommendationItem", Name: "ordinal", Type: "int"},
		{Entity: "FeedPageDeliveredRecommendationItem", Name: "featureSnapshotDigest", Type: "string"},
		{Entity: "FeedPageDeliveredRecommendationItem", Name: "itemFeatureSnapshot", Type: "object"},
	}
	for _, expected := range want {
		found := false
		for _, field := range catalog.Governance.Fields {
			if field.ObjectID == owner && field.Entity == expected.Entity && field.Name == expected.Name {
				if field.Type != expected.Type {
					t.Fatalf("%s.%s type = %s, want %s", field.Entity, field.Name, field.Type, expected.Type)
				}
				found = true
			}
		}
		if !found {
			t.Fatalf("missing delivery contract field %s.%s", expected.Entity, expected.Name)
		}
	}
	var eventFields []string
	for _, field := range catalog.Governance.Fields {
		if field.ObjectID != owner {
			continue
		}
		if field.Entity == "FeedPageDeliveredRecommendationItem" {
			eventFields = append(eventFields, field.Name)
		}
		if field.Name == "objectCards" || field.Name == "anchorIndex" || field.Name == "postId" {
			t.Fatalf("delivery fact must not own a sidecar or a second Post identity: %+v", field)
		}
	}
	if !reflect.DeepEqual(eventFields, []string{"envelope", "featureSnapshotDigest", "itemFeatureSnapshot", "ordinal"}) {
		t.Fatalf("delivery event must have one shared identity envelope: %v", eventFields)
	}
	for _, definition := range catalog.Governance.Types {
		if definition.Name == "ListItemPresentationEnvelope" && definition.ObjectID != "" {
			t.Fatalf("delivery envelope must remain shared rather than object-owned: %+v", definition)
		}
	}
	for _, document := range catalog.Documents {
		if document.Path != "content/content/feed_delivery_page/storage.yaml" {
			continue
		}
		var storage struct {
			RedisCache []ast.StorageRedisCache `json:"redis_cache"`
		}
		if err := json.Unmarshal(document.Content, &storage); err != nil {
			t.Fatalf("decode typed delivery storage: %v", err)
		}
		if len(storage.RedisCache) != 3 {
			t.Fatalf("delivery storage must retain value/index/metadata: %+v", storage.RedisCache)
		}
		value := storage.RedisCache[0]
		if value.MaxItems != 20 || value.MaxObjectCards != 0 || value.MaxValueBytes != 65536 ||
			value.TTLSeconds == nil || *value.TTLSeconds != 600 || value.QuotaShards != 256 ||
			value.MaxActivePerScope != 400 || value.MaxLiveRecordsPerQuotaShard != 512 ||
			value.MaxLiveBytesPerQuotaShard != 33554432 || value.GlobalMaxLiveRecords != 131072 ||
			value.GlobalMaxLiveBytes != 8589934592 {
			t.Fatalf("unified delivery quota or fixed TTL drifted: %+v", value)
		}
		return
	}
	t.Fatal("delivery page storage authoring document is missing")
}

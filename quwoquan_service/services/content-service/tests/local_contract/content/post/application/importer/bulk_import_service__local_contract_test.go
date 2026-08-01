package importer_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/application/importer"
	"strings"
	"testing"
)

type recordingBulkImportStore struct {
	items []BulkImportItem
}

func (s *recordingBulkImportStore) UpsertDiscoveryFeedItem(_ context.Context, item BulkImportItem) error {
	s.items = append(s.items, item)
	return nil
}

func (s *recordingBulkImportStore) UpsertEntityTags(_ context.Context, _ string, _ []string) error {
	return nil
}

func TestBulkImportDerivesActiveRefsAndRejectsCandidates(t *testing.T) {
	store := &recordingBulkImportStore{}
	service := NewBulkImportService(store)
	input := strings.NewReader(
		`{"postId":"post_1","title":"semantic","semanticMentions":[` +
			`{"kind":"entity","status":"pending_review","candidateId":"candidate_entity_1"},` +
			`{"kind":"tag","status":"published","targetRef":"Topic/旅行/高原"}]}` + "\n" +
			`{"postId":"post_2","entityRefs":["candidate:entity:2"]}` + "\n",
	)

	result, err := service.ImportNDJSON(context.Background(), input)
	if err != nil {
		t.Fatal(err)
	}
	if result.Total != 2 || result.Success != 1 || result.Failed != 1 {
		t.Fatalf("result = %+v", result)
	}
	if len(store.items) != 1 {
		t.Fatalf("stored items = %d", len(store.items))
	}
	item := store.items[0]
	if len(item.EntityRefs) != 0 {
		t.Fatalf("pending entity refs = %#v", item.EntityRefs)
	}
	if len(item.Tags) != 1 || item.Tags[0] != "Topic/旅行/高原" {
		t.Fatalf("published tag refs = %#v", item.Tags)
	}
}

func TestBulkImportRequiresSystemCreatorDisclosure(t *testing.T) {
	store := &recordingBulkImportStore{}
	service := NewBulkImportService(store)
	input := strings.NewReader(
		`{"postId":"post_ok","authorId":"agent_author_travel_000000001",` +
			`"creatorProfileId":"agent_creator_travel_000000001",` +
			`"creatorArchetype":"travel_blogger",` +
			`"creatorProfileVersion":"1.0.0",` +
			`"creatorDisclosure":{"type":"platform_virtual_creator","displayText":"平台虚拟创作者","visible":true},` +
			`"experienceClaimMode":"editorial_synthesis",` +
			`"authorQualitySignals":{"qualityScore":0.86,"fatigueScore":0.2,"riskTier":"low"}}` + "\n" +
			`{"postId":"post_bad","authorId":"agent_author_travel_000000002",` +
			`"creatorProfileId":"agent_creator_travel_000000002",` +
			`"creatorArchetype":"travel_blogger",` +
			`"creatorProfileVersion":"1.0.0",` +
			`"experienceClaimMode":"editorial_synthesis"}` + "\n",
	)

	result, err := service.ImportNDJSON(context.Background(), input)
	if err != nil {
		t.Fatal(err)
	}
	if result.Total != 2 || result.Success != 1 || result.Failed != 1 {
		t.Fatalf("result = %+v", result)
	}
	if len(store.items) != 1 {
		t.Fatalf("stored items = %d", len(store.items))
	}
	item := store.items[0]
	if item.CreatorProfileID != "agent_creator_travel_000000001" || item.CreatorArchetype != "travel_blogger" {
		t.Fatalf("creator projection not stored: %+v", item)
	}
	if !item.CreatorDisclosure.Visible {
		t.Fatalf("creator disclosure not stored: %+v", item.CreatorDisclosure)
	}
}

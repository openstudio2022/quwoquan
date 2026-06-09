package search

import (
	"context"
	"testing"
	"time"
)

func sampleDocs() []Document {
	return []Document{
		{
			ObjectType: ObjectTypeContentPost, ObjectID: "post_camp",
			Title: "四川露营旅行攻略", Summary: "整理营地、路线和注意事项",
			ContentType: "article", Visibility: "public",
			Tags:      []string{"Topic/旅行/露营"},
			Freshness: time.Date(2026, 3, 1, 0, 0, 0, 0, time.UTC),
			Fields:    map[string]string{"authorDisplayName": "alice"},
		},
		{
			ObjectType: ObjectTypeContentPost, ObjectID: "post_walk",
			Title: "城市散步指南", Summary: "周末散步路线",
			ContentType: "article", Visibility: "public",
			Freshness: time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC),
		},
		{
			ObjectType: ObjectTypeUserProfile, ObjectID: "user_alice",
			Title: "alice", Summary: "户外创作者", Visibility: "public",
		},
		{
			ObjectType: ObjectTypeChatMessage, ObjectID: "chat_secret",
			Title: "川西集合时间", Visibility: "private",
			Fields: map[string]string{"conversationId": "conv_1"},
		},
	}
}

func TestRetrieveRanksByTermCoverage(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Terms:   []string{"四川", "露营", "攻略"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 {
		t.Fatalf("hits=%d want 1: %#v", len(resp.Hits), resp.Hits)
	}
	if resp.Hits[0].ObjectID != "post_camp" {
		t.Fatalf("top=%q want post_camp", resp.Hits[0].ObjectID)
	}
	if resp.Hits[0].Target != TargetArticle {
		t.Fatalf("target=%q want article", resp.Hits[0].Target)
	}
	if len(resp.Citations) != 1 {
		t.Fatalf("citations=%#v", resp.Citations)
	}
}

func TestRetrieveNameAnchorResolvesAuthor(t *testing.T) {
	// names=[alice] + targets=[article] must associate by author without type.
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Names:   []string{"alice"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 || resp.Hits[0].ObjectID != "post_camp" {
		t.Fatalf("expected post_camp by author anchor, got %#v", resp.Hits)
	}
}

func TestRetrieveIDDirectHitReadsDetail(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		IDs:     []string{"post_walk"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 || resp.Hits[0].ObjectID != "post_walk" {
		t.Fatalf("expected direct id hit post_walk, got %#v", resp.Hits)
	}
}

func TestRetrieveMixedTargetsAreMerged(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle, TargetUser},
		Terms:   []string{"alice"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	gotUser := false
	for _, h := range resp.Hits {
		if h.Target == TargetUser && h.ObjectID == "user_alice" {
			gotUser = true
		}
	}
	if !gotUser {
		t.Fatalf("expected user hit in mixed retrieve, got %#v", resp.Hits)
	}
}

func TestRetrieveTimeRangeFilters(t *testing.T) {
	from := time.Date(2026, 2, 1, 0, 0, 0, 0, time.UTC)
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Terms:   []string{"路线"},
		Filters: RetrieveFilters{TimeRange: &TimeRange{From: from}},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	for _, h := range resp.Hits {
		if h.ObjectID == "post_walk" {
			t.Fatalf("post_walk is before timeRange and must be filtered: %#v", resp.Hits)
		}
	}
}

func TestRetrieveTagFilter(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Terms:   []string{"攻略"},
		Filters: RetrieveFilters{Tags: []string{"露营"}},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 || resp.Hits[0].ObjectID != "post_camp" {
		t.Fatalf("tag filter should keep only tagged post, got %#v", resp.Hits)
	}
}

func TestRetrievePermissionGateHidesPrivateChat(t *testing.T) {
	// Without viewer membership the private chat must not appear.
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetChat},
		Terms:   []string{"集合"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 0 {
		t.Fatalf("private chat must be hidden, got %#v", resp.Hits)
	}

	// With membership it becomes visible.
	resp, err = Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetChat},
		Terms:   []string{"集合"},
	}, NewSliceBackend(sampleDocs()), Viewer{AllowedChatIDs: map[string]bool{"conv_1": true}})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 1 || resp.Hits[0].ObjectID != "chat_secret" {
		t.Fatalf("member should see chat, got %#v", resp.Hits)
	}
}

func TestRetrieveBlocksSensitiveTerms(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{TargetArticle},
		Terms:   []string{"博彩", "攻略"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	if len(resp.Hits) != 0 {
		t.Fatalf("sensitive query must block, got %#v", resp.Hits)
	}
	if len(resp.DegradeSignals) != 1 || resp.DegradeSignals[0].Code != "SEARCH.USER.sensitive_query" {
		t.Fatalf("degrade=%#v", resp.DegradeSignals)
	}
}

func TestRetrieveUnknownTargetDegrades(t *testing.T) {
	resp, err := Retrieve(context.Background(), RetrieveRequest{
		Targets: []Target{"webpage"},
		Terms:   []string{"露营"},
	}, NewSliceBackend(sampleDocs()), Viewer{})
	if err != nil {
		t.Fatalf("retrieve err=%v", err)
	}
	found := false
	for _, d := range resp.DegradeSignals {
		if d.Code == "SEARCH.PLANNER.unknown_target" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected unknown_target degrade, got %#v", resp.DegradeSignals)
	}
}

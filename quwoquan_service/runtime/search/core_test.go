package search

import "testing"

func TestExecuteRanksByQuerySignalsAndBuildsCitations(t *testing.T) {
	resp := Execute(Request{Query: "四川露营攻略", Limit: 2}, []Document{
		{
			ObjectType:   ObjectTypeContentPost,
			ObjectID:     "post_low",
			Title:        "城市散步指南",
			Summary:      "周末散步路线",
			SourceDomain: "content",
			Visibility:   "public",
		},
		{
			ObjectType:   ObjectTypeContentPost,
			ObjectID:     "post_high",
			Title:        "四川露营旅行攻略",
			Summary:      "整理营地、路线和注意事项",
			Tags:         []string{"Topic/四川/露营"},
			SourceDomain: "content",
			Visibility:   "public",
		},
	})
	if len(resp.Hits) != 1 {
		t.Fatalf("hits=%d, want 1", len(resp.Hits))
	}
	if resp.Hits[0].ObjectID != "post_high" {
		t.Fatalf("top object=%q", resp.Hits[0].ObjectID)
	}
	if len(resp.Citations) != 1 || resp.Citations[0].ObjectType != ObjectTypeContentPost {
		t.Fatalf("citations=%#v", resp.Citations)
	}
	if resp.InterpretedQuery.Normalized != "四川露营攻略" {
		t.Fatalf("normalized=%q", resp.InterpretedQuery.Normalized)
	}
}

func TestExecuteSupportsPinyinInitialAndSynonymVariants(t *testing.T) {
	resp := Execute(Request{Query: "scly", Limit: 5}, []Document{{
		ObjectType:   ObjectTypeEntityHomepage,
		ObjectID:     "hp_sichuan",
		Title:        "四川旅游主页",
		Summary:      "景点和路线",
		SourceDomain: "entity",
		Visibility:   "public",
	}})
	if len(resp.Hits) != 1 {
		t.Fatalf("expected pinyin initial hit, got %#v", resp.Hits)
	}

	resp = Execute(Request{Query: "旅行", Limit: 5}, []Document{{
		ObjectType:   ObjectTypeContentPost,
		ObjectID:     "post_travel",
		Title:        "周末出行路线",
		Summary:      "适合朋友一起游玩",
		SourceDomain: "content",
		Visibility:   "public",
	}})
	if len(resp.Hits) != 1 {
		t.Fatalf("expected synonym hit, got %#v", resp.Hits)
	}
}

func TestExecuteBlocksSensitiveQuery(t *testing.T) {
	resp := Execute(Request{Query: "博彩攻略", Limit: 5}, []Document{{
		ObjectType: ObjectTypeWebDocument,
		ObjectID:   "web_1",
		Title:      "公开网页",
	}})
	if len(resp.Hits) != 0 {
		t.Fatalf("blocked query should not return hits: %#v", resp.Hits)
	}
	if len(resp.DegradeSignals) != 1 || resp.DegradeSignals[0].Code != "SEARCH.USER.sensitive_query" {
		t.Fatalf("degrade=%#v", resp.DegradeSignals)
	}
}

func TestExecuteUsesTagEntitySignalsForReasons(t *testing.T) {
	resp := Execute(Request{Query: "旅行", Limit: 5}, []Document{{
		ObjectType:   ObjectTypeContentPost,
		ObjectID:     "post_entity",
		Title:        "周末出行路线",
		Summary:      "适合露营和拍照",
		Tags:         []string{"Topic/旅行/露营"},
		Entities:     []string{"entity:川西"},
		SourceDomain: "content",
		Visibility:   "public",
	}})
	if len(resp.Hits) != 1 {
		t.Fatalf("expected hit, got %#v", resp.Hits)
	}
	found := false
	for _, reason := range resp.Hits[0].Reasons {
		if reason.Code == "tag_entity_signal" {
			found = true
		}
	}
	if !found {
		t.Fatalf("expected tag/entity reason, got %#v", resp.Hits[0].Reasons)
	}
}

package post

import (
	"context"
	"reflect"
	"testing"

	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// R-CS06：发布侧 semanticMentions 端云契约。
// 客户端只写 semanticMentions（结构化数组），服务端把 published+valid 行投影成
// entityRefs/tagRefs；pending_review / rejected 行不进入 refs；published 行若
// targetRef 非法则整单拒绝（不静默丢弃）。
func TestCreatePostProjectsPublishedSemanticMentions(t *testing.T) {
	store := persistence.NewPostStore(nil)
	service := NewPostService(store)

	payload := map[string]any{
		"contentType": "micro",
		"authorId":    "author_sichuan",
		"body":        "九寨沟秋天的海子真的很美",
		"visibility":  "public",
		"semanticMentions": []any{
			map[string]any{
				"mentionId": "m_entity_published",
				"kind":      "entity",
				"status":    "published",
				"targetRef": "/entity/地点/景区/九寨沟",
			},
			map[string]any{
				"mentionId": "m_tag_published",
				"kind":      "tag",
				"status":    "published",
				"targetRef": "tag:topic:川西秋色",
			},
			map[string]any{
				"mentionId":   "m_entity_pending",
				"kind":        "entity",
				"status":      "pending_review",
				"candidateId": "cand_huanglong",
			},
			map[string]any{
				"mentionId": "m_tag_rejected",
				"kind":      "tag",
				"status":    "rejected",
				"targetRef": "tag:topic:被驳回",
			},
		},
	}

	post, err := service.CreatePost(context.Background(), payload)
	if err != nil {
		t.Fatalf("CreatePost returned error: %v", err)
	}

	if got, want := post.EntityRefs, []string{"/entity/地点/景区/九寨沟"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("EntityRefs = %#v, want %#v", got, want)
	}
	if got, want := post.TagRefs, []string{"tag:topic:川西秋色"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("TagRefs = %#v, want %#v", got, want)
	}

	// 持久化后从 store 读回，确认投影随实体一起落盘。
	stored, ok := store.FindByID(context.Background(), post.ID)
	if !ok {
		t.Fatalf("post %q not found in store", post.ID)
	}
	if got, want := stored.EntityRefs, []string{"/entity/地点/景区/九寨沟"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("stored EntityRefs = %#v, want %#v", got, want)
	}
	if got, want := stored.TagRefs, []string{"tag:topic:川西秋色"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("stored TagRefs = %#v, want %#v", got, want)
	}
}

func TestCreatePostRejectsPublishedMentionWithInvalidTargetRef(t *testing.T) {
	store := persistence.NewPostStore(nil)
	service := NewPostService(store)

	payload := map[string]any{
		"contentType": "micro",
		"authorId":    "author_sichuan",
		"body":        "正文足以通过非空校验",
		"visibility":  "public",
		"semanticMentions": []any{
			map[string]any{
				"mentionId": "m_entity_bad",
				"kind":      "entity",
				"status":    "published",
				// 缺少 entity:kind:id 的第三段，属于非法 targetRef。
				"targetRef": "entity:sight",
			},
		},
	}

	if _, err := service.CreatePost(context.Background(), payload); err == nil {
		t.Fatal("CreatePost should reject published mention with invalid targetRef")
	}
}

// 顶层 entityRefs/tagRefs 是只读投影：客户端若与 semanticMentions 投影不一致，
// 服务端必须拒绝，杜绝绕过 mention 直接写 refs 的旁路。
func TestCreatePostRejectsClientSuppliedRefsDivergingFromMentions(t *testing.T) {
	store := persistence.NewPostStore(nil)
	service := NewPostService(store)

	payload := map[string]any{
		"contentType": "micro",
		"authorId":    "author_sichuan",
		"body":        "正文足以通过非空校验",
		"visibility":  "public",
		"entityRefs":  []any{"/entity/地点/景区/不存在的实体"},
		"semanticMentions": []any{
			map[string]any{
				"mentionId": "m_entity_published",
				"kind":      "entity",
				"status":    "published",
				"targetRef": "/entity/地点/景区/九寨沟",
			},
		},
	}

	if _, err := service.CreatePost(context.Background(), payload); err == nil {
		t.Fatal("CreatePost should reject entityRefs diverging from published mentions projection")
	}
}

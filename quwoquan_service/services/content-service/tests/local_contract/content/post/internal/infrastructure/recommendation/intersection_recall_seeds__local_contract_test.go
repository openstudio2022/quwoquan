package local_contract

import (
	"testing"
	"time"

	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// 交集召回通道的准入口径合约：
//   - 只有物化出正边权的交集才能当种子（未物化 / 零权不进召回）；
//   - 人对象与非人对象分开连接（authorId vs entityRefs），不得混淆；
//   - 种子按边权降序截断，保证 $in 谓词有界且保留最强边。

func seedReason(kind, objectID, objectKind string, weight float64) intersectionapp.IntersectionReasonView {
	return intersectionapp.IntersectionReasonView{
		Kind:             kind,
		ActionTargetID:   objectID,
		RelationObjectID: objectID,
		ObjectKind:       objectKind,
		EdgeWeight:       weight,
		FreshAt:          time.Now().UTC().Format(time.RFC3339),
	}
}

func TestIntersectionRecallSeeds_SplitsPeopleAndObjects(t *testing.T) {
	people, objects := recommendation.IntersectionRecallSeeds(
		[]intersectionapp.IntersectionReasonView{
			seedReason("commonFollower", "u_peer", "person", 0.7),
			seedReason("coWishlistedEntity", "entity_place", "place", 0.5),
			seedReason("sharedCircle", "circle_hiking", "circle", 0.4),
		},
		10,
	)
	if len(people) != 1 || people[0] != "u_peer" {
		t.Fatalf("person edges must connect through authorId, got %v", people)
	}
	if len(objects) != 2 {
		t.Fatalf("non-person edges must connect through entityRefs, got %v", objects)
	}
}

func TestIntersectionRecallSeeds_DropsUnmaterialized(t *testing.T) {
	people, objects := recommendation.IntersectionRecallSeeds(
		[]intersectionapp.IntersectionReasonView{
			seedReason("commonFollower", "u_unmaterialized", "person", 0),
			seedReason("commonFollower", "", "person", 0.9),
			seedReason("commonFollower", "u_ok", "person", 0.3),
		},
		10,
	)
	if len(objects) != 0 {
		t.Fatalf("no object seeds expected, got %v", objects)
	}
	if len(people) != 1 || people[0] != "u_ok" {
		t.Fatalf("only materialized edges may seed recall, got %v", people)
	}
}

func TestIntersectionRecallSeeds_TruncatesByEdgeWeight(t *testing.T) {
	reasons := []intersectionapp.IntersectionReasonView{
		seedReason("commonFollower", "u_weak", "person", 0.1),
		seedReason("commonFollower", "u_strong", "person", 0.9),
		seedReason("commonFollower", "u_mid", "person", 0.5),
	}
	people, _ := recommendation.IntersectionRecallSeeds(reasons, 2)
	if len(people) != 2 {
		t.Fatalf("seed count must respect the limit, got %v", people)
	}
	if people[0] != "u_strong" || people[1] != "u_mid" {
		t.Fatalf("truncation must keep the strongest edges in order, got %v", people)
	}
}

// 同一对象出现多条交集时取最强边，避免弱边把强边挤掉或重复进 $in。
func TestIntersectionRecallSeeds_KeepsStrongestEdgePerObject(t *testing.T) {
	people, _ := recommendation.IntersectionRecallSeeds(
		[]intersectionapp.IntersectionReasonView{
			seedReason("commonFollower", "u_peer", "person", 0.2),
			seedReason("sharedFollowees", "u_peer", "person", 0.8),
		},
		10,
	)
	if len(people) != 1 || people[0] != "u_peer" {
		t.Fatalf("duplicate objects must collapse to one seed, got %v", people)
	}
}

package recommendation

import (
	"context"
	"testing"

	feedapp "quwoquan_service/services/content-service/internal/application/feed"
)

// 编译期契约：实体卡召回器必须实现 feed 层 ObjectCardProvider 端口。
var _ feedapp.ObjectCardProvider = (*MongoEntityCardProvider)(nil)

func TestEntityCardProviderNilAndEmptyInputsFailOpen(t *testing.T) {
	var nilProvider *MongoEntityCardProvider
	cards, err := nilProvider.ObjectCards(context.Background(), "u_1", 3)
	if err != nil || cards != nil {
		t.Fatalf("nil provider must fail open, cards=%v err=%v", cards, err)
	}

	provider := &MongoEntityCardProvider{}
	cards, err = provider.ObjectCards(context.Background(), "", 3)
	if err != nil || cards != nil {
		t.Fatalf("empty viewer must fail open, cards=%v err=%v", cards, err)
	}
	cards, err = provider.ObjectCards(context.Background(), "u_1", 0)
	if err != nil || cards != nil {
		t.Fatalf("non-positive limit must fail open, cards=%v err=%v", cards, err)
	}
}

func TestEntityCardKindAndRecallPathAreStable(t *testing.T) {
	// 归因契约：对象卡 objectKind 与 recallPath 是行为归因与 replay 分桶的
	// 稳定标识，漂移会破坏 behaviors objectKind 归因与看板口径。
	if EntityCardObjectKind != "entity_homepage" {
		t.Fatalf("entity card objectKind drifted: %s", EntityCardObjectKind)
	}
	if EntityCardRecallPath != "entity_card_affinity" {
		t.Fatalf("entity card recallPath drifted: %s", EntityCardRecallPath)
	}
}

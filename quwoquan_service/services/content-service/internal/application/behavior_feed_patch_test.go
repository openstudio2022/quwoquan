package application

import (
	"context"
	"encoding/json"
	"sync"
	"testing"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

// fakeSignalProcessor 是 BehaviorService 的最小 hotPath 替身：只接收信号、永不出错，
// 让测试聚焦于行为主链路成功后是否在安全边界发射推荐 patch。
type fakeSignalProcessor struct {
	batches [][]rtrec.BehaviorSignal
}

func (f *fakeSignalProcessor) ProcessSignal(_ context.Context, signal rtrec.BehaviorSignal) error {
	f.batches = append(f.batches, []rtrec.BehaviorSignal{signal})
	return nil
}

func (f *fakeSignalProcessor) ProcessSignalBatch(_ context.Context, signals []rtrec.BehaviorSignal) error {
	f.batches = append(f.batches, signals)
	return nil
}

// capturePatchPublisher 记录所有发射的 patch，用于断言端云 wire 契约。
type capturePatchPublisher struct {
	mu       sync.Mutex
	patches  []rtrec.FeedRealtimePatch
	channels []string
}

func (p *capturePatchPublisher) Publish(_ context.Context, channel, message string) error {
	var patch rtrec.FeedRealtimePatch
	if err := json.Unmarshal([]byte(message), &patch); err != nil {
		return err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.channels = append(p.channels, channel)
	p.patches = append(p.patches, patch)
	return nil
}

func newPatchBehaviorService(pub rtrec.FeedPatchPublisher) (*BehaviorService, *fakeSignalProcessor) {
	processor := &fakeSignalProcessor{}
	store := persistence.NewPostStore([]postmodel.Post{})
	emitter := rtrec.NewFeedPatchEmitter(pub)
	svc := NewBehaviorService(processor, store, WithFeedPatchEmitter(emitter))
	return svc, processor
}

// ProcessBatch 处理一条负反馈后，必须在主链路成功后发射 negative_feedback_removal patch
// 到该用户的 per-user 通道（端侧据此在安全边界剔除内容，不打断阅读位置）。
func TestProcessBatchEmitsNegativeRemovalPatch(t *testing.T) {
	pub := &capturePatchPublisher{}
	svc, processor := newPatchBehaviorService(pub)

	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{
		{
			UserID:    "user-100",
			Action:    "dislike",
			ContentID: "post-42",
			ChannelID: "recommend",
		},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(processor.batches) == 0 {
		t.Fatalf("hotPath should have received the signal batch")
	}
	if len(pub.patches) != 1 {
		t.Fatalf("want 1 emitted patch, got %d", len(pub.patches))
	}
	patch := pub.patches[0]
	if patch.PatchType != rtrec.FeedPatchNegativeFeedbackRemoval {
		t.Fatalf("patchType = %q", patch.PatchType)
	}
	if patch.ReasonCode != rtrec.FeedPatchReasonNegativeDislike {
		t.Fatalf("reasonCode = %q", patch.ReasonCode)
	}
	if patch.UserID != "user-100" {
		t.Fatalf("userId = %q", patch.UserID)
	}
	if len(patch.TargetPostIDs) != 1 || patch.TargetPostIDs[0] != "post-42" {
		t.Fatalf("targetPostIds = %v", patch.TargetPostIDs)
	}
	if pub.channels[0] != rtrec.FeedPatchChannelFor("user-100") {
		t.Fatalf("channel = %q", pub.channels[0])
	}
}

// 普通正向消费（点击/停留）不得触发任何推荐 patch（安全边界）。
func TestProcessBatchNoPatchForNeutralActions(t *testing.T) {
	pub := &capturePatchPublisher{}
	svc, _ := newPatchBehaviorService(pub)

	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{
		{UserID: "user-200", Action: "click", ContentID: "post-1"},
		{UserID: "user-200", Action: "dwell", ContentID: "post-1", DwellMs: 3200},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(pub.patches) != 0 {
		t.Fatalf("neutral actions must not emit patches, got %d", len(pub.patches))
	}
}

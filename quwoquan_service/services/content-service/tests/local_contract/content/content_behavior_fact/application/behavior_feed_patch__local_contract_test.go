package behavior_test

import (
	"context"
	"encoding/json"
	. "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	"sync"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func validBehaviorOccurredAt() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

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
			ClientEventID: "evt-negative-001",
			OccurredAt:    validBehaviorOccurredAt(),
			UserID:        "user-100",
			Action:        "dislike",
			ContentID:     "post-42",
			ChannelID:     "recommend",
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
		{
			ClientEventID: "evt-neutral-click-001",
			OccurredAt:    validBehaviorOccurredAt(),
			UserID:        "user-200",
			Action:        "click",
			ContentID:     "post-1",
		},
		{
			ClientEventID: "evt-neutral-dwell-001",
			OccurredAt:    validBehaviorOccurredAt(),
			UserID:        "user-200",
			Action:        "dwell",
			ContentID:     "post-1",
			Duration:      3.2,
		},
	})
	if err != nil {
		t.Fatalf("ProcessBatch: %v", err)
	}
	if len(pub.patches) != 0 {
		t.Fatalf("neutral actions must not emit patches, got %d", len(pub.patches))
	}
}

func TestPlaybackProgressIsObservationalAndEffectivePlayFailsClosed(t *testing.T) {
	if got := rtrec.SignalWeights["play_progress"]; got != 0 {
		t.Fatalf("seekable play_progress must not affect recommendation, got weight=%v", got)
	}
	if got := rtrec.SignalWeights["effective_play"]; got != 1 {
		t.Fatalf("qualified effective_play weight drifted: %v", got)
	}

	svc, processor := newPatchBehaviorService(&capturePatchPublisher{})
	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
		ClientEventID:   "evt-scrubbing-001",
		OccurredAt:      validBehaviorOccurredAt(),
		UserID:          "user-video",
		Action:          "effective_play",
		ContentID:       "post-video",
		SessionID:       "playback-session-1",
		State:           "scrubbing",
		EffectivePlayMS: 30_000,
		TotalUnits:      125,
	}})
	if err == nil {
		t.Fatal("scrubbing must not qualify as effective playback")
	}
	if len(processor.batches) != 0 {
		t.Fatal("rejected effective playback must not enter recommendation")
	}

	err = svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
		ClientEventID:   "evt-effective-001",
		OccurredAt:      validBehaviorOccurredAt(),
		UserID:          "user-video",
		Action:          "effective_play",
		ContentID:       "post-video",
		SessionID:       "playback-session-1",
		State:           "foreground_visible_playing",
		EffectivePlayMS: 8_000,
		ConsumedRatio:   0.064,
		TotalUnits:      125,
	}})
	if err != nil {
		t.Fatalf("valid effective playback rejected: %v", err)
	}
	if len(processor.batches) != 1 || len(processor.batches[0]) != 1 {
		t.Fatalf("qualified effective playback must enter one batch: %#v", processor.batches)
	}
	if got := processor.batches[0][0].EffectivePlayMS; got != 8_000 {
		t.Fatalf("effective play evidence was not propagated: %d", got)
	}
	if got := processor.batches[0][0].ClientEventID; got !=
		"effective_play:user-video:playback-session-1:post-video" {
		t.Fatalf("effective play dedupe identity drifted: %q", got)
	}
}

func TestBehaviorEventRequiresIdempotencyAndUsesOccurredAt(t *testing.T) {
	svc, processor := newPatchBehaviorService(&capturePatchPublisher{})
	occurredAt := time.Now().UTC().Add(-time.Hour).Truncate(time.Millisecond)

	err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
		ClientEventID: "evt-occurred-at-001",
		OccurredAt:    occurredAt.Format(time.RFC3339Nano),
		UserID:        "user-occurred-at",
		Action:        "click",
		ContentID:     "post-occurred-at",
	}})
	if err != nil {
		t.Fatalf("occurredAt event rejected: %v", err)
	}
	if got := processor.batches[0][0].Timestamp; !got.Equal(occurredAt) {
		t.Fatalf("signal timestamp = %s, want %s", got, occurredAt)
	}

	if err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
		OccurredAt: occurredAt.Format(time.RFC3339Nano),
		UserID:     "user-missing-id",
		Action:     "click",
		ContentID:  "post-missing-id",
	}}); err == nil {
		t.Fatal("missing clientEventId must be rejected")
	}
	if err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
		ClientEventID: "evt-missing-occurred-at",
		UserID:        "user-missing-time",
		Action:        "click",
		ContentID:     "post-missing-time",
	}}); err == nil {
		t.Fatal("missing occurredAt must be rejected")
	}
}

func TestProcessBatchRequiresCanonicalImpressionState(t *testing.T) {
	t.Parallel()

	for _, state := range []string{"", "unknown"} {
		state := state
		t.Run("reject_"+state, func(t *testing.T) {
			svc, processor := newPatchBehaviorService(&capturePatchPublisher{})
			err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
				ClientEventID: "evt-impression-invalid-" + state,
				OccurredAt:    validBehaviorOccurredAt(),
				UserID:        "user-impression-state",
				ContentID:     "post-impression-state",
				Action:        "impression",
				State:         state,
			}})
			if err == nil {
				t.Fatalf("impression state %q must be rejected", state)
			}
			if len(processor.batches) != 0 {
				t.Fatal("rejected impression must not enter recommendation")
			}
		})
	}

	for _, state := range []string{"visible", "impressed"} {
		state := state
		t.Run("accept_"+state, func(t *testing.T) {
			svc, processor := newPatchBehaviorService(&capturePatchPublisher{})
			err := svc.ProcessBatch(context.Background(), []BehaviorEventInput{{
				ClientEventID: "evt-impression-valid-" + state,
				OccurredAt:    validBehaviorOccurredAt(),
				UserID:        "user-impression-state",
				ContentID:     "post-impression-state",
				Action:        "impression",
				State:         state,
			}})
			if err != nil {
				t.Fatalf("canonical impression state %q rejected: %v", state, err)
			}
			if len(processor.batches) != 1 {
				t.Fatalf("canonical impression state %q was not processed", state)
			}
		})
	}
}

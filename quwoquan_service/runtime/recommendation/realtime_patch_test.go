package recommendation

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	"quwoquan_service/runtime/clientrealtime"
)

// recPatchContractYAML mirrors the metadata single source of truth so the test
// can assert Go constants/struct stay aligned with
// services/content-service/contracts/content/post/projections/recommendation_realtime_patch.yaml.
type recPatchContractYAML struct {
	RealtimeChannelTemplate string `yaml:"realtime_channel_template"`
	PatchTypes              []struct {
		ID string `yaml:"id"`
	} `yaml:"patch_types"`
	ReasonCodes []struct {
		ID        string `yaml:"id"`
		PatchType string `yaml:"patch_type"`
	} `yaml:"reason_codes"`
	RemovalDimensions []struct {
		ID string `yaml:"id"`
	} `yaml:"removal_dimensions"`
	EnvelopeFields []struct {
		Name string `yaml:"name"`
	} `yaml:"envelope_fields"`
}

func loadRecPatchContract(t *testing.T) recPatchContractYAML {
	t.Helper()
	path := filepath.Join(
		"..",
		"..",
		"services",
		"content-service",
		"contracts",
		"content",
		"post",
		"projections",
		"recommendation_realtime_patch.yaml",
	)
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read patch contract: %v", err)
	}
	var c recPatchContractYAML
	if err := yaml.Unmarshal(raw, &c); err != nil {
		t.Fatalf("unmarshal patch contract: %v", err)
	}
	return c
}

func TestFeedPatchContractConstantsMatchMetadata(t *testing.T) {
	c := loadRecPatchContract(t)

	if c.RealtimeChannelTemplate != feedPatchChannelTemplate {
		t.Fatalf("realtime_channel_template metadata=%q go=%q", c.RealtimeChannelTemplate, feedPatchChannelTemplate)
	}

	wantPatchTypes := []string{
		string(FeedPatchNewCandidateHint),
		string(FeedPatchNegativeFeedbackRemoval),
		string(FeedPatchRefreshSuggestion),
	}
	gotPatchTypes := make([]string, 0, len(c.PatchTypes))
	for _, pt := range c.PatchTypes {
		gotPatchTypes = append(gotPatchTypes, pt.ID)
	}
	assertSameSet(t, "patch_types", wantPatchTypes, gotPatchTypes)

	wantReasons := []string{
		string(FeedPatchReasonNegativeDislike),
		string(FeedPatchReasonNegativeHideAuthor),
		string(FeedPatchReasonNegativeHideContentType),
		string(FeedPatchReasonNegativeReport),
		string(FeedPatchReasonRelationshipExpanded),
		string(FeedPatchReasonNewCandidatesAvailable),
		string(FeedPatchReasonSessionFatigue),
		string(FeedPatchReasonFeedStaleness),
	}
	gotReasons := make([]string, 0, len(c.ReasonCodes))
	patchTypeSet := map[string]struct{}{}
	for _, pt := range wantPatchTypes {
		patchTypeSet[pt] = struct{}{}
	}
	for _, rc := range c.ReasonCodes {
		gotReasons = append(gotReasons, rc.ID)
		if _, ok := patchTypeSet[rc.PatchType]; !ok {
			t.Fatalf("reason %q bound to unknown patch_type %q", rc.ID, rc.PatchType)
		}
		if !knownFeedPatchReason(FeedPatchReasonCode(rc.ID)) {
			t.Fatalf("reason %q in metadata not a known Go constant", rc.ID)
		}
	}
	assertSameSet(t, "reason_codes", wantReasons, gotReasons)

	wantDims := []string{
		string(FeedPatchRemovalPost),
		string(FeedPatchRemovalAuthor),
		string(FeedPatchRemovalContentType),
	}
	gotDims := make([]string, 0, len(c.RemovalDimensions))
	for _, d := range c.RemovalDimensions {
		gotDims = append(gotDims, d.ID)
	}
	assertSameSet(t, "removal_dimensions", wantDims, gotDims)

	// envelope json tags must match metadata envelope_fields exactly, in order,
	// so the wire contract has a single source of truth (no second definition).
	if feedRealtimePatchWireType != "feed.patch" {
		t.Fatalf("feedRealtimePatchWireType=%q", feedRealtimePatchWireType)
	}

	wantFields := []string{}
	for _, f := range c.EnvelopeFields {
		wantFields = append(wantFields, f.Name)
	}
	gotFields := envelopeJSONTags(t)
	if !reflect.DeepEqual(gotFields, wantFields) {
		t.Fatalf("envelope fields drift:\n metadata=%v\n go json=%v", wantFields, gotFields)
	}
}

func envelopeJSONTags(t *testing.T) []string {
	t.Helper()
	typ := reflect.TypeOf(FeedRealtimePatch{})
	tags := make([]string, 0, typ.NumField())
	for i := 0; i < typ.NumField(); i++ {
		tag := typ.Field(i).Tag.Get("json")
		name := strings.Split(tag, ",")[0]
		if name == "" || name == "-" {
			t.Fatalf("field %s missing json tag", typ.Field(i).Name)
		}
		tags = append(tags, name)
	}
	return tags
}

func assertSameSet(t *testing.T, label string, want, got []string) {
	t.Helper()
	ws := append([]string(nil), want...)
	gs := append([]string(nil), got...)
	sort.Strings(ws)
	sort.Strings(gs)
	if !reflect.DeepEqual(ws, gs) {
		t.Fatalf("%s set mismatch:\n want=%v\n got =%v", label, ws, gs)
	}
}

// capturePublisher records every published (channel, message) for assertions.
type capturePublisher struct {
	mu       sync.Mutex
	messages []capturedPatch
	err      error
}

type capturedPatch struct {
	channel string
	patch   FeedRealtimePatch
	raw     string
}

func (p *capturePublisher) Publish(_ context.Context, channel, message string) error {
	if p.err != nil {
		return p.err
	}
	var patch FeedRealtimePatch
	var envelope clientrealtime.ClientRealtimeEventEnvelope
	if err := json.Unmarshal([]byte(message), &envelope); err != nil {
		return err
	}
	if envelope.Type != feedRealtimePatchWireType || envelope.EventID == "" || envelope.OccurredAt == "" {
		return errors.New("invalid feed realtime envelope")
	}
	if err := json.Unmarshal(envelope.Payload, &patch); err != nil {
		return err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.messages = append(p.messages, capturedPatch{channel: channel, patch: patch, raw: message})
	return nil
}

func (p *capturePublisher) all() []capturedPatch {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]capturedPatch(nil), p.messages...)
}

func newTestEmitter(pub FeedPatchPublisher) *FeedPatchEmitter {
	seq := 0
	return NewFeedPatchEmitter(pub,
		WithFeedPatchClock(func() time.Time { return time.Date(2026, 6, 19, 2, 0, 0, 0, time.UTC) }),
		WithFeedPatchIDFunc(func() string {
			seq++
			return "fpat_test_" + string(rune('0'+seq))
		}),
	)
}

func TestEmitNegativeFeedbackRemovalDislike(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{
			UserID:        "user-1",
			Action:        "dislike",
			ContentID:     "post-9",
			FeedRequestID: "freq-1",
			ChannelID:     "recommend",
		},
	})
	msgs := pub.all()
	if len(msgs) != 1 {
		t.Fatalf("want 1 patch, got %d", len(msgs))
	}
	got := msgs[0]
	if got.channel != "rt:rec:feed:user:user-1" {
		t.Fatalf("channel = %q", got.channel)
	}
	if got.patch.PatchType != FeedPatchNegativeFeedbackRemoval {
		t.Fatalf("patchType = %q", got.patch.PatchType)
	}
	if got.patch.ReasonCode != FeedPatchReasonNegativeDislike {
		t.Fatalf("reasonCode = %q", got.patch.ReasonCode)
	}
	if got.patch.RemovalDimension != FeedPatchRemovalPost {
		t.Fatalf("removalDimension = %q", got.patch.RemovalDimension)
	}
	if len(got.patch.TargetPostIDs) != 1 || got.patch.TargetPostIDs[0] != "post-9" {
		t.Fatalf("targetPostIds = %v", got.patch.TargetPostIDs)
	}
	if !got.patch.SafeToApplyWhileViewing {
		t.Fatalf("safeToApplyWhileViewing must be true")
	}
	if got.patch.FeedRequestID != "freq-1" {
		t.Fatalf("feedRequestId = %q", got.patch.FeedRequestID)
	}
	if got.patch.AffectedCount != 1 {
		t.Fatalf("affectedCount = %d", got.patch.AffectedCount)
	}
}

func TestEmitNegativeFeedbackRemovalHideAuthor(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{
			UserID:    "user-2",
			Action:    "hide_author",
			ContentID: "post-3",
			AuthorID:  "author-77",
		},
	})
	msgs := pub.all()
	if len(msgs) != 1 {
		t.Fatalf("want 1 patch, got %d", len(msgs))
	}
	got := msgs[0].patch
	if got.ReasonCode != FeedPatchReasonNegativeHideAuthor {
		t.Fatalf("reasonCode = %q", got.ReasonCode)
	}
	if got.RemovalDimension != FeedPatchRemovalAuthor {
		t.Fatalf("removalDimension = %q", got.RemovalDimension)
	}
	if got.RemovalDimensionValue != "author-77" {
		t.Fatalf("removalDimensionValue = %q", got.RemovalDimensionValue)
	}
}

func TestEmitNewCandidateHintOnRelationshipExpansion(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{
			UserID:    "user-3",
			Action:    "follow",
			ContentID: "post-1",
			AuthorID:  "author-1",
		},
	})
	msgs := pub.all()
	if len(msgs) != 1 {
		t.Fatalf("want 1 patch, got %d", len(msgs))
	}
	got := msgs[0].patch
	if got.PatchType != FeedPatchNewCandidateHint {
		t.Fatalf("patchType = %q", got.PatchType)
	}
	if got.ReasonCode != FeedPatchReasonRelationshipExpanded {
		t.Fatalf("reasonCode = %q", got.ReasonCode)
	}
	if len(got.TargetPostIDs) != 0 {
		t.Fatalf("hint must not carry targetPostIds, got %v", got.TargetPostIDs)
	}
	if got.AffectedCount != 1 {
		t.Fatalf("affectedCount = %d", got.AffectedCount)
	}
}

func TestEmitRefreshSuggestionOnSessionFatigue(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	signals := make([]BehaviorSignal, 0, sessionFatigueNegativeThreshold)
	for i := 0; i < sessionFatigueNegativeThreshold; i++ {
		signals = append(signals, BehaviorSignal{
			UserID:    "user-4",
			Action:    "dislike",
			ContentID: "post-" + string(rune('a'+i)),
		})
	}
	emitter.EmitForBehaviorBatch(context.Background(), signals)
	msgs := pub.all()
	// sessionFatigueNegativeThreshold removals + 1 refresh suggestion.
	if len(msgs) != sessionFatigueNegativeThreshold+1 {
		t.Fatalf("want %d patches, got %d", sessionFatigueNegativeThreshold+1, len(msgs))
	}
	var refresh *FeedRealtimePatch
	for i := range msgs {
		if msgs[i].patch.PatchType == FeedPatchRefreshSuggestion {
			refresh = &msgs[i].patch
		}
	}
	if refresh == nil {
		t.Fatalf("expected a refresh_suggestion patch")
	}
	if refresh.ReasonCode != FeedPatchReasonSessionFatigue {
		t.Fatalf("reasonCode = %q", refresh.ReasonCode)
	}
	if refresh.AffectedCount != sessionFatigueNegativeThreshold {
		t.Fatalf("affectedCount = %d", refresh.AffectedCount)
	}
}

func TestEmitSkipsGuestUser(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{UserID: "", Action: "dislike", ContentID: "post-1"},
	})
	if len(pub.all()) != 0 {
		t.Fatalf("guest user must not trigger patches")
	}
}

func TestEmitSkipsNonTriggerActions(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{UserID: "user-5", Action: "click", ContentID: "post-1"},
		{UserID: "user-5", Action: "dwell", ContentID: "post-1"},
		{UserID: "user-5", Action: "like", ContentID: "post-1"},
	})
	if len(pub.all()) != 0 {
		t.Fatalf("non-negative/non-relationship actions must not emit patches")
	}
}

func TestNilEmitterIsNoOp(t *testing.T) {
	var emitter *FeedPatchEmitter
	// Must not panic on nil receiver.
	emitter.EmitForBehaviorBatch(context.Background(), []BehaviorSignal{
		{UserID: "user-1", Action: "dislike", ContentID: "post-1"},
	})
	if err := emitter.EmitNewCandidateHint(context.Background(), NewCandidateHint{UserID: "u"}); err != nil {
		t.Fatalf("nil emitter EmitNewCandidateHint err = %v", err)
	}
}

func TestEmitterPublishErrorPropagates(t *testing.T) {
	pub := &capturePublisher{err: errors.New("redis down")}
	emitter := newTestEmitter(pub)
	err := emitter.EmitNegativeFeedbackRemoval(context.Background(), NegativeFeedbackRemoval{
		UserID:           "user-1",
		TargetPostIDs:    []string{"post-1"},
		ReasonCode:       FeedPatchReasonNegativeDislike,
		RemovalDimension: FeedPatchRemovalPost,
	})
	if err == nil {
		t.Fatalf("expected publish error to propagate")
	}
}

func TestPatchWireKeysStable(t *testing.T) {
	pub := &capturePublisher{}
	emitter := newTestEmitter(pub)
	if err := emitter.EmitRefreshSuggestion(context.Background(), RefreshSuggestion{
		UserID:     "user-1",
		ReasonCode: FeedPatchReasonFeedStaleness,
	}); err != nil {
		t.Fatalf("emit: %v", err)
	}
	msgs := pub.all()
	if len(msgs) != 1 {
		t.Fatalf("want 1 patch, got %d", len(msgs))
	}
	var envelope clientrealtime.ClientRealtimeEventEnvelope
	if err := json.Unmarshal([]byte(msgs[0].raw), &envelope); err != nil {
		t.Fatalf("unmarshal envelope: %v", err)
	}
	if envelope.Type != feedRealtimePatchWireType {
		t.Fatalf("envelope type=%q want %q", envelope.Type, feedRealtimePatchWireType)
	}
	var wire map[string]json.RawMessage
	if err := json.Unmarshal(envelope.Payload, &wire); err != nil {
		t.Fatalf("unmarshal payload wire: %v", err)
	}
	for _, key := range []string{"patchId", "patchType", "userId", "targetPostIds", "reasonCode", "affectedCount", "safeToApplyWhileViewing", "emittedAt"} {
		if _, ok := wire[key]; !ok {
			t.Fatalf("payload missing required key %q (got %v)", key, wireKeys(wire))
		}
	}
}

func wireKeys(m map[string]json.RawMessage) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func TestFeedPatchChannelForMatchesTemplate(t *testing.T) {
	if got := FeedPatchChannelFor("abc"); got != "rt:rec:feed:user:abc" {
		t.Fatalf("channel = %q", got)
	}
}

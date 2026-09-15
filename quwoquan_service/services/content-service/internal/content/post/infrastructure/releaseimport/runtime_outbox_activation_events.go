package releaseimport

import (
	"encoding/json"
	"fmt"
	events "quwoquan_service/services/content-service/generated/content/post/contract/event"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func releaseWireFence(f ActiveReleaseBinding) wire.ContentActiveReleaseFence {
	result := wire.ContentActiveReleaseFence{Found: f.Found, Environment: f.Environment, SourceOwner: f.SourceOwner, ReleaseId: f.ReleaseID, ManifestDigest: f.ManifestDigest, Revision: f.Revision, ProjectionVersion: f.ProjectionVersion}
	if f.Found {
		t := f.ActivatedAt.UTC()
		result.ActivatedAt = &t
	}
	return result
}

// 只产生已提交候选切换的控制事实；不把Post从live退出解释成作者删除。
func buildReleaseFenceEvent(before, after ActiveReleaseBinding) (postports.OutboxEvent, wire.ContentReleaseCommitReceipt, error) {
	receipt := wire.ContentReleaseCommitReceipt{Transition: wire.ContentReleaseFenceChangedPayload{Before: releaseWireFence(before), After: releaseWireFence(after)}}
	receipt.EventId = app.ReleaseFenceEventID(receipt.Transition.After)
	receipt.PayloadDigest = app.ReleaseFencePayloadDigest(receipt.Transition)
	q := wire.ReadContentReleaseCommitReceiptQuery{Expected: receipt.Transition.Before, Release: wire.ReleaseCandidateBinding{Environment: after.Environment, SourceOwner: after.SourceOwner, ReleaseId: after.ReleaseID, ManifestDigest: after.ManifestDigest}}
	if err := app.ValidateReleaseCommitReceipt(q, receipt); err != nil {
		return postports.OutboxEvent{}, receipt, fmt.Errorf("invalid fence transition: %w", err)
	}
	raw, err := json.Marshal(receipt.Transition)
	if err != nil {
		return postports.OutboxEvent{}, receipt, err
	}
	return postports.OutboxEvent{EventID: receipt.EventId, EventType: events.ContentReleaseFenceChanged, AggregateType: "Post", AggregateID: after.Environment + "/" + after.SourceOwner, AggregateVersion: after.Revision, OccurredAt: after.ActivatedAt, Payload: raw}, receipt, nil
}

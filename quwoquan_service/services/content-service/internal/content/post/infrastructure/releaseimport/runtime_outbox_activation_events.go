package releaseimport

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// BuildActivationPostLifecycleEvents 把 import 期生成的 Post lifecycle 事件绑定到
// 本次 activation 的完整 release tuple 与单调 activationRevision，供 Search /
// Recommendation 等异步消费者按 Content active fence 追平；tuple 或 revision 缺失
// 一律 fail closed，不生成可分叉的 activation 事件。
func BuildActivationPostLifecycleEvents(
	posts []PostDoc,
	deletedPosts []ImportedPostDeletionSnapshot,
	opts ImportOptions,
	occurredAt time.Time,
	predecessor ActiveReleaseBinding,
	activationRevision int64,
) ([]postports.OutboxEvent, error) {
	opts = NormalizeImportOptions(opts)
	if strings.TrimSpace(opts.SourceOwner) == "" ||
		strings.TrimSpace(opts.ReleaseID) == "" ||
		!sha256Pattern.MatchString(strings.TrimSpace(opts.ManifestDigest)) ||
		activationRevision <= 0 {
		return nil, fmt.Errorf("activation lifecycle release tuple is incomplete")
	}
	events, err := BuildImportedPostLifecycleEvents(posts, deletedPosts, opts, occurredAt)
	if err != nil {
		return nil, err
	}
	predecessorIdentity := "empty"
	if predecessor.Found {
		predecessorIdentity = strings.Join([]string{
			predecessor.SourceOwner, predecessor.ReleaseID,
			predecessor.ManifestDigest, fmt.Sprint(predecessor.Revision),
		}, ":")
	}
	for index := range events {
		var payload map[string]any
		if err := json.Unmarshal(events[index].Payload, &payload); err != nil {
			return nil, fmt.Errorf("decode activation lifecycle payload: %w", err)
		}
		payload["sourceOwner"] = opts.SourceOwner
		payload["releaseId"] = opts.ReleaseID
		payload["manifestDigest"] = opts.ManifestDigest
		payload["activationRevision"] = activationRevision
		encoded, err := json.Marshal(payload)
		if err != nil {
			return nil, fmt.Errorf("encode activation lifecycle payload: %w", err)
		}
		events[index].Payload = encoded
		events[index].EventID = fmt.Sprintf(
			"data-release-activation:%d:%d:%s:%s:%s:%s",
			activationRevision, opts.ProjectionVersion, opts.ReleaseID,
			predecessorIdentity, events[index].AggregateID, events[index].EventType,
		)
	}
	return events, nil
}

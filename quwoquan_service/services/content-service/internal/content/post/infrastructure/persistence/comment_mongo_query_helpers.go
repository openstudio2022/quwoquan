package persistence

import (
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

func topLevelAfter(cursor commentmodel.Cursor) bson.A {
	createdAt := time.Unix(0, cursor.CreatedAtNano).UTC()
	if cursor.Pinned {
		pinnedAt := time.Unix(0, cursor.PinnedAtNano).UTC()
		return bson.A{
			bson.M{"isPinned": false},
			bson.M{"isPinned": true, "pinnedAt": bson.M{"$lt": pinnedAt}},
			bson.M{"isPinned": true, "pinnedAt": pinnedAt, "createdAt": bson.M{"$lt": createdAt}},
			bson.M{
				"isPinned":  true,
				"pinnedAt":  pinnedAt,
				"createdAt": createdAt,
				"_id":       bson.M{"$lt": cursor.ID},
			},
		}
	}
	return bson.A{
		bson.M{
			"isPinned":  false,
			"createdAt": bson.M{"$lt": createdAt},
		},
		bson.M{
			"isPinned":  false,
			"createdAt": createdAt,
			"_id":       bson.M{"$lt": cursor.ID},
		},
	}
}

// topLevelHotAfter 是 sort=hot 档的 keyset 谓词：置顶段与 latest 档共享
// （pinnedAt desc, createdAt desc, _id desc），非置顶段按
// (hotScore desc, createdAt desc, _id desc) 续页。
// hotScore 字段由聚合写入与 relay 保证始终存在（含 0 分），谓词不做缺失兼容。
func topLevelHotAfter(cursor commentmodel.Cursor) bson.A {
	createdAt := time.Unix(0, cursor.CreatedAtNano).UTC()
	if cursor.Pinned {
		pinnedAt := time.Unix(0, cursor.PinnedAtNano).UTC()
		return bson.A{
			bson.M{"isPinned": false},
			bson.M{"isPinned": true, "pinnedAt": bson.M{"$lt": pinnedAt}},
			bson.M{"isPinned": true, "pinnedAt": pinnedAt, "createdAt": bson.M{"$lt": createdAt}},
			bson.M{
				"isPinned":  true,
				"pinnedAt":  pinnedAt,
				"createdAt": createdAt,
				"_id":       bson.M{"$lt": cursor.ID},
			},
		}
	}
	return bson.A{
		bson.M{"isPinned": false, "hotScore": bson.M{"$lt": cursor.HotScore}},
		bson.M{
			"isPinned":  false,
			"hotScore":  cursor.HotScore,
			"createdAt": bson.M{"$lt": createdAt},
		},
		bson.M{
			"isPinned":  false,
			"hotScore":  cursor.HotScore,
			"createdAt": createdAt,
			"_id":       bson.M{"$lt": cursor.ID},
		},
	}
}

func flatAfter(cursor commentmodel.Cursor) bson.A {
	createdAt := time.Unix(0, cursor.CreatedAtNano).UTC()
	return bson.A{
		bson.M{"createdAt": bson.M{"$lt": createdAt}},
		bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": cursor.ID}},
	}
}

func filterWithoutCursor(filter bson.M) bson.M {
	out := make(bson.M, len(filter))
	for key, value := range filter {
		if key != "$or" {
			out[key] = value
		}
	}
	return out
}

func applyCommentAuthorExclusions(filter bson.M, authorIDs []string) {
	excluded := uniqueNonEmptyStrings(authorIDs)
	if len(excluded) == 0 {
		return
	}
	filter["authorId"] = bson.M{"$nin": excluded}
}

func applyCommentAccountRestrictionVisibility(filter bson.M) {
	filter["accountRestricted"] = bson.M{"$ne": true}
}

func normalizeCommentPageLimit(limit int) int {
	if limit <= 0 {
		return 20
	}
	if limit > 100 {
		return 100
	}
	return limit
}

func commentOutboxCheckpoint(occurredAt time.Time, eventID string) string {
	return occurredAt.UTC().Format(time.RFC3339Nano) + "|" + eventID
}

func parseCommentOutboxCheckpoint(checkpoint string) (time.Time, string, error) {
	occurredAtValue, eventID, found := strings.Cut(strings.TrimSpace(checkpoint), "|")
	if !found || strings.TrimSpace(eventID) == "" {
		return time.Time{}, "", fmt.Errorf("invalid comment outbox checkpoint")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, occurredAtValue)
	if err != nil {
		return time.Time{}, "", fmt.Errorf("invalid comment outbox checkpoint: %w", err)
	}
	return occurredAt.UTC(), eventID, nil
}

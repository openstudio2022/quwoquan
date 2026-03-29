package persistence

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// Member list sort modes (align with contracts/metadata _shared/types.yaml MemberListSort).
const (
	SortMembersJoinedAsc      = "joined_asc"
	SortMembersDisplayNameAsc = "display_name_asc"
)

// NormalizeMemberListSort returns a supported sort key; unknown values map to joined_asc.
func NormalizeMemberListSort(s string) string {
	switch strings.TrimSpace(s) {
	case SortMembersDisplayNameAsc:
		return SortMembersDisplayNameAsc
	default:
		return SortMembersJoinedAsc
	}
}

type cursorJoinedAsc struct {
	T int64  `json:"t"` // joinedAt UnixNano UTC
	I string `json:"i"` // _id
}

type cursorDisplayNameAsc struct {
	D string `json:"d"` // displayName
	U string `json:"u"` // userId
}

func memberListCursorFilterJoined(cursor string) (bson.M, error) {
	if cursor == "" {
		return nil, nil
	}
	raw, err := base64.RawURLEncoding.DecodeString(cursor)
	if err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	var c cursorJoinedAsc
	if err := json.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	t := time.Unix(0, c.T).UTC()
	return bson.M{
		"$or": []bson.M{
			{"joinedAt": bson.M{"$gt": t}},
			{
				"$and": []bson.M{
					{"joinedAt": t},
					{"_id": bson.M{"$gt": c.I}},
				},
			},
		},
	}, nil
}

func memberListCursorFilterDisplayName(cursor string) (bson.M, error) {
	if cursor == "" {
		return nil, nil
	}
	raw, err := base64.RawURLEncoding.DecodeString(cursor)
	if err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	var c cursorDisplayNameAsc
	if err := json.Unmarshal(raw, &c); err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	return bson.M{
		"$or": []bson.M{
			{"displayName": bson.M{"$gt": c.D}},
			{
				"$and": []bson.M{
					{"displayName": c.D},
					{"userId": bson.M{"$gt": c.U}},
				},
			},
		},
	}, nil
}

// EncodeMemberListNextCursorJoined encodes a keyset cursor for joined_asc pagination.
func EncodeMemberListNextCursorJoined(joinedAt time.Time, id string) string {
	c := cursorJoinedAsc{T: joinedAt.UTC().UnixNano(), I: id}
	b, _ := json.Marshal(c)
	return base64.RawURLEncoding.EncodeToString(b)
}

// EncodeMemberListNextCursorDisplayName encodes a keyset cursor for display_name_asc pagination.
func EncodeMemberListNextCursorDisplayName(displayName, userID string) string {
	c := cursorDisplayNameAsc{D: displayName, U: userID}
	b, _ := json.Marshal(c)
	return base64.RawURLEncoding.EncodeToString(b)
}

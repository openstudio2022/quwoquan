package application

import (
	"encoding/base64"
	"encoding/json"
	"time"
)

type memberListDisplayNameCursor struct {
	DisplayName string `json:"d"`
	UserID      string `json:"u"`
}

// EncodeMemberListNextCursorDisplayName builds the opaque keyset cursor shared
// by member readers that use display_name_asc. Persistence owns parsing and
// querying; the application layer owns the externally observable page token.
func EncodeMemberListNextCursorDisplayName(displayName, userID string) string {
	payload, _ := json.Marshal(memberListDisplayNameCursor{
		DisplayName: displayName,
		UserID:      userID,
	})
	return base64.RawURLEncoding.EncodeToString(payload)
}

type memberListJoinedCursor struct {
	JoinedAtUnixNanos int64  `json:"t"`
	ID                string `json:"i"`
}

// EncodeMemberListNextCursorJoined builds the opaque keyset cursor for
// joined_asc consumers that need to scan a complete group roster.
func EncodeMemberListNextCursorJoined(joinedAt time.Time, id string) string {
	payload, _ := json.Marshal(memberListJoinedCursor{
		JoinedAtUnixNanos: joinedAt.UTC().UnixNano(),
		ID:                id,
	})
	return base64.RawURLEncoding.EncodeToString(payload)
}

package application

import (
	"time"

	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

// EncodeMemberListNextCursorDisplayName builds the opaque keyset cursor shared
// by member readers that use display_name_asc. Persistence owns parsing and
// querying; the application layer owns the externally observable page token.
func EncodeMemberListNextCursorDisplayName(displayName, userID string) string {
	return membershipmodel.EncodeDisplayNameCursor(displayName, userID)
}

// EncodeMemberListNextCursorJoined builds the opaque keyset cursor for
// joined_asc consumers that need to scan a complete group roster.
func EncodeMemberListNextCursorJoined(joinedAt time.Time, id string) string {
	return membershipmodel.EncodeJoinedCursor(joinedAt, id)
}

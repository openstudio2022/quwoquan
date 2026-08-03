package persistence

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// BumpMembersRosterRevision projects ConversationMembership changes into the
// Conversation summary. It does not expose or access membership persistence.
func (store *MongoChatStore) BumpMembersRosterRevision(
	ctx context.Context,
	conversationID string,
	memberCount *int,
) error {
	setDocument := bson.M{"updatedAt": time.Now()}
	if memberCount != nil {
		setDocument["memberCount"] = *memberCount
	}
	_, err := store.conversations.UpdateOne(ctx, bson.M{"_id": conversationID}, bson.M{
		"$inc": bson.M{"membersRosterRevision": 1},
		"$set": setDocument,
	})
	return err
}

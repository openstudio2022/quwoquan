package persistence

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

const (
	userAccountClosedInboxCollection   = "chat_user_account_closed_inbox"
	userAccountClosedFailureCollection = "chat_user_account_closed_failures"
	userAccountClosedFailureRetention  = 7 * 24 * time.Hour
	closedAccountDisplayName           = "已注销用户"
	closedAccountAnonymousIDPrefix     = "deleted_"
	syncSequenceKeyPrefix              = "sync:user:"
	syncPatchDeleteBatchSize           = int64(256)
)

type userAccountClosedInboxDocument struct {
	ID                      string     `bson:"_id"`
	EventDigest             string     `bson:"eventDigest"`
	AccountVersion          int64      `bson:"accountVersion"`
	AffectedConversationIDs []string   `bson:"affectedConversationIds,omitempty"`
	AppliedAt               time.Time  `bson:"appliedAt"`
	CompletedAt             *time.Time `bson:"completedAt,omitempty"`
}

// MongoUserAccountClosedProjection 把 eventId inbox 与 Chat 清理写入同一
// Mongo 事务；Redis 缓存失效在事务后执行，失败时由同一 pending stream
// message 重试，已落 inbox 的重放不会再次改写审计事实。
type MongoUserAccountClosedProjection struct {
	db                     *mongo.Database
	conversations          *mongo.Collection
	messages               *mongo.Collection
	members                *mongo.Collection
	userStates             *mongo.Collection
	messageReceipts        *mongo.Collection
	messageCommandReceipts *mongo.Collection
	conversationCommands   *mongo.Collection
	userStateCommands      *mongo.Collection
	conversationOutbox     *mongo.Collection
	membershipOutbox       *mongo.Collection
	userStateOutbox        *mongo.Collection
	messageOutbox          *mongo.Collection
	reliableTaskOutbox     *mongo.Collection
	reliableAsyncTasks     *mongo.Collection
	notificationOutbox     *mongo.Collection
	notificationLedger     *mongo.Collection
	inbox                  *mongo.Collection
	failures               *mongo.Collection
	redis                  rtredis.Client
}

var _ application.UserAccountClosedProjection = (*MongoUserAccountClosedProjection)(nil)

func NewMongoUserAccountClosedProjection(
	db *mongo.Database,
	redis rtredis.Client,
) *MongoUserAccountClosedProjection {
	if db == nil || redis == nil {
		panic("chat UserAccountClosed projection requires MongoDB and redis.general")
	}
	return &MongoUserAccountClosedProjection{
		db:                     db,
		conversations:          db.Collection("conversations"),
		messages:               db.Collection("messages"),
		members:                db.Collection("conversation_memberships"),
		userStates:             db.Collection("conversation_user_states"),
		messageReceipts:        db.Collection("message_receipts"),
		messageCommandReceipts: db.Collection("messages_command_receipts"),
		conversationCommands:   db.Collection("conversations_command_receipts"),
		userStateCommands:      db.Collection("conversation_user_states_command_receipts"),
		conversationOutbox:     db.Collection("conversations_outbox"),
		membershipOutbox:       db.Collection("conversation_memberships_outbox"),
		userStateOutbox:        db.Collection("conversation_user_states_outbox"),
		messageOutbox:          db.Collection("messages_outbox"),
		reliableTaskOutbox:     db.Collection("reliable_task_outbox"),
		reliableAsyncTasks:     db.Collection("reliable_async_task"),
		notificationOutbox:     db.Collection("notification_outbox"),
		notificationLedger:     db.Collection("notification_delivery_ledger"),
		inbox:                  db.Collection(userAccountClosedInboxCollection),
		failures:               db.Collection(userAccountClosedFailureCollection),
		redis:                  redis,
	}
}

func (p *MongoUserAccountClosedProjection) EnsureIndexes(
	ctx context.Context,
) error {
	if p == nil || p.db == nil || p.redis == nil {
		return fmt.Errorf("chat UserAccountClosed projection is not configured")
	}
	if _, err := p.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "completedAt", Value: -1},
		},
		Options: options.Index().
			SetName("idx_chat_user_account_closed_completed"),
	}); err != nil {
		return fmt.Errorf("ensure chat UserAccountClosed inbox index: %w", err)
	}
	if _, err := p.failures.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{{Key: "eventDigest", Value: 1}},
			Options: options.Index().
				SetName("idx_chat_user_account_closed_failure_event"),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().
				SetName("ttl_chat_user_account_closed_failures").
				SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("ensure chat UserAccountClosed failure indexes: %w", err)
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedApplyResult, error) {
	if p == nil || p.db == nil || p.redis == nil {
		return application.UserAccountClosedApplyResult{},
			fmt.Errorf("chat UserAccountClosed projection is not configured")
	}
	if err := event.Validate(); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	}
	if inbox, found, err := p.loadInbox(ctx, event); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	} else if found {
		if err := p.completeExternalCleanup(ctx, event, inbox); err != nil {
			return application.UserAccountClosedApplyResult{}, err
		}
		return application.UserAccountClosedApplyResult{Replayed: true}, nil
	}

	var applied userAccountClosedInboxDocument
	replayed := false
	session, err := p.db.Client().StartSession()
	if err != nil {
		return application.UserAccountClosedApplyResult{},
			fmt.Errorf("start chat UserAccountClosed transaction: %w", err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(
		ctx,
		func(txCtx context.Context) (any, error) {
			if existing, found, findErr := p.loadInbox(txCtx, event); findErr != nil {
				return nil, findErr
			} else if found {
				applied = existing
				replayed = true
				return nil, nil
			}
			affected, projectErr := p.projectClosedAccount(txCtx, event)
			if projectErr != nil {
				return nil, projectErr
			}
			applied = userAccountClosedInboxDocument{
				ID:                      event.EventID,
				EventDigest:             event.Digest(),
				AccountVersion:          event.AccountVersion,
				AffectedConversationIDs: affected,
				AppliedAt:               time.Now().UTC(),
			}
			if _, insertErr := p.inbox.InsertOne(txCtx, applied); insertErr != nil {
				return nil, insertErr
			}
			return nil, nil
		},
	)
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			if existing, found, findErr := p.loadInbox(ctx, event); findErr == nil && found {
				applied = existing
				replayed = true
				err = nil
			} else if findErr != nil {
				err = findErr
			}
		}
		if err != nil {
			return application.UserAccountClosedApplyResult{},
				fmt.Errorf("project chat UserAccountClosed: %w", err)
		}
	}
	if err := p.completeExternalCleanup(ctx, event, applied); err != nil {
		return application.UserAccountClosedApplyResult{}, err
	}
	return application.UserAccountClosedApplyResult{Replayed: replayed}, nil
}

func (p *MongoUserAccountClosedProjection) projectClosedAccount(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) ([]string, error) {
	subjects := event.SubjectIDs()
	affected := map[string]struct{}{}
	for _, query := range []struct {
		collection *mongo.Collection
		filter     any
		field      string
	}{
		{
			collection: p.members,
			filter: bson.M{"$or": bson.A{
				bson.M{"userId": bson.M{"$in": subjects}},
				bson.M{"invitedBy": bson.M{"$in": subjects}},
			}},
			field: "conversationId",
		},
		{
			collection: p.userStates,
			filter:     bson.M{"userId": bson.M{"$in": subjects}},
			field:      "conversationId",
		},
		{
			collection: p.messages,
			filter:     bson.M{"senderId": bson.M{"$in": subjects}},
			field:      "conversationId",
		},
		{
			collection: p.conversations,
			filter: bson.M{"$or": bson.A{
				bson.M{"creatorId": bson.M{"$in": subjects}},
				bson.M{"announcementUpdatedBy": bson.M{"$in": subjects}},
			}},
			field: "_id",
		},
	} {
		if err := collectStringField(
			ctx,
			query.collection,
			query.filter,
			query.field,
			affected,
		); err != nil {
			return nil, err
		}
	}

	stateIDs := map[string]struct{}{}
	if err := collectStringField(
		ctx,
		p.userStates,
		bson.M{"userId": bson.M{"$in": subjects}},
		"_id",
		stateIDs,
	); err != nil {
		return nil, err
	}
	if _, err := p.messageCommandReceipts.DeleteMany(
		ctx,
		bson.M{"result.senderId": bson.M{"$in": subjects}},
	); err != nil {
		return nil, fmt.Errorf(
			"delete closed chat message command receipts: %w",
			err,
		)
	}
	if _, err := p.messageCommandReceipts.UpdateMany(
		ctx,
		bson.M{"result.mentions": bson.M{"$in": subjects}},
		bson.M{"$pull": bson.M{
			"result.mentions": bson.M{"$in": subjects},
		}},
	); err != nil {
		return nil, fmt.Errorf(
			"remove closed chat message receipt mentions: %w",
			err,
		)
	}
	if len(stateIDs) > 0 {
		if _, err := p.userStateCommands.DeleteMany(
			ctx,
			bson.M{"aggregateId": bson.M{"$in": sortedSetValues(stateIDs)}},
		); err != nil {
			return nil, fmt.Errorf(
				"delete closed chat user-state command receipts: %w",
				err,
			)
		}
	}
	if _, err := p.userStateOutbox.DeleteMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"actorId": bson.M{"$in": subjects}},
			bson.M{"payload.userId": bson.M{"$in": subjects}},
		}},
	); err != nil {
		return nil, fmt.Errorf("delete closed chat user-state outbox: %w", err)
	}
	anonymousIDs, err := newClosedAccountAnonymousIDs(subjects)
	if err != nil {
		return nil, err
	}
	if err := p.anonymizeConversationCommandReceipts(
		ctx,
		sortedSetValues(affected),
		anonymousIDs,
	); err != nil {
		return nil, err
	}
	for _, subject := range subjects {
		anonymousID := anonymousIDs[subject]
		if _, err := p.messages.UpdateMany(
			ctx,
			bson.M{"senderId": subject},
			bson.M{
				"$set": bson.M{
					"senderId":                  anonymousID,
					"senderDisplayNameSnapshot": closedAccountDisplayName,
					"senderAvatarUrlSnapshot":   "",
					"personaContextVersion":     int64(0),
				},
				"$pull": bson.M{"mentions": subject},
			},
		); err != nil {
			return nil, fmt.Errorf("anonymize chat message sender: %w", err)
		}
		if _, err := p.messages.UpdateMany(
			ctx,
			bson.M{"mentions": subject},
			bson.M{"$pull": bson.M{"mentions": subject}},
		); err != nil {
			return nil, fmt.Errorf("remove closed chat mention: %w", err)
		}
		if err := p.anonymizeMessageOutbox(ctx, subject, anonymousID); err != nil {
			return nil, err
		}
		if err := p.anonymizeAggregateOutboxes(
			ctx,
			subject,
			anonymousID,
		); err != nil {
			return nil, err
		}
		if _, err := p.conversations.UpdateMany(
			ctx,
			bson.M{"creatorId": subject},
			bson.M{"$set": bson.M{"creatorId": anonymousID}},
		); err != nil {
			return nil, fmt.Errorf("anonymize chat conversation creator: %w", err)
		}
		if _, err := p.conversations.UpdateMany(
			ctx,
			bson.M{"announcementUpdatedBy": subject},
			bson.M{"$set": bson.M{"announcementUpdatedBy": anonymousID}},
		); err != nil {
			return nil, fmt.Errorf(
				"anonymize chat announcement updater: %w",
				err,
			)
		}
		if _, err := p.members.UpdateMany(
			ctx,
			bson.M{"invitedBy": subject},
			bson.M{"$set": bson.M{"invitedBy": anonymousID}},
		); err != nil {
			return nil, fmt.Errorf("anonymize chat membership inviter: %w", err)
		}
		if err := p.anonymizeReliableRuntimeState(
			ctx,
			subject,
			anonymousID,
		); err != nil {
			return nil, err
		}
	}

	if _, err := p.notificationOutbox.UpdateMany(
		ctx,
		bson.M{"recipientIds": bson.M{"$in": subjects}},
		bson.M{"$pull": bson.M{"recipientIds": bson.M{"$in": subjects}}},
	); err != nil {
		return nil, fmt.Errorf(
			"remove closed chat notification recipients: %w",
			err,
		)
	}
	if _, err := p.notificationOutbox.DeleteMany(
		ctx,
		bson.M{"recipientIds": bson.M{"$size": 0}},
	); err != nil {
		return nil, fmt.Errorf(
			"delete empty closed chat notifications: %w",
			err,
		)
	}
	if _, err := p.notificationLedger.DeleteMany(
		ctx,
		bson.M{"recipientId": bson.M{"$in": subjects}},
	); err != nil {
		return nil, fmt.Errorf(
			"delete closed chat notification delivery state: %w",
			err,
		)
	}
	if _, err := p.members.DeleteMany(
		ctx,
		bson.M{"userId": bson.M{"$in": subjects}},
	); err != nil {
		return nil, fmt.Errorf("delete closed chat memberships: %w", err)
	}
	if _, err := p.userStates.DeleteMany(
		ctx,
		bson.M{"userId": bson.M{"$in": subjects}},
	); err != nil {
		return nil, fmt.Errorf("delete closed chat user states: %w", err)
	}
	if _, err := p.messageReceipts.DeleteMany(
		ctx,
		bson.M{"userId": bson.M{"$in": subjects}},
	); err != nil {
		return nil, fmt.Errorf("delete closed chat receipts: %w", err)
	}

	affectedIDs := sortedSetValues(affected)
	now := time.Now().UTC()
	for _, conversationID := range affectedIDs {
		memberCount, err := p.members.CountDocuments(
			ctx,
			bson.M{"conversationId": conversationID},
		)
		if err != nil {
			return nil, fmt.Errorf("recount chat conversation members: %w", err)
		}
		if _, err := p.conversations.UpdateOne(
			ctx,
			bson.M{"_id": conversationID},
			bson.M{
				"$set": bson.M{
					"memberCount":           int(memberCount),
					"avatarUrl":             "",
					"groupAvatarAssetId":    "",
					"groupAvatarSourceHash": "",
					"updatedAt":             now,
				},
				"$inc": bson.M{"membersRosterRevision": int64(1)},
			},
		); err != nil {
			return nil, fmt.Errorf(
				"reconcile chat conversation roster: %w",
				err,
			)
		}
	}
	return affectedIDs, nil
}

func (p *MongoUserAccountClosedProjection) anonymizeConversationCommandReceipts(
	ctx context.Context,
	conversationIDs []string,
	anonymousIDs map[string]string,
) error {
	if len(conversationIDs) == 0 {
		return nil
	}
	cursor, err := p.conversationCommands.Find(
		ctx,
		bson.M{"aggregateId": bson.M{"$in": conversationIDs}},
		options.Find().SetProjection(bson.M{"_id": 1, "resultJson": 1}),
	)
	if err != nil {
		return fmt.Errorf("scan chat conversation command receipts: %w", err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document struct {
			ID         string `bson:"_id"`
			ResultJSON []byte `bson:"resultJson"`
		}
		if err := cursor.Decode(&document); err != nil {
			return fmt.Errorf("decode chat conversation command receipt: %w", err)
		}
		if len(document.ResultJSON) == 0 {
			continue
		}
		var result conversationmodel.Conversation
		if err := json.Unmarshal(document.ResultJSON, &result); err != nil {
			return fmt.Errorf("decode chat conversation command result: %w", err)
		}
		if anonymousID := anonymousIDs[strings.TrimSpace(result.CreatorId)]; anonymousID != "" {
			result.CreatorId = anonymousID
		}
		if anonymousID := anonymousIDs[strings.TrimSpace(result.AnnouncementUpdatedBy)]; anonymousID != "" {
			result.AnnouncementUpdatedBy = anonymousID
		}
		result.AvatarUrl = ""
		result.GroupAvatarAssetId = ""
		result.GroupAvatarSourceHash = ""
		sanitized, err := json.Marshal(result)
		if err != nil {
			return fmt.Errorf("encode anonymized chat command result: %w", err)
		}
		if _, err := p.conversationCommands.UpdateOne(
			ctx,
			bson.M{"_id": document.ID},
			bson.M{"$set": bson.M{"resultJson": sanitized}},
		); err != nil {
			return fmt.Errorf("anonymize chat conversation command result: %w", err)
		}
	}
	if err := cursor.Err(); err != nil {
		return fmt.Errorf("scan chat conversation command receipts: %w", err)
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) anonymizeMessageOutbox(
	ctx context.Context,
	subject string,
	anonymousID string,
) error {
	if _, err := p.messageOutbox.UpdateMany(
		ctx,
		bson.M{"actorId": subject},
		bson.M{"$set": bson.M{"actorId": anonymousID}},
	); err != nil {
		return fmt.Errorf("anonymize chat message outbox actor: %w", err)
	}
	if _, err := p.messageOutbox.UpdateMany(
		ctx,
		bson.M{"payload.senderId": subject},
		bson.M{"$set": bson.M{
			"payload.senderId":                  anonymousID,
			"payload.senderDisplayNameSnapshot": closedAccountDisplayName,
			"payload.senderAvatarUrlSnapshot":   "",
			"payload.personaContextVersion":     int64(0),
		}},
	); err != nil {
		return fmt.Errorf("anonymize chat message outbox payload: %w", err)
	}
	if _, err := p.messageOutbox.UpdateMany(
		ctx,
		bson.M{"payload.mentions": subject},
		bson.M{"$pull": bson.M{"payload.mentions": subject}},
	); err != nil {
		return fmt.Errorf("remove closed chat outbox mention: %w", err)
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) anonymizeAggregateOutboxes(
	ctx context.Context,
	subject string,
	anonymousID string,
) error {
	for _, collection := range []*mongo.Collection{
		p.conversationOutbox,
		p.membershipOutbox,
	} {
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{"actorId": subject},
			bson.M{"$set": bson.M{"actorId": anonymousID}},
		); err != nil {
			return fmt.Errorf(
				"anonymize %s actor: %w",
				collection.Name(),
				err,
			)
		}
	}
	if _, err := p.membershipOutbox.UpdateMany(
		ctx,
		bson.M{"payload.userId": subject},
		bson.M{"$set": bson.M{
			"payload.userId":        anonymousID,
			"payload.displayName":   closedAccountDisplayName,
			"payload.avatarUrl":     "",
			"payload.avatarAssetId": "",
			"payload.avatarVersion": int64(0),
		}},
	); err != nil {
		return fmt.Errorf("anonymize chat membership outbox subject: %w", err)
	}
	for _, field := range []string{
		"payload.invitedBy",
		"payload.removedBy",
		"payload.changedBy",
		"payload.dissolvedBy",
		"payload.creatorId",
	} {
		for _, collection := range []*mongo.Collection{
			p.conversationOutbox,
			p.membershipOutbox,
		} {
			if _, err := collection.UpdateMany(
				ctx,
				bson.M{field: subject},
				bson.M{"$set": bson.M{field: anonymousID}},
			); err != nil {
				return fmt.Errorf(
					"anonymize %s %s: %w",
					collection.Name(),
					field,
					err,
				)
			}
		}
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) anonymizeReliableRuntimeState(
	ctx context.Context,
	subject string,
	anonymousID string,
) error {
	for _, collection := range []*mongo.Collection{
		p.reliableTaskOutbox,
		p.reliableAsyncTasks,
		p.notificationOutbox,
	} {
		if _, err := collection.UpdateMany(
			ctx,
			bson.M{"payload.actorID": subject},
			bson.M{"$set": bson.M{"payload.actorID": anonymousID}},
		); err != nil {
			return fmt.Errorf(
				"anonymize %s actor state: %w",
				collection.Name(),
				err,
			)
		}
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) loadInbox(
	ctx context.Context,
	event application.UserAccountClosedEvent,
) (userAccountClosedInboxDocument, bool, error) {
	var document userAccountClosedInboxDocument
	err := p.inbox.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(event.EventID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return userAccountClosedInboxDocument{}, false, nil
	}
	if err != nil {
		return userAccountClosedInboxDocument{}, false,
			fmt.Errorf("read chat UserAccountClosed inbox: %w", err)
	}
	if document.EventDigest != event.Digest() ||
		document.AccountVersion != event.AccountVersion {
		return userAccountClosedInboxDocument{}, true, errors.New(
			"chat UserAccountClosed eventId was reused with different data",
		)
	}
	return document, true, nil
}

func (p *MongoUserAccountClosedProjection) completeExternalCleanup(
	ctx context.Context,
	event application.UserAccountClosedEvent,
	inbox userAccountClosedInboxDocument,
) error {
	if err := p.invalidateConversationCaches(
		ctx,
		inbox.AffectedConversationIDs,
	); err != nil {
		return err
	}
	if err := p.purgeSubjectRuntimeState(ctx, event.SubjectIDs()); err != nil {
		return err
	}
	now := time.Now().UTC()
	result, err := p.inbox.UpdateOne(
		ctx,
		bson.M{
			"_id":         event.EventID,
			"eventDigest": event.Digest(),
		},
		bson.M{
			"$set":   bson.M{"completedAt": now},
			"$unset": bson.M{"affectedConversationIds": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("complete chat UserAccountClosed inbox: %w", err)
	}
	if result.MatchedCount != 1 {
		return errors.New("chat UserAccountClosed inbox state is missing")
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) invalidateConversationCaches(
	ctx context.Context,
	conversationIDs []string,
) error {
	for _, conversationID := range conversationIDs {
		if err := p.redis.Del(
			ctx,
			"cache:conversation:"+conversationID,
		); err != nil {
			return fmt.Errorf(
				"invalidate closed-account chat cache: %w",
				err,
			)
		}
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) purgeSubjectRuntimeState(
	ctx context.Context,
	subjects []string,
) error {
	for _, subject := range subjects {
		latestKey := syncSequenceKeyPrefix + subject + ":latest"
		rawLatest, err := p.redis.Get(ctx, latestKey)
		if errors.Is(err, rtredis.ErrKeyNotFound) {
			continue
		}
		if err != nil {
			return fmt.Errorf("read closed chat sync sequence: %w", err)
		}
		latest, err := strconv.ParseInt(strings.TrimSpace(rawLatest), 10, 64)
		if err != nil || latest < 0 {
			return errors.New("closed chat sync sequence is invalid")
		}
		keys := make([]string, 0, int(syncPatchDeleteBatchSize))
		for sequence := int64(1); sequence <= latest; sequence++ {
			keys = append(
				keys,
				syncSequenceKeyPrefix+subject+":patch:"+
					strconv.FormatInt(sequence, 10),
			)
			if int64(len(keys)) == syncPatchDeleteBatchSize {
				if err := p.redis.Del(ctx, keys...); err != nil {
					return fmt.Errorf("delete closed chat sync patches: %w", err)
				}
				keys = keys[:0]
			}
		}
		if len(keys) > 0 {
			if err := p.redis.Del(ctx, keys...); err != nil {
				return fmt.Errorf("delete closed chat sync patches: %w", err)
			}
		}
		if err := p.redis.Del(ctx, latestKey); err != nil {
			return fmt.Errorf("delete closed chat sync sequence: %w", err)
		}
	}
	return nil
}

func (p *MongoUserAccountClosedProjection) RecordUserAccountClosedFailure(
	ctx context.Context,
	messageID string,
	eventID string,
	cause error,
) (int64, error) {
	if cause == nil {
		return 0, fmt.Errorf("chat UserAccountClosed failure cause is required")
	}
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	now := time.Now().UTC()
	err := p.failures.FindOneAndUpdate(
		ctx,
		bson.M{"_id": userAccountClosedFailureID(messageID)},
		bson.M{
			"$set": bson.M{
				"eventDigest": irreversiblePersistenceDigest(eventID),
				"errorDigest": irreversiblePersistenceDigest(cause.Error()),
				"updatedAt":   now,
				"expiresAt":   now.Add(userAccountClosedFailureRetention),
			},
			"$inc":         bson.M{"attempts": int64(1)},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.FindOneAndUpdate().
			SetUpsert(true).
			SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	return document.Attempts, nil
}

func (p *MongoUserAccountClosedProjection) ClearUserAccountClosedFailure(
	ctx context.Context,
	messageID string,
) error {
	_, err := p.failures.DeleteOne(
		ctx,
		bson.M{"_id": userAccountClosedFailureID(messageID)},
	)
	return err
}

func newClosedAccountAnonymousIDs(
	subjects []string,
) (map[string]string, error) {
	result := make(map[string]string, len(subjects))
	for _, subject := range subjects {
		raw := make([]byte, 16)
		if _, err := rand.Read(raw); err != nil {
			return nil, fmt.Errorf("generate closed chat anonymous identity: %w", err)
		}
		result[subject] = closedAccountAnonymousIDPrefix + hex.EncodeToString(raw)
	}
	return result, nil
}

func userAccountClosedFailureID(messageID string) string {
	return irreversiblePersistenceDigest(
		userAccountClosedFailureNamespace + "\x00" +
			strings.TrimSpace(messageID),
	)
}

const userAccountClosedFailureNamespace = "chat-user-account-closed"

func irreversiblePersistenceDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func collectStringField(
	ctx context.Context,
	collection *mongo.Collection,
	filter any,
	field string,
	target map[string]struct{},
) error {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{field: 1}),
	)
	if err != nil {
		return fmt.Errorf("scan %s for account cleanup: %w", collection.Name(), err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var document bson.M
		if err := cursor.Decode(&document); err != nil {
			return err
		}
		value, _ := document[field].(string)
		value = strings.TrimSpace(value)
		if value != "" {
			target[value] = struct{}{}
		}
	}
	return cursor.Err()
}

func sortedSetValues(values map[string]struct{}) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	for index := 1; index < len(result); index++ {
		for cursor := index; cursor > 0 && result[cursor] < result[cursor-1]; cursor-- {
			result[cursor], result[cursor-1] = result[cursor-1], result[cursor]
		}
	}
	return result
}

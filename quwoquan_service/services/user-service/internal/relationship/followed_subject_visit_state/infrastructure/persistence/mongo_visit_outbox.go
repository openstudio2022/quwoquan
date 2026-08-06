package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	visitmodel "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/model"
	visitports "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/domain/ports"
)

type visitOutboxDocument struct {
	ID            string     `bson:"_id"`
	AggregateID   string     `bson:"aggregateId"`
	EventName     string     `bson:"eventName"`
	PersonaID     string     `bson:"personaId"`
	SubjectType   string     `bson:"subjectType"`
	SubjectID     string     `bson:"subjectId"`
	LastVisitedAt time.Time  `bson:"lastVisitedAt"`
	UpdatedAt     time.Time  `bson:"updatedAt"`
	OccurredAt    time.Time  `bson:"occurredAt"`
	LeaseOwner    string     `bson:"leaseOwner,omitempty"`
	LeasedUntil   *time.Time `bson:"leasedUntil,omitempty"`
	PublishedAt   *time.Time `bson:"publishedAt,omitempty"`
}

// ClaimPendingOutbox 以租约独占一批未投递事件。租约到期而未确认的事件会被
// 重新认领，投递语义因此是至少一次。
func (s *MongoFollowedSubjectVisitStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]visitmodel.OutboxEvent, error) {
	if s == nil || s.outbox == nil {
		return nil, errors.New("followed subject visit outbox is unavailable")
	}
	if ownerID = strings.TrimSpace(ownerID); ownerID == "" {
		return nil, errors.New("followed subject visit outbox owner is required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	now := time.Now().UTC()
	leasedUntil := now.Add(lease)
	claimed := make([]visitmodel.OutboxEvent, 0, limit)
	for len(claimed) < limit {
		var document visitOutboxDocument
		err := s.outbox.FindOneAndUpdate(
			ctx,
			bson.M{
				"publishedAt": nil,
				"$or": bson.A{
					bson.M{"leasedUntil": nil},
					bson.M{"leasedUntil": bson.M{"$lte": now}},
				},
			},
			bson.M{"$set": bson.M{"leaseOwner": ownerID, "leasedUntil": leasedUntil}},
			options.FindOneAndUpdate().
				SetSort(bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}}).
				SetReturnDocument(options.After),
		).Decode(&document)
		if errors.Is(err, mongo.ErrNoDocuments) {
			break
		}
		if err != nil {
			return claimed, fmt.Errorf("claim followed subject visit outbox: %w", err)
		}
		claimed = append(claimed, visitmodel.OutboxEvent{
			EventID:     document.ID,
			AggregateID: document.AggregateID,
			EventName:   document.EventName,
			OccurredAt:  document.OccurredAt.UTC(),
			Payload: visitmodel.EventPayload{
				PersonaID:     document.PersonaID,
				SubjectType:   document.SubjectType,
				SubjectID:     document.SubjectID,
				LastVisitedAt: document.LastVisitedAt.UTC(),
				UpdatedAt:     document.UpdatedAt.UTC(),
			},
		})
	}
	return claimed, nil
}

// MarkOutboxPublished 只在租约仍归 ownerID 时确认；租约已被抢走时返回
// ErrOutboxClaimLost，由新持有者重新投递。
func (s *MongoFollowedSubjectVisitStore) MarkOutboxPublished(
	ctx context.Context,
	eventID, ownerID string,
) error {
	if s == nil || s.outbox == nil {
		return errors.New("followed subject visit outbox is unavailable")
	}
	result, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID, "leaseOwner": ownerID, "publishedAt": nil},
		bson.M{
			"$set":   bson.M{"publishedAt": time.Now().UTC()},
			"$unset": bson.M{"leaseOwner": "", "leasedUntil": ""},
		},
	)
	if err != nil {
		return fmt.Errorf("mark followed subject visit outbox published: %w", err)
	}
	if result.MatchedCount != 1 {
		return visitports.ErrOutboxClaimLost
	}
	return nil
}

func (s *MongoFollowedSubjectVisitStore) ReleaseOutboxClaim(
	ctx context.Context,
	eventID, ownerID string,
) error {
	if s == nil || s.outbox == nil {
		return errors.New("followed subject visit outbox is unavailable")
	}
	_, err := s.outbox.UpdateOne(
		ctx,
		bson.M{"_id": eventID, "leaseOwner": ownerID, "publishedAt": nil},
		bson.M{"$unset": bson.M{"leaseOwner": "", "leasedUntil": ""}},
	)
	if err != nil {
		return fmt.Errorf("release followed subject visit outbox claim: %w", err)
	}
	return nil
}

var (
	_ visitports.VisitStateStore  = (*MongoFollowedSubjectVisitStore)(nil)
	_ visitports.VisitStateOutbox = (*MongoFollowedSubjectVisitStore)(nil)
)

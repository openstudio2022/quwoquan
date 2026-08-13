package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

const (
	gatheringQueryCollection    = "gatherings"
	gatheringHostPageIndex      = "idx_gathering_host_page"
	gatheringSourcePageIndex    = "idx_gathering_source_page"
	gatheringParticipationIndex = "idx_gathering_participation_identity"
)

type MongoGatheringQueryReader struct {
	gatherings *mongo.Collection
}

func NewMongoGatheringQueryReader(database *mongo.Database) *MongoGatheringQueryReader {
	if database == nil {
		panic("Gathering MongoGatheringQueryReader requires database")
	}
	return &MongoGatheringQueryReader{gatherings: database.Collection(gatheringQueryCollection)}
}

func (reader *MongoGatheringQueryReader) ReadGathering(
	ctx context.Context,
	gatheringID string,
) (gatheringapp.GatheringReadModel, bool, error) {
	var value gatheringapp.GatheringReadModel
	err := reader.gatherings.FindOne(ctx, bson.M{"_id": strings.TrimSpace(gatheringID)}).Decode(&value)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return gatheringapp.GatheringReadModel{}, false, nil
	}
	if err != nil {
		return gatheringapp.GatheringReadModel{}, false, err
	}
	return value, true, nil
}

func (reader *MongoGatheringQueryReader) ListByHost(
	ctx context.Context,
	host gatheringapp.HostRef,
	after gatheringapp.PublicListPosition,
	limit int,
) ([]gatheringapp.GatheringReadModel, error) {
	filter := bson.M{
		"hostBinding.hostSubjectKind": host.SubjectKind,
		"hostBinding.hostSubjectId":   host.SubjectID,
		"lifecycleStatus":             bson.M{"$in": bson.A{"published", "cancelled", "completed"}},
		"policySet.audiencePolicy":    "public",
	}
	addPublicPageKeyset(filter, after)
	return reader.findPublicPage(ctx, filter, gatheringHostPageIndex, limit)
}

// ListMineByHost 返回 persona host 名下全部行动（含 draft 与非公开
// audiencePolicy）；授权边界在 application facade（viewer 即 host 本人）。
func (reader *MongoGatheringQueryReader) ListMineByHost(
	ctx context.Context,
	personaID string,
	after gatheringapp.PublicListPosition,
	limit int,
) ([]gatheringapp.GatheringReadModel, error) {
	filter := bson.M{
		"hostBinding.hostSubjectKind": "persona",
		"hostBinding.hostSubjectId":   personaID,
	}
	addPublicPageKeyset(filter, after)
	return reader.findPublicPage(ctx, filter, gatheringHostPageIndex, limit)
}

func (reader *MongoGatheringQueryReader) ListBySource(
	ctx context.Context,
	source gatheringapp.CanonicalObjectRef,
	after gatheringapp.PublicListPosition,
	limit int,
) ([]gatheringapp.GatheringReadModel, error) {
	filter := bson.M{
		"purpose.sourceObjectRefs": bson.M{"$elemMatch": bson.M{
			"objectRef.objectTypeRef": source.ObjectTypeRef,
			"objectRef.objectId":      source.ObjectID,
		}},
		"lifecycleStatus":          bson.M{"$in": bson.A{"published", "cancelled", "completed"}},
		"policySet.audiencePolicy": "public",
	}
	addPublicPageKeyset(filter, after)
	return reader.findPublicPage(ctx, filter, gatheringSourcePageIndex, limit)
}

func (reader *MongoGatheringQueryReader) ListApplications(
	ctx context.Context,
	query gatheringapp.ApplicationReadQuery,
) ([]gatheringapp.ParticipationRecord, error) {
	participationFilter := bson.M{
		"participations.state":            "application_pending",
		"participations.reviewExpectedBy": bson.M{"$ne": nil},
	}
	if query.After.ReviewExpectedBy != nil {
		participationFilter["$or"] = bson.A{
			bson.M{"participations.reviewExpectedBy": bson.M{"$gt": *query.After.ReviewExpectedBy}},
			bson.M{
				"participations.reviewExpectedBy": *query.After.ReviewExpectedBy,
				"participations.personaId":        bson.M{"$gt": query.After.PersonaID},
			},
			bson.M{
				"participations.reviewExpectedBy": *query.After.ReviewExpectedBy,
				"participations.personaId":        query.After.PersonaID,
				"participations.attemptNo":        bson.M{"$gt": query.After.AttemptNo},
			},
		}
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"_id":                            strings.TrimSpace(query.GatheringID),
			"organizerAssignments.personaId": strings.TrimSpace(query.OrganizerPersonaID),
		}}},
		{{Key: "$unwind", Value: "$participations"}},
		{{Key: "$match", Value: participationFilter}},
		{{Key: "$sort", Value: bson.D{
			{Key: "participations.reviewExpectedBy", Value: 1},
			{Key: "participations.personaId", Value: 1},
			{Key: "participations.attemptNo", Value: 1},
		}}},
		{{Key: "$replaceWith", Value: bson.M{"$mergeObjects": bson.A{
			"$participations",
			bson.M{"gatheringId": "$_id"},
		}}}},
		{{Key: "$limit", Value: int64(query.Limit)}},
	}
	// GatheringID is mandatory and unique, so the canonical _id index narrows
	// the pipeline to one aggregate before organizer authorization and
	// participation unwind. A compound organizerAssignments+participations
	// index is invalid in MongoDB because both paths are arrays.
	cursor, err := reader.gatherings.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []gatheringapp.ParticipationRecord
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	if values == nil {
		values = []gatheringapp.ParticipationRecord{}
	}
	return values, nil
}

func (reader *MongoGatheringQueryReader) ListRoster(
	ctx context.Context,
	query gatheringapp.RosterReadQuery,
) ([]gatheringapp.ParticipationRecord, error) {
	participationFilter := bson.M{}
	if query.ActiveOnly {
		participationFilter["participations.state"] = "active"
	}
	if strings.TrimSpace(query.After.PersonaID) != "" {
		participationFilter["participations.personaId"] = bson.M{"$gt": query.After.PersonaID}
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{"_id": strings.TrimSpace(query.GatheringID)}}},
		{{Key: "$unwind", Value: "$participations"}},
	}
	if len(participationFilter) > 0 {
		pipeline = append(pipeline, bson.D{{Key: "$match", Value: participationFilter}})
	}
	pipeline = append(pipeline,
		bson.D{{Key: "$sort", Value: bson.D{{Key: "participations.personaId", Value: 1}}}},
		bson.D{{Key: "$replaceWith", Value: bson.M{"$mergeObjects": bson.A{
			"$participations",
			bson.M{"gatheringId": "$_id"},
		}}}},
		bson.D{{Key: "$limit", Value: int64(query.Limit)}},
	)
	cursor, err := reader.gatherings.Aggregate(
		ctx,
		pipeline,
		options.Aggregate().SetHint(gatheringParticipationIndex),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []gatheringapp.ParticipationRecord
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	if values == nil {
		values = []gatheringapp.ParticipationRecord{}
	}
	return values, nil
}

func (reader *MongoGatheringQueryReader) findPublicPage(
	ctx context.Context,
	filter bson.M,
	hint string,
	limit int,
) ([]gatheringapp.GatheringReadModel, error) {
	cursor, err := reader.gatherings.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "schedule.startAt", Value: 1}, {Key: "_id", Value: 1}}).
			SetLimit(int64(limit)).
			SetHint(hint),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var values []gatheringapp.GatheringReadModel
	if err := cursor.All(ctx, &values); err != nil {
		return nil, err
	}
	if values == nil {
		values = []gatheringapp.GatheringReadModel{}
	}
	return values, nil
}

func addPublicPageKeyset(filter bson.M, after gatheringapp.PublicListPosition) {
	if after.StartAt == nil {
		return
	}
	filter["$or"] = bson.A{
		bson.M{"schedule.startAt": bson.M{"$gt": *after.StartAt}},
		bson.M{"schedule.startAt": *after.StartAt, "_id": bson.M{"$gt": after.GatheringID}},
	}
}

var _ gatheringapp.GatheringQueryReader = (*MongoGatheringQueryReader)(nil)

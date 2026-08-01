package accountclosure

import (
	"context"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const mongoIDBatchSize = 500

type commentClosureRow struct {
	ID     string `bson:"_id"`
	PostID string `bson:"postId"`
}

type reactionClosureRow struct {
	ID         string `bson:"_id"`
	TargetKind string `bson:"targetKind"`
	TargetID   string `bson:"targetId"`
}

type shareClosureRow struct {
	ID     string `bson:"_id"`
	PostID string `bson:"postId"`
}

type activityClosureRow struct {
	ID         string `bson:"_id"`
	ActivityID string `bson:"activityId"`
}

func collectStringField(
	ctx context.Context,
	collection *mongo.Collection,
	filter any,
	field string,
) ([]string, error) {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{field: 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	seen := map[string]struct{}{}
	values := make([]string, 0)
	for cursor.Next(ctx) {
		var document bson.M
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		value, _ := document[field].(string)
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		values = append(values, value)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return values, nil
}

func collectCommentClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
	postIDs []string,
) ([]commentClosureRow, error) {
	orFilters := bson.A{
		bson.M{"authorId": bson.M{"$in": subjectIDs}},
	}
	if len(postIDs) > 0 {
		orFilters = append(
			orFilters,
			bson.M{"postId": bson.M{"$in": postIDs}},
		)
	}
	return findCommentRows(
		ctx,
		collection,
		bson.M{"$or": orFilters},
	)
}

func collectCommentReferenceRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
	deletedCommentIDs []string,
) ([]commentClosureRow, error) {
	return findCommentRows(
		ctx,
		collection,
		bson.M{"$or": bson.A{
			bson.M{"replyToUserId": bson.M{"$in": subjectIDs}},
			bson.M{"mentions.subjectId": bson.M{"$in": subjectIDs}},
			bson.M{"parentCommentId": bson.M{"$in": deletedCommentIDs}},
			bson.M{"replyToCommentId": bson.M{"$in": deletedCommentIDs}},
		}},
	)
}

func findCommentRows(
	ctx context.Context,
	collection *mongo.Collection,
	filter any,
) ([]commentClosureRow, error) {
	cursor, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(
			bson.M{"_id": 1, "postId": 1},
		),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []commentClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func collectReactionClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
	targetIDs []string,
) ([]reactionClosureRow, error) {
	orFilters := bson.A{
		bson.M{"actorId": bson.M{"$in": subjectIDs}},
	}
	if len(targetIDs) > 0 {
		orFilters = append(
			orFilters,
			bson.M{"targetId": bson.M{"$in": targetIDs}},
		)
	}
	cursor, err := collection.Find(
		ctx,
		bson.M{"$or": orFilters},
		options.Find().SetProjection(
			bson.M{
				"_id":        1,
				"targetKind": 1,
				"targetId":   1,
			},
		),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []reactionClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func collectShareClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
	postIDs []string,
) ([]shareClosureRow, error) {
	orFilters := bson.A{
		bson.M{"actorId": bson.M{"$in": subjectIDs}},
	}
	if len(postIDs) > 0 {
		orFilters = append(
			orFilters,
			bson.M{"postId": bson.M{"$in": postIDs}},
		)
	}
	cursor, err := collection.Find(
		ctx,
		bson.M{"$or": orFilters},
		options.Find().SetProjection(bson.M{"_id": 1, "postId": 1}),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []shareClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func collectActivityClosureRows(
	ctx context.Context,
	collection *mongo.Collection,
	subjectIDs []string,
	postIDs []string,
	commentIDs []string,
) ([]activityClosureRow, error) {
	orFilters := bson.A{
		bson.M{"ownerPersonaId": bson.M{"$in": subjectIDs}},
		bson.M{"actorPersonaId": bson.M{"$in": subjectIDs}},
		bson.M{"counterpartPersonaId": bson.M{"$in": subjectIDs}},
		bson.M{"targetPersonaId": bson.M{"$in": subjectIDs}},
		bson.M{"displayPersonaId": bson.M{"$in": subjectIDs}},
	}
	if len(postIDs) > 0 {
		orFilters = append(
			orFilters,
			bson.M{"targetContentId": bson.M{"$in": postIDs}},
		)
	}
	if len(commentIDs) > 0 {
		orFilters = append(
			orFilters,
			bson.M{"commentId": bson.M{"$in": commentIDs}},
		)
	}
	cursor, err := collection.Find(
		ctx,
		bson.M{"$or": orFilters},
		options.Find().SetProjection(
			bson.M{"_id": 1, "activityId": 1},
		),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []activityClosureRow
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	return rows, nil
}

func deleteByStringIDs(
	ctx context.Context,
	collection *mongo.Collection,
	field string,
	values []string,
) error {
	for start := 0; start < len(values); start += mongoIDBatchSize {
		end := start + mongoIDBatchSize
		if end > len(values) {
			end = len(values)
		}
		if _, err := collection.DeleteMany(
			ctx,
			bson.M{field: bson.M{"$in": values[start:end]}},
		); err != nil {
			return err
		}
	}
	return nil
}

func uniqueStrings(values ...[]string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0)
	for _, group := range values {
		for _, value := range group {
			value = strings.TrimSpace(value)
			if value == "" {
				continue
			}
			if _, exists := seen[value]; exists {
				continue
			}
			seen[value] = struct{}{}
			out = append(out, value)
		}
	}
	return out
}

func rowIDs[T interface {
	commentClosureRow | reactionClosureRow | shareClosureRow | activityClosureRow
}](rows []T) []string {
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		switch value := any(row).(type) {
		case commentClosureRow:
			ids = append(ids, value.ID)
		case reactionClosureRow:
			ids = append(ids, value.ID)
		case shareClosureRow:
			ids = append(ids, value.ID)
		case activityClosureRow:
			ids = append(ids, value.ID)
		default:
			panic(fmt.Sprintf("unsupported closure row %T", row))
		}
	}
	return ids
}

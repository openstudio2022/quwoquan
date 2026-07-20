package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"regexp"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func (projection *MongoUserAccountClosedProjection) anonymizeAccountClosureOutboxes(
	ctx context.Context,
	subjects []string,
) error {
	replacements := make(map[string]string, len(subjects))
	orFilters := make(bson.A, 0, len(subjects))
	for _, subject := range subjects {
		replacements[subject] = closedCircleAnonymousID(subject)
		orFilters = append(orFilters, bson.M{
			"payloadJson": bson.M{"$regex": regexp.QuoteMeta(subject)},
		})
	}
	if len(orFilters) == 0 {
		return nil
	}
	for _, collectionName := range []string{
		"circle_outbox",
		"circle_membership_outbox",
		"circle_group_outbox",
		"circle_group_membership_outbox",
		"circle_files_outbox",
		"circle_post_placement_outbox",
		"circle_behavior_fact_outbox",
	} {
		if err := rewriteAccountClosurePayloads(
			ctx,
			projection.db.Collection(collectionName),
			bson.M{"$or": orFilters},
			replacements,
		); err != nil {
			return fmt.Errorf(
				"anonymize account-closure payloads in %s: %w",
				collectionName,
				err,
			)
		}
	}
	return nil
}

func rewriteAccountClosurePayloads(
	ctx context.Context,
	collection *mongo.Collection,
	filter bson.M,
	replacements map[string]string,
) error {
	rows, err := collection.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{"payloadJson": 1}),
	)
	if err != nil {
		return err
	}
	defer rows.Close(ctx)
	type payloadDocument struct {
		ID          string `bson:"_id"`
		PayloadJSON string `bson:"payloadJson"`
	}
	for rows.Next(ctx) {
		var document payloadDocument
		if err := rows.Decode(&document); err != nil {
			return err
		}
		rewritten, changed, err := rewriteAccountClosureJSON(
			document.PayloadJSON,
			replacements,
		)
		if err != nil {
			return err
		}
		if !changed {
			continue
		}
		result, err := collection.UpdateOne(
			ctx,
			bson.M{"_id": document.ID, "payloadJson": document.PayloadJSON},
			bson.M{"$set": bson.M{"payloadJson": rewritten}},
		)
		if err != nil {
			return err
		}
		if result.MatchedCount != 1 {
			return fmt.Errorf(
				"outbox payload changed during account closure",
			)
		}
	}
	return rows.Err()
}

func rewriteAccountClosureJSON(
	raw string,
	replacements map[string]string,
) (string, bool, error) {
	decoder := json.NewDecoder(bytes.NewBufferString(raw))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return "", false, fmt.Errorf(
			"decode account-closure outbox payload: %w",
			err,
		)
	}
	rewritten, changed := replaceAccountClosureJSONValue(
		value,
		replacements,
	)
	if !changed {
		return raw, false, nil
	}
	encoded, err := json.Marshal(rewritten)
	if err != nil {
		return "", false, err
	}
	return string(encoded), true, nil
}

func replaceAccountClosureJSONValue(
	value any,
	replacements map[string]string,
) (any, bool) {
	switch typed := value.(type) {
	case string:
		replacement, exists := replacements[typed]
		if !exists {
			return value, false
		}
		return replacement, true
	case []any:
		changed := false
		for index, item := range typed {
			next, itemChanged := replaceAccountClosureJSONValue(
				item,
				replacements,
			)
			if itemChanged {
				typed[index] = next
				changed = true
			}
		}
		return typed, changed
	case map[string]any:
		changed := false
		for key, item := range typed {
			next, itemChanged := replaceAccountClosureJSONValue(
				item,
				replacements,
			)
			if itemChanged {
				typed[key] = next
				changed = true
			}
		}
		return typed, changed
	default:
		return value, false
	}
}

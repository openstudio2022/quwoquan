package persistence

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
)

// This file is the sole owner of the retired Mongo projection key. Startup
// performs one data-preserving move and removes the old field before canonical
// indexes are created. Runtime readers and writers never dual-read or maintain
// aliases.
const retiredFollowingSubjectViewerKey = "viewerSubAccountId"

type followingSubjectIndexSpec struct {
	Name   string `bson:"name"`
	Key    bson.D `bson:"key"`
	Unique bool   `bson:"unique"`
}

func (s *MongoFollowingSubjectStore) migratePersonaIdentity(
	ctx context.Context,
) error {
	if s == nil || s.collection == nil {
		return nil
	}
	canonicalKey := "viewerPersonaId"

	conflict := s.collection.FindOne(ctx, bson.M{
		retiredFollowingSubjectViewerKey: bson.M{"$exists": true},
		canonicalKey:                     bson.M{"$exists": true},
		"$expr": bson.M{"$ne": bson.A{
			"$" + retiredFollowingSubjectViewerKey,
			"$" + canonicalKey,
		}},
	})
	if conflict.Err() == nil {
		return errors.New(
			"following_subjects contains conflicting retired and canonical viewer identities",
		)
	}
	if !errors.Is(conflict.Err(), mongo.ErrNoDocuments) {
		return fmt.Errorf("inspect following_subjects identity conflicts: %w", conflict.Err())
	}

	missing := s.collection.FindOne(ctx, bson.M{
		retiredFollowingSubjectViewerKey: bson.M{"$exists": false},
		canonicalKey:                     bson.M{"$exists": false},
	})
	if missing.Err() == nil {
		return errors.New("following_subjects contains a row without viewer Persona identity")
	}
	if !errors.Is(missing.Err(), mongo.ErrNoDocuments) {
		return fmt.Errorf("inspect following_subjects missing identities: %w", missing.Err())
	}

	duplicateCursor, err := s.collection.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$project", Value: bson.D{
			{Key: "viewer", Value: bson.D{{Key: "$ifNull", Value: bson.A{
				"$" + canonicalKey,
				"$" + retiredFollowingSubjectViewerKey,
			}}}},
			{Key: "subjectType", Value: 1},
			{Key: "subjectId", Value: 1},
		}}},
		bson.D{{Key: "$group", Value: bson.D{
			{Key: "_id", Value: bson.D{
				{Key: "viewer", Value: "$viewer"},
				{Key: "subjectType", Value: "$subjectType"},
				{Key: "subjectId", Value: "$subjectId"},
			}},
			{Key: "count", Value: bson.D{{Key: "$sum", Value: 1}}},
		}}},
		bson.D{{Key: "$match", Value: bson.D{
			{Key: "count", Value: bson.D{{Key: "$gt", Value: 1}}},
		}}},
		bson.D{{Key: "$limit", Value: 1}},
	})
	if err != nil {
		return fmt.Errorf("inspect following_subjects canonical identity duplicates: %w", err)
	}
	hasDuplicate := duplicateCursor.Next(ctx)
	if cursorErr := duplicateCursor.Err(); cursorErr != nil {
		_ = duplicateCursor.Close(ctx)
		return fmt.Errorf("iterate following_subjects identity duplicates: %w", cursorErr)
	}
	if err := duplicateCursor.Close(ctx); err != nil {
		return fmt.Errorf("close following_subjects identity duplicate cursor: %w", err)
	}
	if hasDuplicate {
		return errors.New(
			"following_subjects contains duplicate rows under canonical Persona identity",
		)
	}

	if _, err := s.collection.UpdateMany(
		ctx,
		bson.M{
			retiredFollowingSubjectViewerKey: bson.M{"$exists": true},
			canonicalKey:                     bson.M{"$exists": false},
		},
		mongo.Pipeline{
			bson.D{{Key: "$set", Value: bson.D{{
				Key: canonicalKey, Value: "$" + retiredFollowingSubjectViewerKey,
			}}}},
			bson.D{{Key: "$unset", Value: retiredFollowingSubjectViewerKey}},
		},
	); err != nil {
		return fmt.Errorf("migrate following_subjects viewer Persona identity: %w", err)
	}
	if _, err := s.collection.UpdateMany(
		ctx,
		bson.M{
			retiredFollowingSubjectViewerKey: bson.M{"$exists": true},
			canonicalKey:                     bson.M{"$exists": true},
		},
		bson.M{"$unset": bson.M{retiredFollowingSubjectViewerKey: ""}},
	); err != nil {
		return fmt.Errorf("remove retired following_subjects viewer identity: %w", err)
	}

	if err := s.replaceRetiredFollowingSubjectIndexes(ctx); err != nil {
		return err
	}
	return nil
}

func (s *MongoFollowingSubjectStore) replaceRetiredFollowingSubjectIndexes(
	ctx context.Context,
) error {
	cursor, err := s.collection.Indexes().List(ctx)
	if err != nil {
		return fmt.Errorf("list following_subjects indexes: %w", err)
	}
	retired := make([]string, 0, 2)
	for cursor.Next(ctx) {
		var index followingSubjectIndexSpec
		if err := cursor.Decode(&index); err != nil {
			_ = cursor.Close(ctx)
			return fmt.Errorf("decode following_subjects index: %w", err)
		}
		expectedUnique := false
		switch index.Name {
		case followingSubjectIdentityIndex:
			expectedUnique = true
		case followingSubjectChangedIndex:
		default:
			continue
		}
		if len(index.Key) == 0 {
			_ = cursor.Close(ctx)
			return fmt.Errorf("following_subjects index %s has no key", index.Name)
		}
		firstKey := index.Key[0].Key
		switch firstKey {
		case retiredFollowingSubjectViewerKey:
			retired = append(retired, index.Name)
		case "viewerPersonaId":
			if index.Unique != expectedUnique {
				_ = cursor.Close(ctx)
				return fmt.Errorf(
					"following_subjects index %s has non-canonical uniqueness",
					index.Name,
				)
			}
		default:
			_ = cursor.Close(ctx)
			return fmt.Errorf(
				"following_subjects index %s has unexpected viewer key %s",
				index.Name,
				firstKey,
			)
		}
	}
	if err := cursor.Err(); err != nil {
		_ = cursor.Close(ctx)
		return fmt.Errorf("iterate following_subjects indexes: %w", err)
	}
	if err := cursor.Close(ctx); err != nil {
		return fmt.Errorf("close following_subjects index cursor: %w", err)
	}
	for _, name := range retired {
		if err := s.collection.Indexes().DropOne(ctx, name); err != nil {
			return fmt.Errorf("drop retired following_subjects index %s: %w", name, err)
		}
	}
	return nil
}

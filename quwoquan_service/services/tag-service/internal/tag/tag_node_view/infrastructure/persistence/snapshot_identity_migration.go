package persistence

import (
	"context"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/bson"
)

const formerGlobalTagRefIndex = "idx_tag_ref"

// MigrateSnapshotIdentity replaces the former global tagRef uniqueness rule with
// the release-scoped snapshot identity. It never deletes taxonomy snapshots.
//
// Historical documents without releaseId remain read-only history and are ignored
// by all release-scoped reads; a canonical re-import creates the first usable
// snapshot.
func (s *MongoTagNodeStore) MigrateSnapshotIdentity(ctx context.Context) error {
	indexes, err := s.coll.Indexes().List(ctx)
	if err != nil {
		return fmt.Errorf("list tag_nodes indexes: %w", err)
	}
	defer indexes.Close(ctx)

	hasFormerGlobalIndex := false
	for indexes.Next(ctx) {
		var index bson.M
		if err := indexes.Decode(&index); err != nil {
			return fmt.Errorf("decode tag_nodes index: %w", err)
		}
		if name, _ := index["name"].(string); name == formerGlobalTagRefIndex {
			hasFormerGlobalIndex = true
			break
		}
	}
	if err := indexes.Err(); err != nil {
		return fmt.Errorf("iterate tag_nodes indexes: %w", err)
	}
	if hasFormerGlobalIndex {
		if err := s.coll.Indexes().DropOne(ctx, formerGlobalTagRefIndex); err != nil {
			return fmt.Errorf("drop former global tagRef index: %w", err)
		}
	}
	if err := s.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("create release-scoped tag_nodes indexes: %w", err)
	}
	return nil
}

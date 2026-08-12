package persistence

import (
	"context"
	"fmt"
	"sort"

	"go.mongodb.org/mongo-driver/v2/mongo"
)

var retiredMediaProcessingDeadLetterIndexes = [...]string{
	"idx_media_processing_dead_letters_aggregate_time",
	"idx_media_processing_dead_letters_consumer_time",
}

type MediaProcessingDeadLetterIndexMigrationResult struct {
	DroppedIndexes []string
}

// MigrateRetiredProcessingDeadLetterIndexes removes only the two retired
// secondary indexes after a controlled migration caller has quiesced the
// object. It does not delete dead-letter facts and is safe to replay.
//
// Application startup deliberately does not call this method. The standalone
// migration command owns execution so release orchestration can bind stop-write,
// backup and hosted readback evidence around the physical change.
func (s *MongoMediaStore) MigrateRetiredProcessingDeadLetterIndexes(
	ctx context.Context,
	expectedDropCount int,
) (MediaProcessingDeadLetterIndexMigrationResult, error) {
	if s == nil || s.processingDeadLetters == nil {
		return MediaProcessingDeadLetterIndexMigrationResult{},
			fmt.Errorf("media processing dead-letter store is not configured")
	}

	existing, err := mediaProcessingDeadLetterIndexNames(ctx, s.processingDeadLetters)
	if err != nil {
		return MediaProcessingDeadLetterIndexMigrationResult{}, err
	}
	if expectedDropCount != 0 && expectedDropCount != len(retiredMediaProcessingDeadLetterIndexes) {
		return MediaProcessingDeadLetterIndexMigrationResult{}, fmt.Errorf(
			"expected retired media processing dead-letter index drop count must be 0 or %d",
			len(retiredMediaProcessingDeadLetterIndexes),
		)
	}
	existingRetiredCount := 0
	for _, name := range retiredMediaProcessingDeadLetterIndexes {
		if existing[name] {
			existingRetiredCount++
		}
	}
	if existingRetiredCount != expectedDropCount {
		return MediaProcessingDeadLetterIndexMigrationResult{}, fmt.Errorf(
			"retired media processing dead-letter index count is %d; expected %d",
			existingRetiredCount,
			expectedDropCount,
		)
	}
	dropped := make([]string, 0, len(retiredMediaProcessingDeadLetterIndexes))
	for _, name := range retiredMediaProcessingDeadLetterIndexes {
		if !existing[name] {
			continue
		}
		if err := s.processingDeadLetters.Indexes().DropOne(ctx, name); err != nil {
			return MediaProcessingDeadLetterIndexMigrationResult{}, fmt.Errorf(
				"drop retired media processing dead-letter index %s: %w",
				name,
				err,
			)
		}
		dropped = append(dropped, name)
	}

	readback, err := mediaProcessingDeadLetterIndexNames(ctx, s.processingDeadLetters)
	if err != nil {
		return MediaProcessingDeadLetterIndexMigrationResult{}, err
	}
	for _, name := range retiredMediaProcessingDeadLetterIndexes {
		if readback[name] {
			return MediaProcessingDeadLetterIndexMigrationResult{}, fmt.Errorf(
				"retired media processing dead-letter index %s remains after migration",
				name,
			)
		}
	}
	sort.Strings(dropped)
	return MediaProcessingDeadLetterIndexMigrationResult{DroppedIndexes: dropped}, nil
}

func mediaProcessingDeadLetterIndexNames(
	ctx context.Context,
	collection *mongo.Collection,
) (map[string]bool, error) {
	specifications, err := collection.Indexes().ListSpecifications(ctx)
	if err != nil {
		return nil, fmt.Errorf("list media processing dead-letter indexes: %w", err)
	}
	names := make(map[string]bool, len(specifications))
	for _, specification := range specifications {
		names[specification.Name] = true
	}
	return names, nil
}

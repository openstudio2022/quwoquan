package application

import (
	"context"
	"errors"
)

type RebuildEntry struct {
	Item    SearchItem
	Visible bool
}

type RebuildSource interface {
	ListSearchItems(context.Context, string, int) ([]RebuildEntry, error)
}

type RebuildReport struct {
	Total    int
	Upserted int
	Deleted  int
	Batches  int
}

func (projector *Projector) Rebuild(
	ctx context.Context,
	source RebuildSource,
	batchSize int,
) (RebuildReport, error) {
	var report RebuildReport
	if projector == nil || projector.index == nil || source == nil {
		return report, errors.New("CircleSearchItemView rebuild requires projector and source")
	}
	if batchSize <= 0 {
		batchSize = 500
	}
	afterID := ""
	for {
		entries, err := source.ListSearchItems(ctx, afterID, batchSize)
		if err != nil {
			return report, err
		}
		if len(entries) == 0 {
			break
		}
		for _, entry := range entries {
			report.Total++
			if entry.Visible {
				if _, err := projector.Upsert(ctx, entry.Item); err != nil {
					return report, err
				}
				report.Upserted++
			} else {
				if _, err := projector.Delete(ctx, entry.Item.CircleID, entry.Item.SourceVersion); err != nil {
					return report, err
				}
				report.Deleted++
			}
		}
		report.Batches++
		next := entries[len(entries)-1].Item.CircleID
		if next == "" || next == afterID {
			return report, errors.New("CircleSearchItemView rebuild cursor did not advance")
		}
		afterID = next
		if len(entries) < batchSize {
			break
		}
	}
	return report, nil
}

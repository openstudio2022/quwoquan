package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

type PersistentSubjectClosureLookup interface {
	IsSubjectClosed(ctx context.Context, subjectID string) (bool, error)
}

type SubjectClosureStateCache interface {
	IsSubjectClosed(ctx context.Context, subjectID string) (bool, error)
	IsSubjectKnownOpen(ctx context.Context, subjectID string) (bool, error)
	RememberOpenSubject(ctx context.Context, subjectID string) error
	BlockClosedSubjects(ctx context.Context, subjectIDs []string) error
}

type SubjectClosureGuard struct {
	persistent PersistentSubjectClosureLookup
	cache      SubjectClosureStateCache
}

func NewSubjectClosureGuard(
	persistent PersistentSubjectClosureLookup,
	cache SubjectClosureStateCache,
) (*SubjectClosureGuard, error) {
	if persistent == nil || cache == nil {
		return nil, errors.New(
			"subject-closure guard requires persistent lookup and cache",
		)
	}
	return &SubjectClosureGuard{
		persistent: persistent,
		cache:      cache,
	}, nil
}

func (guard *SubjectClosureGuard) IsSubjectClosed(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	subjectID = strings.TrimSpace(subjectID)
	if guard == nil || guard.persistent == nil || guard.cache == nil {
		return false, errors.New("subject-closure guard is not configured")
	}
	if subjectID == "" {
		return false, nil
	}

	closed, err := guard.cache.IsSubjectClosed(ctx, subjectID)
	if err != nil {
		return false, fmt.Errorf(
			"check cached closed-account subject state: %w",
			err,
		)
	}
	if closed {
		return true, nil
	}

	knownOpen, err := guard.cache.IsSubjectKnownOpen(ctx, subjectID)
	if err != nil {
		return false, fmt.Errorf(
			"check cached open-account subject state: %w",
			err,
		)
	}
	if knownOpen {
		return false, nil
	}

	closed, err = guard.persistent.IsSubjectClosed(ctx, subjectID)
	if err != nil {
		return false, fmt.Errorf(
			"check persistent closed-account subject state: %w",
			err,
		)
	}
	if closed {
		if err := guard.cache.BlockClosedSubjects(
			ctx,
			[]string{subjectID},
		); err != nil {
			return false, fmt.Errorf(
				"restore cached closed-account subject state: %w",
				err,
			)
		}
		return true, nil
	}

	if err := guard.cache.RememberOpenSubject(ctx, subjectID); err != nil {
		return false, fmt.Errorf(
			"cache open-account subject state: %w",
			err,
		)
	}
	return false, nil
}

var _ interface {
	IsSubjectClosed(context.Context, string) (bool, error)
} = (*SubjectClosureGuard)(nil)

package accountclosure

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const openSubjectCacheTTL = 5 * time.Minute

type RedisKeyRouter interface {
	ForKey(key string) rtredis.Client
}

type RedisPersonalDataCacheCleaner struct {
	router          RedisKeyRouter
	subjectDigestor SubjectDigestor
}

func NewRedisPersonalDataCacheCleaner(
	router RedisKeyRouter,
	subjectDigestor SubjectDigestor,
) (*RedisPersonalDataCacheCleaner, error) {
	if router == nil || subjectDigestor == nil {
		return nil, errors.New(
			"UserAccountClosed Redis cache cleaner requires key router and subject digestor",
		)
	}
	return &RedisPersonalDataCacheCleaner{
		router:          router,
		subjectDigestor: subjectDigestor,
	}, nil
}

func (cleaner *RedisPersonalDataCacheCleaner) BlockClosedSubjects(
	ctx context.Context,
	subjectIDs []string,
) error {
	if cleaner == nil ||
		cleaner.router == nil ||
		cleaner.subjectDigestor == nil {
		return errors.New(
			"UserAccountClosed Redis subject blocker is not configured",
		)
	}
	for _, subjectID := range uniqueStrings(subjectIDs) {
		key, err := closedSubjectRedisKey(
			cleaner.subjectDigestor,
			subjectID,
		)
		if err != nil {
			return err
		}
		if err := cleaner.router.ForKey(key).Set(
			ctx,
			key,
			"closed",
			0,
		); err != nil {
			return fmt.Errorf(
				"persist closed-account Redis subject tombstone: %w",
				err,
			)
		}
		openKey, err := openSubjectRedisKey(
			cleaner.subjectDigestor,
			subjectID,
		)
		if err != nil {
			return err
		}
		if err := cleaner.router.ForKey(openKey).Del(ctx, openKey); err != nil {
			return fmt.Errorf(
				"delete stale open-account Redis subject cache: %w",
				err,
			)
		}
	}
	return nil
}

func (cleaner *RedisPersonalDataCacheCleaner) IsSubjectClosed(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	if cleaner == nil ||
		cleaner.router == nil ||
		cleaner.subjectDigestor == nil {
		return false, errors.New(
			"UserAccountClosed Redis subject guard is not configured",
		)
	}
	key, err := closedSubjectRedisKey(cleaner.subjectDigestor, subjectID)
	if err != nil {
		return false, err
	}
	_, err = cleaner.router.ForKey(key).Get(ctx, key)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf(
			"read closed-account Redis subject tombstone: %w",
			err,
		)
	}
	return true, nil
}

func (cleaner *RedisPersonalDataCacheCleaner) IsSubjectKnownOpen(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	if cleaner == nil ||
		cleaner.router == nil ||
		cleaner.subjectDigestor == nil {
		return false, errors.New(
			"open-account Redis subject cache is not configured",
		)
	}
	key, err := openSubjectRedisKey(cleaner.subjectDigestor, subjectID)
	if err != nil {
		return false, err
	}
	_, err = cleaner.router.ForKey(key).Get(ctx, key)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf(
			"read open-account Redis subject cache: %w",
			err,
		)
	}
	return true, nil
}

func (cleaner *RedisPersonalDataCacheCleaner) RememberOpenSubject(
	ctx context.Context,
	subjectID string,
) error {
	if cleaner == nil ||
		cleaner.router == nil ||
		cleaner.subjectDigestor == nil {
		return errors.New(
			"open-account Redis subject cache is not configured",
		)
	}
	key, err := openSubjectRedisKey(cleaner.subjectDigestor, subjectID)
	if err != nil {
		return err
	}
	if err := cleaner.router.ForKey(key).Set(
		ctx,
		key,
		"open",
		openSubjectCacheTTL,
	); err != nil {
		return fmt.Errorf(
			"cache open-account Redis subject state: %w",
			err,
		)
	}
	return nil
}

func (cleaner *RedisPersonalDataCacheCleaner) DeletePersonalCacheKeys(
	ctx context.Context,
	keys []string,
) error {
	if cleaner == nil || cleaner.router == nil {
		return errors.New(
			"UserAccountClosed Redis cache cleaner is not configured",
		)
	}
	for _, key := range uniqueStrings(keys) {
		key = strings.TrimSpace(key)
		if key == "" {
			continue
		}
		if err := cleaner.router.ForKey(key).Del(ctx, key); err != nil {
			return fmt.Errorf(
				"delete closed-account Redis cache key: %w",
				err,
			)
		}
	}
	return nil
}

var _ PersonalDataCacheCleaner = (*RedisPersonalDataCacheCleaner)(nil)

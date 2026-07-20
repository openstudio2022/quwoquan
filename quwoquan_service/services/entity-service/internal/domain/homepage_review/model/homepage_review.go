// Package model 包含 HomepageReview 聚合。
// 每个 persona 对同一 homepage 仅持有一条评价记录；软删后再次创建复活同一聚合。
package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidReview   = errors.New("invalid homepage review")
	ErrReviewDeleted   = errors.New("homepage review is deleted")
	ErrReviewForbidden = errors.New("homepage review mutation forbidden")
	ErrInvalidRating   = errors.New("homepage review rating must be within 1..5")
)

type Status string

const (
	StatusActive  Status = "active"
	StatusDeleted Status = "deleted"
)

// Snapshot 是 HomepageReview 的持久化边界，只包含值；application 与
// infrastructure 必须通过聚合方法产生新的状态，不能直接改写聚合。
type Snapshot struct {
	ID                        string
	Version                   int64
	HomepageID                string
	AuthorPersonaID           string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	Rating                    int
	Body                      string
	TagRefs                   []string
	Status                    Status
	CreatedAt                 time.Time
	UpdatedAt                 time.Time
}

type CreateParams struct {
	ID                        string
	HomepageID                string
	AuthorPersonaID           string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	Rating                    int
	Body                      string
	TagRefs                   []string
	Now                       time.Time
}

type MutationParams struct {
	Rating                    int
	Body                      string
	TagRefs                   []string
	AuthorDisplayNameSnapshot string
	AuthorAvatarURLSnapshot   string
	Now                       time.Time
}

// HomepageReview 将状态保持私有。Homepage 侧的摘要投影
// （averageRating/ratingCount/highlightTags）不属于此聚合。
type HomepageReview struct {
	id                        string
	version                   int64
	homepageID                string
	authorPersonaID           string
	authorDisplayNameSnapshot string
	authorAvatarURLSnapshot   string
	rating                    int
	body                      string
	tagRefs                   []string
	status                    Status
	createdAt                 time.Time
	updatedAt                 time.Time
}

func Create(params CreateParams) (*HomepageReview, error) {
	now := params.Now.UTC()
	review := &HomepageReview{
		id:                        strings.TrimSpace(params.ID),
		version:                   1,
		homepageID:                strings.TrimSpace(params.HomepageID),
		authorPersonaID:           strings.TrimSpace(params.AuthorPersonaID),
		authorDisplayNameSnapshot: strings.TrimSpace(params.AuthorDisplayNameSnapshot),
		authorAvatarURLSnapshot:   strings.TrimSpace(params.AuthorAvatarURLSnapshot),
		rating:                    params.Rating,
		body:                      strings.TrimSpace(params.Body),
		tagRefs:                   cloneStrings(params.TagRefs),
		status:                    StatusActive,
		createdAt:                 now,
		updatedAt:                 now,
	}
	if err := review.validate(); err != nil {
		return nil, err
	}
	return review, nil
}

func Restore(snapshot Snapshot) (*HomepageReview, error) {
	review := &HomepageReview{
		id:                        strings.TrimSpace(snapshot.ID),
		version:                   snapshot.Version,
		homepageID:                strings.TrimSpace(snapshot.HomepageID),
		authorPersonaID:           strings.TrimSpace(snapshot.AuthorPersonaID),
		authorDisplayNameSnapshot: strings.TrimSpace(snapshot.AuthorDisplayNameSnapshot),
		authorAvatarURLSnapshot:   strings.TrimSpace(snapshot.AuthorAvatarURLSnapshot),
		rating:                    snapshot.Rating,
		body:                      strings.TrimSpace(snapshot.Body),
		tagRefs:                   cloneStrings(snapshot.TagRefs),
		status:                    snapshot.Status,
		createdAt:                 snapshot.CreatedAt.UTC(),
		updatedAt:                 snapshot.UpdatedAt.UTC(),
	}
	if err := review.validate(); err != nil {
		return nil, err
	}
	return review, nil
}

// Update 由作者修改自己的评价；服务端内部 version CAS 由 Store Commit 保证。
func (r *HomepageReview) Update(actorPersonaID string, params MutationParams) error {
	if r == nil || r.status == StatusDeleted {
		return ErrReviewDeleted
	}
	if err := r.requireAuthor(actorPersonaID); err != nil {
		return err
	}
	if err := r.advance(params.Now); err != nil {
		return err
	}
	r.applyMutation(params)
	return nil
}

// Delete 是 active -> deleted 命名迁移；内容保留供复活预填。
func (r *HomepageReview) Delete(actorPersonaID string, now time.Time) error {
	if r == nil || r.status == StatusDeleted {
		return ErrReviewDeleted
	}
	if err := r.requireAuthor(actorPersonaID); err != nil {
		return err
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.status = StatusDeleted
	return nil
}

// Revive 在软删记录上复活同一聚合：重置内容、status 回 active、version 继续递增。
func (r *HomepageReview) Revive(actorPersonaID string, params MutationParams) error {
	if r == nil {
		return ErrInvalidReview
	}
	if r.status != StatusDeleted {
		return ErrInvalidReview
	}
	if err := r.requireAuthor(actorPersonaID); err != nil {
		return err
	}
	if err := r.advance(params.Now); err != nil {
		return err
	}
	r.status = StatusActive
	r.applyMutation(params)
	return nil
}

func (r *HomepageReview) requireAuthor(actorPersonaID string) error {
	actor := strings.TrimSpace(actorPersonaID)
	if actor == "" || actor != r.authorPersonaID {
		return ErrReviewForbidden
	}
	return nil
}

func (r *HomepageReview) applyMutation(params MutationParams) {
	r.rating = params.Rating
	r.body = strings.TrimSpace(params.Body)
	r.tagRefs = cloneStrings(params.TagRefs)
	if name := strings.TrimSpace(params.AuthorDisplayNameSnapshot); name != "" {
		r.authorDisplayNameSnapshot = name
	}
	if avatar := strings.TrimSpace(params.AuthorAvatarURLSnapshot); avatar != "" {
		r.authorAvatarURLSnapshot = avatar
	}
}

func (r *HomepageReview) advance(now time.Time) error {
	next := now.UTC()
	if next.Before(r.updatedAt) {
		next = r.updatedAt
	}
	r.version++
	r.updatedAt = next
	return r.validate()
}

func (r *HomepageReview) validate() error {
	if r.id == "" || r.homepageID == "" || r.authorPersonaID == "" {
		return ErrInvalidReview
	}
	if r.version < 1 {
		return ErrInvalidReview
	}
	if r.rating < 1 || r.rating > 5 {
		return ErrInvalidRating
	}
	switch r.status {
	case StatusActive, StatusDeleted:
	default:
		return ErrInvalidReview
	}
	if r.createdAt.IsZero() || r.updatedAt.IsZero() {
		return ErrInvalidReview
	}
	return nil
}

func (r *HomepageReview) ID() string {
	if r == nil {
		return ""
	}
	return r.id
}

func (r *HomepageReview) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}

func (r *HomepageReview) Status() Status {
	if r == nil {
		return ""
	}
	return r.status
}

func (r *HomepageReview) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:                        r.id,
		Version:                   r.version,
		HomepageID:                r.homepageID,
		AuthorPersonaID:           r.authorPersonaID,
		AuthorDisplayNameSnapshot: r.authorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   r.authorAvatarURLSnapshot,
		Rating:                    r.rating,
		Body:                      r.body,
		TagRefs:                   cloneStrings(r.tagRefs),
		Status:                    r.status,
		CreatedAt:                 r.createdAt,
		UpdatedAt:                 r.updatedAt,
	}
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	cloned := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		cloned = append(cloned, trimmed)
	}
	if len(cloned) == 0 {
		return nil
	}
	return cloned
}

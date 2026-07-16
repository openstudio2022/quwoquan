// Package reaction 定义 ContentReaction 独立聚合及其局部不变量。
package reaction

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidActor    = errors.New("invalid reaction actor")
	ErrInvalidIdentity = errors.New("invalid reaction identity")
	ErrInvalidValue    = errors.New("invalid reaction value")
	ErrInvalidState    = errors.New("invalid reaction state")
)

type ActorDimension string

const (
	ActorDimensionPersona ActorDimension = "persona"
	ActorDimensionDevice  ActorDimension = "device"
)

// Actor 把公开 persona 与匿名 device 明确分成不相交的关系维度。
type Actor struct {
	Dimension ActorDimension
	ID        string
}

type CommentReactionCounts struct {
	LikeCount    int64
	DislikeCount int64
}

func NewActor(dimension ActorDimension, id string) (Actor, error) {
	actor := Actor{Dimension: dimension, ID: strings.TrimSpace(id)}
	if err := actor.Validate(); err != nil {
		return Actor{}, err
	}
	return actor, nil
}

func (a Actor) Validate() error {
	if strings.TrimSpace(a.ID) == "" {
		return fmt.Errorf("%w: actor id is required", ErrInvalidActor)
	}
	switch a.Dimension {
	case ActorDimensionPersona, ActorDimensionDevice:
		return nil
	default:
		return fmt.Errorf("%w: unsupported dimension %q", ErrInvalidActor, a.Dimension)
	}
}

// TargetKind 是 ContentReaction 可引用对象的封闭集合。新增目标必须先扩展
// metadata、授权、目标存在性端口和投影消费者，不能退化为任意字符串。
type TargetKind string

const (
	TargetKindPost    TargetKind = "post"
	TargetKindComment TargetKind = "comment"
)

type Target struct {
	Kind TargetKind
	ID   string
}

func NewTarget(kind TargetKind, id string) (Target, error) {
	target := Target{Kind: kind, ID: strings.TrimSpace(id)}
	if err := target.Validate(); err != nil {
		return Target{}, err
	}
	return target, nil
}

func (t Target) Validate() error {
	if strings.TrimSpace(t.ID) == "" {
		return fmt.Errorf("%w: target id is required", ErrInvalidIdentity)
	}
	switch t.Kind {
	case TargetKindPost, TargetKindComment:
		return nil
	default:
		return fmt.Errorf("%w: unsupported target kind %q", ErrInvalidIdentity, t.Kind)
	}
}

type Identity struct {
	Target Target
	Actor  Actor
}

func NewIdentity(target Target, actor Actor) (Identity, error) {
	normalizedTarget, err := NewTarget(target.Kind, target.ID)
	if err != nil {
		return Identity{}, err
	}
	normalizedActor, err := NewActor(actor.Dimension, actor.ID)
	if err != nil {
		return Identity{}, err
	}
	identity := Identity{Target: normalizedTarget, Actor: normalizedActor}
	if err := identity.Validate(); err != nil {
		return Identity{}, err
	}
	return identity, nil
}

func NewPostIdentity(postID string, actor Actor) (Identity, error) {
	target, err := NewTarget(TargetKindPost, postID)
	if err != nil {
		return Identity{}, err
	}
	return NewIdentity(target, actor)
}

func NewCommentIdentity(commentID string, actor Actor) (Identity, error) {
	target, err := NewTarget(TargetKindComment, commentID)
	if err != nil {
		return Identity{}, err
	}
	return NewIdentity(target, actor)
}

func (i Identity) Validate() error {
	if err := i.Target.Validate(); err != nil {
		return err
	}
	return i.Actor.Validate()
}

// AggregateID 是关系 identity 的稳定散列，唯一性仍由 Mongo 复合索引强制。
func (i Identity) AggregateID() string {
	sum := sha256.Sum256([]byte(
		string(i.Target.Kind) + "\x00" + strings.TrimSpace(i.Target.ID) + "\x00" +
			string(i.Actor.Dimension) + "\x00" + strings.TrimSpace(i.Actor.ID),
	))
	return "reaction_" + hex.EncodeToString(sum[:])
}

// Value 是成员关系当前值。none 仍作为聚合状态持久化，以支持幂等撤销、
// 版本竞争和完整审计；它不是一条活跃互动。
type Value string

const (
	ValueNone    Value = "none"
	ValueLike    Value = "like"
	ValueDislike Value = "dislike"
)

func (v Value) ValidateFor(kind TargetKind) error {
	switch kind {
	case TargetKindPost:
		if v == ValueNone || v == ValueLike {
			return nil
		}
	case TargetKindComment:
		if v == ValueNone || v == ValueLike || v == ValueDislike {
			return nil
		}
	}
	return fmt.Errorf("%w: %q is unsupported for %q", ErrInvalidValue, v, kind)
}

type Snapshot struct {
	ID        string
	Version   int64
	Identity  Identity
	Value     Value
	ReactedAt *time.Time
	CreatedAt time.Time
	UpdatedAt time.Time
}

// ContentReaction 的可变状态只允许通过 Set 行为变更。
type ContentReaction struct {
	id        string
	version   int64
	identity  Identity
	value     Value
	reactedAt *time.Time
	createdAt time.Time
	updatedAt time.Time
}

func New(identity Identity, value Value, now time.Time) (*ContentReaction, error) {
	if err := identity.Validate(); err != nil {
		return nil, err
	}
	if err := value.ValidateFor(identity.Target.Kind); err != nil {
		return nil, err
	}
	now = now.UTC()
	if now.IsZero() {
		return nil, fmt.Errorf("%w: creation time is required", ErrInvalidState)
	}
	aggregate := &ContentReaction{
		id: identity.AggregateID(), version: 1, identity: identity, value: value,
		createdAt: now, updatedAt: now,
	}
	if value != ValueNone {
		reactedAt := now
		aggregate.reactedAt = &reactedAt
	}
	if err := aggregate.validate(); err != nil {
		return nil, err
	}
	return aggregate, nil
}

func Restore(snapshot Snapshot) (*ContentReaction, error) {
	aggregate := &ContentReaction{
		id: strings.TrimSpace(snapshot.ID), version: snapshot.Version,
		identity: snapshot.Identity, value: snapshot.Value,
		reactedAt: cloneTime(snapshot.ReactedAt), createdAt: snapshot.CreatedAt.UTC(),
		updatedAt: snapshot.UpdatedAt.UTC(),
	}
	if err := aggregate.validate(); err != nil {
		return nil, err
	}
	return aggregate, nil
}

func (r *ContentReaction) Set(value Value, now time.Time) (bool, error) {
	if r == nil {
		return false, fmt.Errorf("%w: aggregate is required", ErrInvalidState)
	}
	if err := value.ValidateFor(r.identity.Target.Kind); err != nil {
		return false, err
	}
	if r.value == value {
		return false, nil
	}
	if err := r.advance(now); err != nil {
		return false, err
	}
	r.value = value
	if value == ValueNone {
		r.reactedAt = nil
	} else {
		reactedAt := r.updatedAt
		r.reactedAt = &reactedAt
	}
	return true, nil
}

func (r *ContentReaction) ID() string {
	if r == nil {
		return ""
	}
	return r.id
}

func (r *ContentReaction) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}

func (r *ContentReaction) Identity() Identity {
	if r == nil {
		return Identity{}
	}
	return r.identity
}

func (r *ContentReaction) Value() Value {
	if r == nil {
		return ""
	}
	return r.value
}

func (r *ContentReaction) IsLiked() bool { return r != nil && r.value == ValueLike }

func (r *ContentReaction) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID: r.id, Version: r.version, Identity: r.identity, Value: r.value,
		ReactedAt: cloneTime(r.reactedAt), CreatedAt: r.createdAt, UpdatedAt: r.updatedAt,
	}
}

func (r *ContentReaction) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(r.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidState)
	}
	r.version++
	r.updatedAt = now
	return nil
}

func (r *ContentReaction) validate() error {
	if r == nil || strings.TrimSpace(r.id) == "" || r.version < 1 ||
		r.identity.AggregateID() != r.id || r.createdAt.IsZero() || r.updatedAt.IsZero() ||
		r.updatedAt.Before(r.createdAt) {
		return fmt.Errorf("%w: required aggregate state is missing", ErrInvalidState)
	}
	if err := r.identity.Validate(); err != nil {
		return err
	}
	if err := r.value.ValidateFor(r.identity.Target.Kind); err != nil {
		return err
	}
	if r.value == ValueNone && r.reactedAt != nil {
		return fmt.Errorf("%w: none reaction retains reactedAt", ErrInvalidState)
	}
	if r.value != ValueNone && (r.reactedAt == nil || r.reactedAt.IsZero()) {
		return fmt.Errorf("%w: active reaction has no reactedAt", ErrInvalidState)
	}
	return nil
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	copied := value.UTC()
	return &copied
}

package following_subject

import (
	"context"
	"time"
)

// Row 是 following_subjects 投影行（读模型）。展示字段由 reader 按主体类型
// enrich；投影本体只持有标识、关注与访问水位。bson tag 供 infrastructure
// 适配器复用同一形状，本包不依赖任何驱动。
type Row struct {
	ViewerPersonaID    string     `bson:"viewerPersonaId" json:"viewerPersonaId"`
	SubjectType        string     `bson:"subjectType" json:"subjectType"`
	SubjectID          string     `bson:"subjectId" json:"subjectId"`
	FollowedAt         time.Time  `bson:"followedAt" json:"followedAt"`
	LastVisitedAt      *time.Time `bson:"lastVisitedAt,omitempty" json:"lastVisitedAt,omitempty"`
	LatestChangedAt    *time.Time `bson:"latestChangedAt,omitempty" json:"latestChangedAt,omitempty"`
	UnreadChangeCount  int64      `bson:"unreadChangeCount" json:"unreadChangeCount"`
	LatestChangeReason string     `bson:"latestChangeReason,omitempty" json:"latestChangeReason,omitempty"`
	SourceVersion      int64      `bson:"sourceVersion" json:"sourceVersion"`
	UpdatedAt          time.Time  `bson:"updatedAt" json:"updatedAt"`
}

// ProjectionStore 是投影的唯一 writer 端口（projector 消费）。
type ProjectionStore interface {
	UpsertFollow(ctx context.Context, personaID, subjectType, subjectID string, followedAt time.Time, sourceVersion int64) error
	RemoveFollow(ctx context.Context, personaID, subjectType, subjectID string, sourceVersion int64) error
}

// ProjectionReader 是关注频道列表的 named reader 端口。
type ProjectionReader interface {
	List(ctx context.Context, personaID, subjectType string, limit int) ([]Row, error)
}

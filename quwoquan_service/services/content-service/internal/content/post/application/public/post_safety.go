package public

import (
	"context"
	"errors"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/safety"
)

type PostCandidateSafetyReader interface {
	ReadSafety(context.Context, wire.ReadPostCandidateSafetyQuery) (wire.PostCandidateSafetyResult, error)
}
type PostCandidateSafetyQueryFacade struct{ reader PostCandidateSafetyReader }

func NewPostCandidateSafetyQueryFacade(reader PostCandidateSafetyReader) *PostCandidateSafetyQueryFacade {
	return &PostCandidateSafetyQueryFacade{reader}
}
func (f *PostCandidateSafetyQueryFacade) Read(ctx context.Context, q wire.ReadPostCandidateSafetyQuery) (wire.PostCandidateSafetyResult, error) {
	if f == nil || f.reader == nil {
		return wire.PostCandidateSafetyResult{}, ErrPostSafetyNotReady
	}
	return f.reader.ReadSafety(ctx, q)
}

var ErrPostSafetyNotReady = errors.New("CONTENT.RELEASE.query_barrier_not_ready")
var ErrPostSafetyConflict = errors.New("CONTENT.RELEASE.query_barrier_invalid")

// PostSafetyAuthority只确认独立密钥与恢复水位以及源资格，不能由caller boolean实现。
// 生产实现必须读受管证据；测试authority只代表隔离前置，不授予生产资格。
type PostSafetyAuthority interface {
	VerifyRecovery(context.Context) error
	VerifySource(context.Context, string, string, string) error
}
type PostSafetySourceVerifier interface {
	VerifySource(context.Context, string, string, string) error
}

type PostSafetyMember struct {
	ObjectDigest   string
	SafetyRevision int64
}
type PostSafetyPort interface {
	Identity(string, string) (string, error)
	Initialize(context.Context, string, string, int64, string, string, string) (PostSafetyMember, error)
	Read(context.Context, string, string) (PostSafetyMember, error)
	LoadRevision(context.Context, string, string) (PostSafetyMember, error)
	TouchAllowed(context.Context, []PostSafetyMember) error
	Decide(context.Context, string, string, int64, int64, string, string, string) (PostSafetyMember, error)
}

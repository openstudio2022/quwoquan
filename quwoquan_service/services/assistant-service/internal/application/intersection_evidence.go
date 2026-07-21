package application

import (
	"context"
	"errors"
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	assistantgenerated "quwoquan_service/services/assistant-service/internal/generated"
)

// ErrIntersectionEvidenceNotFound 覆盖对象不存在、授权拒绝、证据撤销和快照不匹配，
// 防止通过不同错误向客户端泄露其他 persona 的交集事实。
var ErrIntersectionEvidenceNotFound = errors.New("authorized intersection evidence not found")

// ErrIntersectionEvidenceUnavailable 表示无法从 content 的公开 Reader 核验当前事实。
var ErrIntersectionEvidenceUnavailable = errors.New("authorized intersection evidence unavailable")

func (s *AssistantService) resolveAuthorizedIntersectionEvidence(
	ctx context.Context,
	personaID string,
	refs []assistant.AssistantIntersectionEvidenceRef,
) ([]assistant.AuthorizedIntersectionEvidence, error) {
	if len(refs) == 0 {
		return nil, nil
	}
	if s.intersectionEvidence == nil {
		return nil, assistantgenerated.AppErrorFromIntersectionEvidenceUnavailable(
			"authorized intersection evidence reader is not configured",
		)
	}
	for _, ref := range refs {
		if strings.TrimSpace(ref.IntersectionID) == "" ||
			strings.TrimSpace(ref.EvidenceID) == "" ||
			strings.TrimSpace(ref.SourceRef) == "" ||
			strings.TrimSpace(ref.ObjectTypeRef) == "" ||
			strings.TrimSpace(ref.ObjectID) == "" {
			return nil, assistantgenerated.AppErrorFromIntersectionEvidenceNotFound(
				"intersection evidence reference is incomplete",
			)
		}
	}
	evidence, err := s.intersectionEvidence.ResolveAuthorizedIntersectionEvidence(
		ctx,
		strings.TrimSpace(personaID),
		refs,
	)
	if err == nil && len(evidence) == len(refs) {
		return evidence, nil
	}
	if err == nil {
		err = ErrIntersectionEvidenceNotFound
	}
	if errors.Is(err, ErrIntersectionEvidenceNotFound) {
		return nil, assistantgenerated.AppErrorFromIntersectionEvidenceNotFound(err.Error())
	}
	return nil, assistantgenerated.AppErrorFromIntersectionEvidenceUnavailable(err.Error())
}

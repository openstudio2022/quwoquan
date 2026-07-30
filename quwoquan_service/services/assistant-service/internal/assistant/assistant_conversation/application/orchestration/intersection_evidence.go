package orchestration

import (
	"context"
	"errors"
	"strings"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
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
		return nil, runerrors.AppErrorFromIntersectionEvidenceUnavailable(
			"authorized intersection evidence reader is not configured",
		)
	}
	for _, ref := range refs {
		if strings.TrimSpace(ref.IntersectionID) == "" ||
			strings.TrimSpace(ref.EvidenceID) == "" ||
			strings.TrimSpace(ref.SourceRef) == "" ||
			strings.TrimSpace(ref.ObjectTypeRef) == "" ||
			strings.TrimSpace(ref.ObjectID) == "" {
			return nil, runerrors.AppErrorFromIntersectionEvidenceNotFound(
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
		return nil, runerrors.AppErrorFromIntersectionEvidenceNotFound(err.Error())
	}
	return nil, runerrors.AppErrorFromIntersectionEvidenceUnavailable(err.Error())
}

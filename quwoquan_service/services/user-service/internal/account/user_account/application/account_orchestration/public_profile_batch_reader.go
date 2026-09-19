package application

import (
	"context"
	"fmt"
	"strings"

	generated "quwoquan_service/services/user-service/generated/account/user_account"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// GetPersonaProfileViews 批量组装一页普通 Persona 的公开资料。生产存储必须
// 暴露两个 batch port，因此页大小 20/100 都固定为 Persona + owner 两次查询。
// 缺席、私密、strict、退役条目不出现在结果中；依赖错误整体返回，调用方不得
// 将其伪装为空页。
func (s *PersonaService) GetPersonaProfileViews(
	ctx context.Context,
	personaIDs []string,
) (map[string]map[string]any, error) {
	ordered := uniqueNonBlank(personaIDs)
	views := make(map[string]map[string]any, len(ordered))
	if len(ordered) == 0 {
		return views, nil
	}
	personaBatch, ok := s.personas.(userrepo.PersonaBatchReader)
	if !ok {
		return nil, generated.AppErrorFromInternalError("public Persona batch reader unavailable")
	}
	profileBatch, ok := s.profiles.(userrepo.UserProfileBatchReader)
	if !ok {
		return nil, generated.AppErrorFromInternalError("public owner profile batch reader unavailable")
	}
	personas, err := personaBatch.FindManyByPersonaID(ctx, ordered)
	if err != nil {
		return nil, fmt.Errorf("batch read public Personas: %w", err)
	}
	ownerIDs := make([]string, 0, len(personas))
	for _, persona := range personas {
		if canExposePublicPersona(&persona) && strings.TrimSpace(persona.UserID) != "" {
			ownerIDs = append(ownerIDs, persona.UserID)
		}
	}
	owners, err := profileBatch.FindManyByID(ctx, uniqueNonBlank(ownerIDs))
	if err != nil {
		return nil, fmt.Errorf("batch read public Persona owners: %w", err)
	}
	for _, personaID := range ordered {
		persona, found := personas[personaID]
		if !found || !canExposePublicPersona(&persona) {
			continue
		}
		owner, found := owners[persona.UserID]
		if !found || strings.TrimSpace(owner.IdentityOrigin) == "content_release" {
			continue
		}
		view := buildPublicPersonaProfileView(&owner, &persona)
		if hasPublicLeakage(view) {
			return nil, generated.AppErrorFromInternalError("public Persona batch projection leaked owner identity")
		}
		views[personaID] = view
	}
	return views, nil
}

func uniqueNonBlank(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

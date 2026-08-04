package main

import (
	"context"
	"errors"
	"log"
	"strings"

	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	consenterrors "quwoquan_service/services/assistant-service/generated/assistant/skill_consent"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
	assistantdomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runports "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	skillcatalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillcatalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	settingapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
)

type skillAccessAuthorizer func(
	ctx context.Context,
	accountID string,
	skillID string,
	surfaceKind string,
	surfaceID string,
) error

func newSkillAccessAuthorizer(
	settingQueries *settingapplication.QueryFacade,
	consentQueries *consentapplication.QueryFacade,
	placementQueries *placementapplication.QueryFacade,
	activeSkillCatalog *skillcatalogactive.CatalogSource,
) skillAccessAuthorizer {
	return func(
		ctx context.Context,
		accountID string,
		skillID string,
		surfaceKind string,
		surfaceID string,
	) error {
		accountID = strings.TrimSpace(accountID)
		skillID = strings.TrimSpace(skillID)
		surfaceKind = strings.TrimSpace(surfaceKind)
		surfaceID = strings.TrimSpace(surfaceID)
		manifest, found, manifestErr := skillcatalogapplication.ResolveRuntimeManifest(
			ctx,
			activeSkillCatalog,
			skillID,
		)
		if manifestErr != nil || !found {
			return runruntime.ErrSkillPackageUnavailable
		}
		if surfaceKind == "" {
			enabled, settingErr := settingQueries.IsEnabled(ctx, accountID, skillID)
			if settingErr != nil {
				return runruntime.ErrSkillSettingUnavailable
			}
			if !enabled {
				return runruntime.ErrSkillDisabled
			}
		} else {
			if surfaceID == "" ||
				(surfaceKind != placementmodel.SurfaceConversation &&
					surfaceKind != placementmodel.SurfaceCircle) {
				return runruntime.ErrSkillDisabled
			}
			sharedAllowed := false
			for _, allowedSurface := range manifest.ActivationProfile.AllowedSurfaceKinds {
				if strings.TrimSpace(allowedSurface) == surfaceKind {
					sharedAllowed = true
					break
				}
			}
			if !sharedAllowed {
				return runruntime.ErrSkillDisabled
			}
			allowed, placementErr := placementQueries.AllowsSkill(
				ctx,
				surfaceKind,
				surfaceID,
				skillID,
			)
			if placementErr != nil {
				if errors.Is(placementErr, placementmodel.ErrNotFound) {
					return runruntime.ErrSkillDisabled
				}
				return runruntime.ErrSkillSettingUnavailable
			}
			if !allowed {
				return runruntime.ErrSkillDisabled
			}
		}
		consentErr := consentQueries.Require(
			ctx,
			accountID,
			skillID,
			skillcatalogapplication.RequiredContextConsentScopes(
				manifest.ContextProfile,
			),
		)
		switch {
		case errors.Is(consentErr, consentmodel.ErrConsentRequired):
			return runerrors.AppErrorFromSkillConsentRequired(
				"active consent is required for skill " + skillID,
			)
		case errors.Is(consentErr, consentmodel.ErrStorageUnavailable):
			return consenterrors.AppErrorFromConsentUnavailable(
				"skill consent reader is unavailable",
			)
		default:
			return consentErr
		}
	}
}

func configureAgentSkillAccess(
	agentLoop *orchestration.AgentLoop,
	settingQueries *settingapplication.QueryFacade,
	placementQueries *placementapplication.QueryFacade,
	activeSkillCatalog *skillcatalogactive.CatalogSource,
	authorizeSkillAccess skillAccessAuthorizer,
) {
	agentLoop.SkillCandidates = orchestration.SkillCandidateAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
	) ([]string, error) {
		manifests, loadErr := activeSkillCatalog.Load(ctx)
		if loadErr != nil {
			return nil, runruntime.ErrSkillPackageUnavailable
		}
		surfaceKind := strings.TrimSpace(turn.RequestContext.SurfaceKind)
		surfaceID := strings.TrimSpace(turn.RequestContext.SurfaceID)
		allowed := make([]string, 0, len(manifests))
		if surfaceKind == "" {
			for _, manifest := range manifests {
				if !manifest.IsReactive() {
					continue
				}
				enabled, settingErr := settingQueries.IsEnabled(
					ctx,
					turn.UserID,
					manifest.SkillID,
				)
				if settingErr != nil {
					return nil, runruntime.ErrSkillSettingUnavailable
				}
				if enabled {
					allowed = append(allowed, manifest.SkillID)
				}
			}
			return allowed, nil
		}
		if surfaceID == "" ||
			(surfaceKind != placementmodel.SurfaceConversation &&
				surfaceKind != placementmodel.SurfaceCircle) {
			return []string{}, nil
		}
		placement, placementErr := placementQueries.Get(
			ctx,
			turn.UserID,
			turn.RequestContext.PersonaID,
			surfaceKind,
			surfaceID,
		)
		if placementErr != nil {
			if errors.Is(placementErr, placementmodel.ErrNotFound) ||
				errors.Is(placementErr, placementmodel.ErrForbidden) {
				return []string{}, nil
			}
			return nil, runruntime.ErrSkillSettingUnavailable
		}
		for _, manifest := range manifests {
			if !manifest.IsReactive() || !placement.Allows(manifest.SkillID) {
				continue
			}
			for _, allowedSurfaceKind := range manifest.ActivationProfile.AllowedSurfaceKinds {
				if strings.TrimSpace(allowedSurfaceKind) == surfaceKind {
					allowed = append(allowed, manifest.SkillID)
					break
				}
			}
		}
		return allowed, nil
	})
	agentLoop.SkillAccess = orchestration.SkillExecutionAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
		skillID string,
	) error {
		return authorizeSkillAccess(
			ctx,
			turn.UserID,
			skillID,
			turn.RequestContext.SurfaceKind,
			turn.RequestContext.SurfaceID,
		)
	})
}

func configureAgentToolAccess(
	agentLoop *orchestration.AgentLoop,
	policy *toolaccess.Policy,
) {
	agentLoop.ToolAccess = orchestration.ToolExecutionAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
		skill orchestration.SkillSelection,
		toolName string,
		metadata toolpkg.Metadata,
	) error {
		requirement := metadata.Capability
		if strings.TrimSpace(requirement.CapabilityKey) == "" &&
			strings.TrimSpace(requirement.ConnectorRequirement) == "" &&
			len(requirement.ConsentScopes) == 0 &&
			len(requirement.AllowedSurfaceKinds) == 0 &&
			!requirement.RecheckAtExecution {
			return nil
		}
		decision, authorizeErr := policy.Authorize(
			ctx,
			toolaccess.Request{
				AccountID:   turn.UserID,
				SkillID:     skill.SkillID,
				SurfaceKind: turn.RequestContext.SurfaceKind,
				Requirement: toolaccess.Requirement{
					CapabilityKey:        requirement.CapabilityKey,
					ConnectorRequirement: requirement.ConnectorRequirement,
					ConsentScopes:        requirement.ConsentScopes,
					AllowedSurfaceKinds:  requirement.AllowedSurfaceKinds,
					RecheckAtExecution:   requirement.RecheckAtExecution,
				},
			},
		)
		log.Printf(
			"assistant tool capability_decision turnId=%s skillId=%s toolName=%s capability=%s surface=%s allowed=%t reason=%s",
			turn.TurnID,
			skill.SkillID,
			strings.TrimSpace(toolName),
			strings.TrimSpace(requirement.CapabilityKey),
			decision.SurfaceKind,
			decision.Allowed,
			decision.Reason,
		)
		switch {
		case authorizeErr == nil:
			return nil
		case errors.Is(authorizeErr, toolaccess.ErrConsentRequired):
			return runerrors.AppErrorFromSkillConsentRequired(
				"tool capability consent is not active",
			)
		case errors.Is(authorizeErr, toolaccess.ErrConnectorRequired),
			errors.Is(authorizeErr, toolaccess.ErrSurfaceDenied):
			return runerrors.AppErrorFromConnectorCapabilityRequired(
				"required connector capability is not active for this surface",
			)
		default:
			return runerrors.AppErrorFromConnectorGatewayUnavailable(
				"connector capability policy could not be evaluated",
			)
		}
	})
}

func newAssistantRunContextResolver(
	pageContextFacade *pageapplication.Facade,
	intersectionEvidence runports.IntersectionEvidenceReader,
) *runapplication.ContextResolver {
	return runapplication.NewContextResolver(
		runapplication.CurrentPageContextReaderFunc(func(
			ctx context.Context,
			accountID string,
		) (map[string]any, bool, error) {
			current, readErr := pageContextFacade.Current(ctx, accountID)
			if readErr != nil || current == nil {
				return nil, false, readErr
			}
			objects := make([]any, 0, len(current.Snapshot.PageObjects))
			for _, object := range current.Snapshot.PageObjects {
				objects = append(objects, map[string]any{
					"objectTypeRef": object.ObjectTypeRef,
					"objectId":      object.ObjectID,
				})
			}
			actions := make([]any, 0, len(current.Snapshot.UserActions))
			for _, action := range current.Snapshot.UserActions {
				actions = append(actions, map[string]any{
					"action":        action.ActionType,
					"objectTypeRef": action.ObjectTypeRef,
					"objectId":      action.ObjectID,
				})
			}
			return map[string]any{
				"capturedAt":  current.CapturedAt.UTC(),
				"pageType":    current.Snapshot.PageType,
				"pageObjects": objects,
				"userActions": actions,
				"consentMatrix": map[string]any{
					"canReadCurrentPage": current.Snapshot.ConsentGranted,
				},
			}, true, nil
		}),
		runapplication.IntersectionEvidenceAuthorizerFunc(func(
			ctx context.Context,
			personaID string,
			references []runapplication.IntersectionEvidenceRef,
		) ([]runapplication.AuthorizedIntersectionEvidence, error) {
			requested := make(
				[]assistantdomain.AssistantIntersectionEvidenceRef,
				0,
				len(references),
			)
			for _, reference := range references {
				requested = append(requested, assistantdomain.AssistantIntersectionEvidenceRef{
					IntersectionID: reference.IntersectionID,
					EvidenceID:     reference.EvidenceID,
					SourceRef:      reference.SourceRef,
					ObjectTypeRef:  reference.ObjectTypeRef,
					ObjectID:       reference.ObjectID,
				})
			}
			authorized, authorizeErr := intersectionEvidence.ResolveAuthorizedIntersectionEvidence(
				ctx,
				personaID,
				requested,
			)
			if authorizeErr != nil {
				if errors.Is(authorizeErr, runapplication.ErrIntersectionEvidenceNotFound) {
					return nil, runapplication.ErrIntersectionEvidenceNotFound
				}
				return nil, authorizeErr
			}
			result := make(
				[]runapplication.AuthorizedIntersectionEvidence,
				0,
				len(authorized),
			)
			for _, evidence := range authorized {
				result = append(result, runapplication.AuthorizedIntersectionEvidence{
					IntersectionID: evidence.IntersectionID,
					EvidenceID:     evidence.EvidenceID,
					SourceRef:      evidence.SourceRef,
					ObjectTypeRef:  evidence.ObjectTypeRef,
					ObjectID:       evidence.ObjectID,
					PrimaryText:    evidence.PrimaryText,
					Dimension:      evidence.Dimension,
					VerifiedAt:     evidence.VerifiedAt,
				})
			}
			return result, nil
		}),
	)
}

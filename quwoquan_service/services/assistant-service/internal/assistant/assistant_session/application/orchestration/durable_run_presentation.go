package orchestration

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
)

type presentationTemplateLoader interface {
	ResolvePresentationTemplate(context.Context, string, string) (json.RawMessage, bool, error)
}

// buildExecutionPresentation resolves only templates frozen in the active Skill
// package. It never synthesizes presentation nodes or actions in the AgentLoop.
func (e *DurableRunExecutor) buildExecutionPresentation(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	answer string,
	processes []map[string]any,
	pendingApproval map[string]any,
) (map[string]any, error) {
	if len(request.SurfaceCapabilities) == 0 ||
		(strings.TrimSpace(answer) == "" && len(pendingApproval) == 0) {
		return nil, nil
	}
	skillID := strings.TrimSpace(request.RequestedSkillID)
	if skillID == "" {
		skillID = executionStringFromProcesses(processes, "skillId")
	}
	if skillID == "" {
		return nil, nil
	}
	manifest, found, err := e.loop.resolveSkillManifest(ctx, skillID)
	if err != nil {
		return nil, fmt.Errorf("load adaptive presentation skill: %w", err)
	}
	if !found || len(manifest.Presentation.TemplateRefs) == 0 {
		return nil, nil
	}
	loader, ok := e.loop.Catalog.(presentationTemplateLoader)
	if !ok {
		return nil, fmt.Errorf("active Skill package presentation loader is unavailable")
	}
	sources := []map[string]any{{"answer": answer}}
	actionPolicy := presentationpkg.ActionPolicy(nil)
	fallbackMarkdown := answer
	preferredTemplateID := ""
	if len(pendingApproval) > 0 {
		confirmation, fallback, templateID, policy, err := toolConfirmationPresentation(
			pendingApproval,
		)
		if err != nil {
			return nil, err
		}
		sources = []map[string]any{confirmation}
		fallbackMarkdown = fallback
		preferredTemplateID = templateID
		actionPolicy = policy
	} else {
		contextSources, err := e.executionPresentationContextSources(
			ctx, request, manifest,
		)
		if err != nil {
			return nil, err
		}
		sources = append(contextSources, sources...)
	}
	var fallback *presentationpkg.Document
	for _, templateID := range manifest.Presentation.TemplateRefs {
		if preferredTemplateID != "" && templateID != preferredTemplateID {
			continue
		}
		raw, found, err := loader.ResolvePresentationTemplate(
			ctx, templateID, manifest.SkillID,
		)
		if err != nil {
			return nil, err
		}
		if !found {
			return nil, fmt.Errorf("active presentation template %q is unavailable", templateID)
		}
		template, err := presentationpkg.DecodeTemplate(raw)
		if err != nil {
			return nil, err
		}
		data, selected := selectTemplateInput(template.InputSchema, sources)
		if !selected {
			continue
		}
		catalog, err := presentationpkg.NewCatalog([]presentationpkg.Template{template})
		if err != nil {
			return nil, err
		}
		resolver := presentationpkg.NewResolver(catalog, actionPolicy, nil)
		document, err := resolver.Resolve(
			ctx,
			manifest.SkillID,
			presentationpkg.Selection{
				TemplateRef: presentationpkg.TemplateRef(template),
				Data:        data,
			},
			presentationSurfaceCapabilities(request.SurfaceCapabilities),
			1,
		)
		if err != nil {
			return nil, err
		}
		if strings.TrimSpace(fallbackMarkdown) != "" {
			document.FallbackMarkdown = fallbackMarkdown
			document.FallbackPlainText = fallbackMarkdown
		}
		if !document.UseFallback {
			return presentationDocumentMap(document)
		}
		if fallback == nil {
			copy := document
			fallback = &copy
		}
	}
	if fallback != nil {
		return presentationDocumentMap(*fallback)
	}
	if preferredTemplateID != "" {
		return nil, fmt.Errorf(
			"typed tool confirmation template %q is not allowed by Skill %q",
			preferredTemplateID,
			manifest.SkillID,
		)
	}
	return nil, nil
}

func (e *DurableRunExecutor) executionPresentationContextSources(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	manifest skillpkg.Manifest,
) ([]map[string]any, error) {
	if e.loop.SkillContexts == nil || len(manifest.ContextProfile.Requirements) == 0 {
		return nil, nil
	}
	profile, err := canonicalSkillContextProfile(manifest.ContextProfile)
	if err != nil {
		return nil, err
	}
	visibility := skillcontext.DeliveryPersonal
	pageType := strings.ToLower(executionString(request.ContextSnapshot, "pageType"))
	if strings.Contains(pageType, "conversation") || strings.Contains(pageType, "circle") ||
		strings.Contains(pageType, "group") {
		visibility = skillcontext.DeliveryShared
	}
	snapshot, err := e.loop.SkillContexts.Assemble(ctx, profile, skillcontext.AssembleRequest{
		RunID: request.RunID, OwnerID: request.UserID, SkillID: manifest.SkillID,
		Visibility:         visibility,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	})
	if err != nil {
		return nil, nil
	}
	sources := make([]map[string]any, 0, len(snapshot.Segments))
	for _, segment := range snapshot.Segments {
		if len(segment.Value) > 0 {
			sources = append(sources, cloneObject(segment.Value))
		}
	}
	return sources, nil
}

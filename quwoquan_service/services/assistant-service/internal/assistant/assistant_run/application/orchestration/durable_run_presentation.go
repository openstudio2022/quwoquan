package orchestration

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
)

type presentationTemplateLoader interface {
	ResolvePresentationTemplate(context.Context, string, string) (json.RawMessage, bool, error)
}

// buildExecutionPresentation resolves only templates frozen in the active Skill
// package. It never synthesizes presentation nodes or actions in the AgentLoop.
func (e *DurableRunExecutor) buildExecutionPresentation(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	prepared PreparedExecution,
	answer string,
	pendingApproval map[string]any,
) (map[string]any, error) {
	if strings.TrimSpace(answer) == "" && len(pendingApproval) == 0 {
		return nil, nil
	}
	skillID := strings.TrimSpace(prepared.SkillID)
	if skillID == "" {
		return nil, fmt.Errorf("adaptive presentation has no frozen Skill")
	}
	if len(prepared.PresentationProfile.TemplateRefs) == 0 {
		return nil, nil
	}
	loader, ok := e.loop.Catalog.(presentationTemplateLoader)
	if !ok {
		return nil, fmt.Errorf("active Skill package presentation loader is unavailable")
	}
	sources := []map[string]any{{"answer": answer}}
	actionPolicy := presentationpkg.ActionPolicy(nil)
	mediaPolicy := presentationpkg.MediaPolicy(nil)
	preferredTemplateID := ""
	if len(pendingApproval) > 0 {
		confirmation, templateID, policy, err := toolConfirmationPresentation(
			pendingApproval,
		)
		if err != nil {
			return nil, err
		}
		sources = []map[string]any{confirmation}
		preferredTemplateID = templateID
		actionPolicy = policy
	} else {
		sources = append(
			executionPresentationContextSources(prepared.ContextSnapshot),
			sources...,
		)
		grounding := newGroundedPresentationPolicy(
			prepared.ContextSnapshot,
			presentationSurfaceCapabilities(request.SurfaceCapabilities),
		)
		actionPolicy = grounding
		mediaPolicy = grounding
	}
	var fallback *presentationpkg.Document
	candidates := make([]resolvedPresentationCandidate, 0, len(prepared.PresentationProfile.TemplateRefs))
	dataPolicies := presentationpkg.NewOfficialNodeDataPolicies()
	capabilities := presentationSurfaceCapabilities(request.SurfaceCapabilities)
	for _, templateID := range prepared.PresentationProfile.TemplateRefs {
		if preferredTemplateID != "" && templateID != preferredTemplateID {
			continue
		}
		raw, found, err := loader.ResolvePresentationTemplate(
			ctx, templateID, skillID,
		)
		if err != nil {
			return nil, fmt.Errorf(
				"resolve adaptive presentation template %q: %w",
				templateID,
				err,
			)
		}
		if !found {
			return nil, fmt.Errorf("active presentation template %q is unavailable", templateID)
		}
		template, err := presentationpkg.DecodeTemplate(raw)
		if err != nil {
			return nil, fmt.Errorf(
				"decode adaptive presentation template %q: %w",
				templateID,
				err,
			)
		}
		data, selected := selectTemplateInput(template.InputSchema, sources)
		if !selected {
			continue
		}
		catalog, err := presentationpkg.NewCatalog([]presentationpkg.Template{template})
		if err != nil {
			return nil, fmt.Errorf(
				"validate adaptive presentation template %q: %w",
				templateID,
				err,
			)
		}
		resolver := presentationpkg.NewResolver(
			catalog,
			actionPolicy,
			mediaPolicy,
			dataPolicies,
		)
		document, err := resolver.Resolve(
			ctx,
			skillID,
			presentationpkg.Selection{
				TemplateRef: presentationpkg.TemplateRef(template),
				Data:        data,
			},
			capabilities,
			1,
		)
		if err != nil {
			return nil, fmt.Errorf(
				"resolve adaptive presentation document %q: %w",
				templateID,
				err,
			)
		}
		if !document.UseFallback {
			candidates = append(candidates, resolvedPresentationCandidate{
				CandidateID: document.TemplateRef,
				Template:    template,
				Data:        data,
				Document:    document,
			})
			continue
		}
		if fallback == nil {
			copy := document
			fallback = &copy
		}
	}
	if len(candidates) > 0 {
		selected := deterministicPresentationCandidate(candidates)
		selectionOutcome := "single_candidate"
		if preferredTemplateID == "" && len(candidates) > 1 {
			modelSelected, selectedByModel, err := e.selectPresentationCandidate(
				ctx,
				request,
				prepared,
				candidates,
				capabilities,
			)
			if err != nil {
				return nil, err
			}
			if selectedByModel {
				selected = modelSelected
				selectionOutcome = "model_selected"
			} else {
				selectionOutcome = "safe_fallback"
			}
		} else if preferredTemplateID != "" {
			selectionOutcome = "typed_confirmation"
		}
		observeAdaptivePresentationSelection(selectionOutcome)
		return presentationDocumentMap(selected.Document)
	}
	if fallback != nil {
		return presentationDocumentMap(*fallback)
	}
	if preferredTemplateID != "" {
		return nil, fmt.Errorf(
			"typed tool confirmation template %q is not allowed by Skill %q",
			preferredTemplateID,
			skillID,
		)
	}
	return nil, fmt.Errorf(
		"adaptive presentation profile %q has no template compatible with its structured input",
		prepared.PresentationProfile.ProfileID,
	)
}

func executionPresentationContextSources(
	snapshot *skillcontext.Snapshot,
) []map[string]any {
	if snapshot == nil {
		return nil
	}
	sources := make([]map[string]any, 0, len(snapshot.Segments))
	for _, segment := range snapshot.Segments {
		if len(segment.Value) > 0 {
			sources = append(sources, cloneObject(segment.Value))
		}
	}
	return sources
}

func (e *DurableRunExecutor) prepareDeviceCompletionPresentation(
	ctx context.Context,
	request runruntime.ExecutionRequest,
) (PreparedExecution, error) {
	skillID := strings.TrimSpace(request.RequestedSkillID)
	if skillID == "" {
		return PreparedExecution{}, nil
	}
	manifest, found, err := e.loop.resolveSkillManifest(ctx, skillID)
	if err != nil {
		return PreparedExecution{}, fmt.Errorf(
			"load device completion presentation Skill: %w",
			err,
		)
	}
	if !found {
		return PreparedExecution{}, fmt.Errorf(
			"device completion Skill %q is absent from the frozen package",
			skillID,
		)
	}
	return PreparedExecution{
		SkillID:             skillID,
		PresentationProfile: freezePresentationProfile(manifest.Presentation),
	}, nil
}

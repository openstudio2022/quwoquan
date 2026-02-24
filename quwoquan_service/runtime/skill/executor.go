package skill

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	rctx "quwoquan_service/runtime/context"
)

var (
	ErrSkillNotFound    = errors.New("skill not found")
	ErrConsentRequired  = errors.New("user consent required")
	ErrDataClassDenied  = errors.New("data class exceeds skill's maximum")
	ErrSkillTimeout     = errors.New("skill execution timed out")
)

// ConsentStore persists user consent decisions.
type ConsentStore interface {
	HasConsent(ctx context.Context, userID, skillID string) (bool, error)
	GrantConsent(ctx context.Context, record ConsentRecord) error
	RevokeConsent(ctx context.Context, userID, skillID string) error
}

// Executor orchestrates skill execution with context injection and authorization.
type Executor struct {
	router   *Router
	consents ConsentStore
	tools    *ToolRegistry
	assembler *rctx.ContextAssembler
	timeout  time.Duration
}

func NewExecutor(
	router *Router,
	consents ConsentStore,
	tools *ToolRegistry,
	assembler *rctx.ContextAssembler,
) *Executor {
	return &Executor{
		router:    router,
		consents:  consents,
		tools:     tools,
		assembler: assembler,
		timeout:   10 * time.Second,
	}
}

// Execute runs a specific skill with full authorization and context injection.
func (e *Executor) Execute(ctx context.Context, skillID, userID, sessionID string, params map[string]any) (SkillOutput, error) {
	sk := e.findSkill(skillID)
	if sk == nil {
		return SkillOutput{}, ErrSkillNotFound
	}

	manifest := sk.Manifest()

	// Consent check
	if manifest.RequiresConsent && e.consents != nil {
		granted, err := e.consents.HasConsent(ctx, userID, skillID)
		if err != nil {
			return SkillOutput{}, fmt.Errorf("check consent: %w", err)
		}
		if !granted {
			return SkillOutput{}, ErrConsentRequired
		}
	}

	// Assemble context (trimmed per skill's ContextRequirements)
	input, err := e.buildInput(ctx, manifest, userID, sessionID, params)
	if err != nil {
		return SkillOutput{}, fmt.Errorf("build input: %w", err)
	}

	// Create guarded tool proxy
	if e.tools != nil {
		input.Tools = &guardedToolProxy{
			registry:     e.tools,
			dataClassMax: manifest.DataClassMax,
			pageType:     input.pageType(),
		}
	}

	// Execute with timeout
	execCtx, cancel := context.WithTimeout(ctx, e.timeout)
	defer cancel()

	resultCh := make(chan SkillOutput, 1)
	errCh := make(chan error, 1)

	go func() {
		out, err := sk.Execute(execCtx, input)
		if err != nil {
			errCh <- err
		} else {
			resultCh <- out
		}
	}()

	select {
	case out := <-resultCh:
		slog.Info("skill executed", "skill", skillID, "user", userID)
		return out, nil
	case err := <-errCh:
		return SkillOutput{}, err
	case <-execCtx.Done():
		return SkillOutput{}, ErrSkillTimeout
	}
}

// ExecuteMatched runs the highest-priority matched skill for the current context.
func (e *Executor) ExecuteMatched(ctx context.Context, userID, sessionID string, params map[string]any) (SkillOutput, error) {
	assistCtx, err := e.assembler.Assemble(ctx, userID, sessionID)
	if err != nil {
		return SkillOutput{}, err
	}
	if assistCtx.PageContext == nil {
		return SkillOutput{}, errors.New("no page context available")
	}

	matched := e.router.Match(assistCtx.PageContext)
	if len(matched) == 0 {
		return SkillOutput{}, ErrSkillNotFound
	}

	return e.Execute(ctx, matched[0].Manifest().ID, userID, sessionID, params)
}

func (e *Executor) findSkill(id string) Skill {
	for _, s := range e.router.RegisteredSkills() {
		if s.Manifest().ID == id {
			return s
		}
	}
	return nil
}

func (e *Executor) buildInput(ctx context.Context, manifest SkillManifest, userID, sessionID string, params map[string]any) (SkillInput, error) {
	input := SkillInput{
		UserID:     userID,
		SessionID:  sessionID,
		Parameters: params,
	}

	if e.assembler == nil {
		return input, nil
	}

	ac, err := e.assembler.Assemble(ctx, userID, sessionID)
	if err != nil {
		return input, err
	}

	if manifest.ContextRequirements.Page && ac.PageContext != nil {
		input.PageContext = ac.PageContext
	}
	if manifest.ContextRequirements.Session && ac.SessionSignals != nil {
		input.SessionCtx = ac.SessionSignals
	}
	if manifest.ContextRequirements.Profile && ac.HolisticProfile != nil {
		input.ProfileCtx = ac.HolisticProfile
	}

	return input, nil
}

func (si SkillInput) pageType() string {
	if si.PageContext != nil {
		return string(si.PageContext.PageType)
	}
	return ""
}

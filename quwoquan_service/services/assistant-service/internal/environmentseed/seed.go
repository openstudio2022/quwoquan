package environmentseed

import (
	"context"
	"fmt"
	"strings"

	"quwoquan_service/runtime/contractfixture"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

const defaultScenarioFixtureName = "assistant/test_fixtures/scenarios/assistant_scenarios.json"

type AppSeedManifest struct {
	Environment string               `json:"environment"`
	SeedRefs    []AppSeedDomainEntry `json:"seedRefs"`
}

type AppSeedDomainEntry struct {
	Domain      string   `json:"domain"`
	FixturePath string   `json:"fixturePath"`
	Refs        []string `json:"refs"`
	TargetStore string   `json:"targetStore"`
}

type AssistantScenarioPack struct {
	SchemaVersion          string                      `json:"schemaVersion"`
	RepositoryExpectations map[string]string           `json:"repositoryExpectations"`
	SeedSets               map[string]AssistantSeedSet `json:"seedSets"`
	Scenarios              []AssistantScenarioFixture  `json:"scenarios"`
}

type AssistantSeedSet struct {
	Users         []AssistantSeedUser         `json:"users"`
	Subscriptions []AssistantSeedSubscription `json:"subscriptions"`
}

type AssistantSeedUser struct {
	UserID string `json:"userId"`
}

type AssistantSeedSubscription struct {
	SubscriptionID string `json:"subscriptionId"`
	UserID         string `json:"userId"`
	SkillID        string `json:"skillId"`
	DomainID       string `json:"domainId"`
	Status         string `json:"status"`
}

type AssistantScenarioFixture struct {
	ID                      string                                  `json:"id"`
	Title                   string                                  `json:"title"`
	Type                    string                                  `json:"type"`
	SkillID                 string                                  `json:"skillId"`
	DomainID                string                                  `json:"domainId"`
	Question                string                                  `json:"question"`
	SeedRefs                []string                                `json:"seedRefs"`
	ExpectedAnswerFragments []string                                `json:"expectedAnswerFragments"`
	ExpectedEvents          []string                                `json:"expectedEvents"`
	AlphaMockStream         AssistantScenarioAlphaMockStream        `json:"alphaMockStream"`
	RemoteExpectations      AssistantScenarioRemoteExpectations     `json:"remoteExpectations"`
	Environments            map[string]AssistantScenarioEnvironment `json:"environments"`
}

type AssistantScenarioAlphaMockStream struct {
	FinalAnswer string `json:"finalAnswer"`
	ToolName    string `json:"toolName"`
	ToolSummary string `json:"toolSummary"`
}

type AssistantScenarioRemoteExpectations struct {
	AnswerFragments []string `json:"answerFragments"`
	EventTypes      []string `json:"eventTypes"`
}

type AssistantScenarioEnvironment struct {
	Enabled           bool   `json:"enabled"`
	Repository        string `json:"repository"`
	RequiresSeedReset bool   `json:"requiresSeedReset"`
}

type Plan struct {
	Environment string
	Manifest    string
	FixturePath string
	TargetStore string
	Refs        []string
	Pack        AssistantScenarioPack
}

type Result struct {
	Environment     string   `json:"environment"`
	FixturePath     string   `json:"fixturePath"`
	TargetStore     string   `json:"targetStore"`
	Refs            []string `json:"refs"`
	AppliedCount    int      `json:"appliedCount"`
	SubscriptionIDs []string `json:"subscriptionIds"`
	UserIDs         []string `json:"userIds"`
}

type SkillSubscriptionWriter interface {
	UpsertSkillSubscription(context.Context, string, assistant.UpsertSkillSubscriptionInput) (assistant.SkillSubscription, error)
}

func LoadPlan(environment string, refsOverride []string) (Plan, error) {
	environment = strings.TrimSpace(environment)
	if environment != "beta" && environment != "gamma" {
		return Plan{}, fmt.Errorf("assistant environment seed only supports beta|gamma, got %q", environment)
	}
	manifestPath := fmt.Sprintf("_shared/test_fixtures/app_%s_seed_manifest.json", environment)
	manifest, err := contractfixture.LoadMetadataJSON[AppSeedManifest](manifestPath)
	if err != nil {
		return Plan{}, fmt.Errorf("load assistant seed manifest %s: %w", manifestPath, err)
	}
	if manifest.Environment != environment {
		return Plan{}, fmt.Errorf("assistant seed manifest environment=%q, want %q", manifest.Environment, environment)
	}
	var entry *AppSeedDomainEntry
	for i := range manifest.SeedRefs {
		if strings.TrimSpace(manifest.SeedRefs[i].Domain) == "assistant" {
			entry = &manifest.SeedRefs[i]
			break
		}
	}
	if entry == nil {
		return Plan{}, fmt.Errorf("assistant seed manifest %s has no assistant domain entry", manifestPath)
	}
	targetStore := strings.ToLower(strings.TrimSpace(entry.TargetStore))
	if !strings.Contains(targetStore, "mongodb") || !strings.Contains(targetStore, "redis") {
		return Plan{}, fmt.Errorf("assistant seed targetStore must declare real mongodb+redis adapters, got %q", entry.TargetStore)
	}
	manifestRefs := compactStrings(entry.Refs)
	refs := compactStrings(refsOverride)
	if len(refs) == 0 {
		refs = manifestRefs
	}
	allowed := make(map[string]struct{}, len(manifestRefs))
	for _, ref := range manifestRefs {
		allowed[ref] = struct{}{}
	}
	for _, ref := range refs {
		if _, ok := allowed[ref]; !ok {
			return Plan{}, fmt.Errorf("assistant seed ref %q is not declared by %s", ref, manifestPath)
		}
	}
	pack, err := LoadAssistantScenarioPackAt(entry.FixturePath)
	if err != nil {
		return Plan{}, err
	}
	for _, ref := range refs {
		if _, ok := pack.SeedSets[ref]; !ok {
			return Plan{}, fmt.Errorf("assistant seed ref %q is absent from %s", ref, entry.FixturePath)
		}
	}
	return Plan{
		Environment: environment,
		Manifest:    manifestPath,
		FixturePath: strings.TrimSpace(entry.FixturePath),
		TargetStore: strings.TrimSpace(entry.TargetStore),
		Refs:        refs,
		Pack:        pack,
	}, nil
}

func LoadAssistantScenarioPack() (AssistantScenarioPack, error) {
	return LoadAssistantScenarioPackAt(defaultScenarioFixtureName)
}

func LoadAssistantScenarioPackAt(fixturePath string) (AssistantScenarioPack, error) {
	pack, err := contractfixture.LoadMetadataJSON[AssistantScenarioPack](strings.TrimSpace(fixturePath))
	if err != nil {
		return AssistantScenarioPack{}, fmt.Errorf("load assistant scenario fixture: %w", err)
	}
	return pack, nil
}

func Apply(ctx context.Context, writer SkillSubscriptionWriter, plan Plan) (Result, error) {
	if writer == nil {
		return Result{}, fmt.Errorf("assistant environment seed writer is nil")
	}
	result := Result{
		Environment:     plan.Environment,
		FixturePath:     plan.FixturePath,
		TargetStore:     plan.TargetStore,
		Refs:            append([]string(nil), plan.Refs...),
		SubscriptionIDs: []string{},
		UserIDs:         []string{},
	}
	userIDs := map[string]struct{}{}
	for _, ref := range plan.Refs {
		seedSet, ok := plan.Pack.SeedSets[ref]
		if !ok {
			return Result{}, fmt.Errorf("assistant seed ref %q not found", ref)
		}
		for _, fixture := range seedSet.Subscriptions {
			userID, err := subscriptionUserID(seedSet, fixture)
			if err != nil {
				return Result{}, fmt.Errorf("assistant seed ref %q subscription %q: %w", ref, fixture.SubscriptionID, err)
			}
			status := strings.TrimSpace(fixture.Status)
			if status == "" {
				status = assistant.SkillSubscriptionStatusActive
			}
			subscription, err := writer.UpsertSkillSubscription(ctx, userID, assistant.UpsertSkillSubscriptionInput{
				SubscriptionID: fixture.SubscriptionID,
				SkillID:        fixture.SkillID,
				DomainID:       fixture.DomainID,
				Status:         status,
				SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
					RawText: "environment seed: " + strings.TrimSpace(fixture.SkillID),
					Queries: []string{strings.TrimSpace(fixture.SkillID)},
				},
				Trigger: assistant.SkillSubscriptionTrigger{
					Type: "cron",
					Cron: "0 8 * * *",
				},
				Destination: assistant.SkillSubscriptionDestination{
					DestinationType: "user",
					DestinationID:   userID,
				},
			})
			if err != nil {
				return Result{}, fmt.Errorf("upsert assistant subscription %q: %w", fixture.SubscriptionID, err)
			}
			result.AppliedCount++
			result.SubscriptionIDs = append(result.SubscriptionIDs, subscription.SubscriptionID)
			userIDs[userID] = struct{}{}
		}
	}
	for userID := range userIDs {
		result.UserIDs = append(result.UserIDs, userID)
	}
	return result, nil
}

func (p AssistantScenarioPack) AssistantTurnScenariosFor(env string) []AssistantScenarioFixture {
	out := make([]AssistantScenarioFixture, 0, len(p.Scenarios))
	for _, scenario := range p.Scenarios {
		if scenario.Type == "assistant_turn" && scenario.EnabledFor(env) {
			out = append(out, scenario)
		}
	}
	return out
}

func (s AssistantScenarioFixture) EnabledFor(env string) bool {
	if s.Environments == nil {
		return false
	}
	return s.Environments[env].Enabled
}

func (s AssistantScenarioFixture) RemoteAnswerFragments() []string {
	if len(s.RemoteExpectations.AnswerFragments) > 0 {
		return s.RemoteExpectations.AnswerFragments
	}
	return s.ExpectedAnswerFragments
}

func (s AssistantScenarioFixture) RemoteEventTypes() []string {
	if len(s.RemoteExpectations.EventTypes) > 0 {
		return s.RemoteExpectations.EventTypes
	}
	return s.ExpectedEvents
}

func SeedRefsForAssistantTurnScenarios(scenarios []AssistantScenarioFixture) []string {
	refs := []string{}
	for _, scenario := range scenarios {
		refs = append(refs, scenario.SeedRefs...)
	}
	return compactStrings(refs)
}

func subscriptionUserID(seedSet AssistantSeedSet, fixture AssistantSeedSubscription) (string, error) {
	if userID := strings.TrimSpace(fixture.UserID); userID != "" {
		return userID, nil
	}
	users := compactSeedUsers(seedSet.Users)
	if len(users) != 1 {
		return "", fmt.Errorf("userId is ambiguous: subscription has no userId and seed set has %d users", len(users))
	}
	return users[0], nil
}

func compactSeedUsers(users []AssistantSeedUser) []string {
	values := make([]string, 0, len(users))
	for _, user := range users {
		values = append(values, user.UserID)
	}
	return compactStrings(values)
}

func compactStrings(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]struct{}{}
	for _, item := range items {
		item = strings.TrimSpace(item)
		if item == "" {
			continue
		}
		if _, ok := seen[item]; ok {
			continue
		}
		seen[item] = struct{}{}
		out = append(out, item)
	}
	return out
}

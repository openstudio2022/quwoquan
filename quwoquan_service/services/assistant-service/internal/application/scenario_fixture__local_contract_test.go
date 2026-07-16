package application

import (
	"strings"
	"testing"

	"quwoquan_service/runtime/contractfixture"
)

func TestAssistantScenarioFixtureContract(t *testing.T) {
	pack, err := LoadAssistantScenarioPack()
	if err != nil {
		t.Fatalf("load assistant scenario fixture: %v", err)
	}
	if strings.TrimSpace(pack.SchemaVersion) == "" {
		t.Fatal("assistant scenario fixture schemaVersion is empty")
	}
	if len(pack.SeedSets) == 0 || len(pack.Scenarios) == 0 {
		t.Fatal("assistant scenario fixture must declare seed sets and scenarios")
	}
}

const assistantScenarioFixtureRelativePath = "assistant/test_fixtures/scenarios/assistant_scenarios.json"

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
	Type                    string                                  `json:"type"`
	Question                string                                  `json:"question"`
	SkillID                 string                                  `json:"skillId"`
	DomainID                string                                  `json:"domainId"`
	RemoteExpectations      RemoteExpected                          `json:"remoteExpectations"`
	ExpectedEvents          []string                                `json:"expectedEvents"`
	ExpectedAnswerFragments []string                                `json:"expectedAnswerFragments"`
	SeedRefs                []string                                `json:"seedRefs"`
	Environments            map[string]AssistantScenarioEnvironment `json:"environments"`
}

type RemoteExpected struct {
	AnswerFragments []string `json:"answerFragments"`
	EventTypes      []string `json:"eventTypes"`
}

type AssistantScenarioEnvironment struct {
	Enabled           bool   `json:"enabled"`
	Repository        string `json:"repository"`
	RequiresSeedReset bool   `json:"requiresSeedReset"`
}

func LoadAssistantScenarioPack() (AssistantScenarioPack, error) {
	return contractfixture.LoadMetadataJSON[AssistantScenarioPack](assistantScenarioFixtureRelativePath)
}

func (p AssistantScenarioPack) AssistantTurnScenariosFor(environment string) []AssistantScenarioFixture {
	items := make([]AssistantScenarioFixture, 0, len(p.Scenarios))
	for _, scenario := range p.Scenarios {
		if scenario.Type != "assistant_turn" || !scenario.EnabledFor(environment) {
			continue
		}
		items = append(items, scenario)
	}
	return items
}

func (s AssistantScenarioFixture) EnabledFor(environment string) bool {
	if s.Environments == nil {
		return false
	}
	return s.Environments[environment].Enabled
}

func (s AssistantScenarioFixture) RemoteAnswerFragments() []string {
	if len(s.RemoteExpectations.AnswerFragments) > 0 {
		return append([]string{}, s.RemoteExpectations.AnswerFragments...)
	}
	return append([]string{}, s.ExpectedAnswerFragments...)
}

func (s AssistantScenarioFixture) RemoteEventTypes() []string {
	if len(s.RemoteExpectations.EventTypes) > 0 {
		return append([]string{}, s.RemoteExpectations.EventTypes...)
	}
	return append([]string{}, s.ExpectedEvents...)
}

func SeedRefsForAssistantTurnScenarios(scenarios []AssistantScenarioFixture) []string {
	out := []string{}
	seen := map[string]struct{}{}
	for _, scenario := range scenarios {
		for _, ref := range scenario.SeedRefs {
			ref = strings.TrimSpace(ref)
			if ref == "" {
				continue
			}
			if _, ok := seen[ref]; ok {
				continue
			}
			seen[ref] = struct{}{}
			out = append(out, ref)
		}
	}
	return out
}

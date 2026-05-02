package application

import (
	"fmt"

	"quwoquan_service/runtime/contractfixture"
)

const assistantScenarioFixtureName = "assistant/test_fixtures/scenarios/assistant_scenarios.json"

type AssistantScenarioPack struct {
	SchemaVersion          string                     `json:"schemaVersion"`
	RepositoryExpectations map[string]string          `json:"repositoryExpectations"`
	SeedSets               map[string]any             `json:"seedSets"`
	Scenarios              []AssistantScenarioFixture `json:"scenarios"`
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

func LoadAssistantScenarioPack() (AssistantScenarioPack, error) {
	pack, err := contractfixture.LoadMetadataJSON[AssistantScenarioPack](assistantScenarioFixtureName)
	if err != nil {
		return AssistantScenarioPack{}, fmt.Errorf("load assistant scenario fixture: %w", err)
	}
	return pack, nil
}

func (p AssistantScenarioPack) AssistantTurnScenariosFor(env string) []AssistantScenarioFixture {
	out := make([]AssistantScenarioFixture, 0, len(p.Scenarios))
	for _, scenario := range p.Scenarios {
		if scenario.Type != "assistant_turn" {
			continue
		}
		if !scenario.EnabledFor(env) {
			continue
		}
		out = append(out, scenario)
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

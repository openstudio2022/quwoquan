package model

import "strings"

type Chip struct {
	ChipID     string `json:"chipId" bson:"chipId"`
	Label      string `json:"label" bson:"label"`
	ActionType string `json:"actionType" bson:"actionType"`
	Value      string `json:"value,omitempty" bson:"value,omitempty"`
}

type Action struct {
	ActionID   string         `json:"actionId" bson:"actionId"`
	ActionType string         `json:"actionType" bson:"actionType"`
	Label      string         `json:"label" bson:"label"`
	Payload    map[string]any `json:"payload,omitempty" bson:"payload,omitempty"`
}

type View struct {
	AccountID       string   `json:"-" bson:"accountId"`
	WelcomeMessage  string   `json:"welcomeMessage" bson:"welcomeMessage"`
	SuggestionLines []string `json:"suggestionLines" bson:"suggestionLines"`
	Chips           []Chip   `json:"chips" bson:"chips"`
	Actions         []Action `json:"actions" bson:"actions"`
	Personalized    bool     `json:"personalized" bson:"personalized"`
	Checkpoint      int64    `json:"-" bson:"checkpoint"`
}

func Empty() View {
	return View{
		WelcomeMessage:  "你好，我是小趣，可以帮你查内容、订阅提醒、整理待办。",
		SuggestionLines: []string{"想了解什么？直接问我就行"},
		Chips: []Chip{
			{ChipID: "chip.search", Label: "帮我搜索", ActionType: "open_search"},
			{ChipID: "chip.skills", Label: "看看技能", ActionType: "open_skill_center"},
			{ChipID: "chip.tasks", Label: "今日待办", ActionType: "open_tasks"},
		},
		Actions: []Action{},
	}
}

func ActionsForPage(pageType, objectID string) []Action {
	pageType = strings.TrimSpace(pageType)
	objectID = strings.TrimSpace(objectID)
	if pageType == "" {
		return []Action{}
	}
	payload := map[string]any{"pageType": pageType}
	if objectID != "" {
		payload["objectId"] = objectID
	}
	actions := []Action{{
		ActionID: "assistant.ask_followup", ActionType: "open_assistant",
		Label: "继续追问小趣", Payload: payload,
	}}
	pageAction := map[string]Action{
		"home":      {ActionID: "assistant.explore_home", ActionType: "explore", Label: "看看今日推荐"},
		"discovery": {ActionID: "assistant.find_similar_content", ActionType: "find_similar", Label: "发现相似内容"},
		"circles":   {ActionID: "assistant.summarize_circle_discussion", ActionType: "summarize_discussion", Label: "总结圈内讨论"},
		"article":   {ActionID: "assistant.summarize_article", ActionType: "summarize", Label: "总结这篇内容"},
		"profile":   {ActionID: "assistant.explain_profile", ActionType: "explain_profile", Label: "了解此主页"},
		"chat":      {ActionID: "assistant.summarize_conversation", ActionType: "summarize_conversation", Label: "总结当前对话"},
		"create":    {ActionID: "assistant.help_create", ActionType: "creation_assistance", Label: "帮我完善创作"},
		"search":    {ActionID: "assistant.refine_search", ActionType: "refine_search", Label: "优化搜索问题"},
	}[pageType]
	if pageAction.ActionID != "" {
		pageAction.Payload = payload
		actions = append(actions, pageAction)
	}
	return actions
}

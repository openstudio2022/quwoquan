package model

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
		SuggestionLines: []string{},
		Chips:           []Chip{},
		Actions:         []Action{},
	}
}

package model

// FullSnapshot is a joined view returned by GetUserProfile.
// It aggregates profile + active persona + user settings.
type FullSnapshot struct {
	Profile       *UserProfile `json:"profile"`
	ActivePersona *Persona     `json:"activePersona,omitempty"`
	Settings      *UserSetting `json:"settings,omitempty"`
}

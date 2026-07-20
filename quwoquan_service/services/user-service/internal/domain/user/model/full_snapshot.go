package model

// FullSnapshot is a joined view returned by GetUserProfile.
// Public profile reads must never include account-private UserSettings.
type FullSnapshot struct {
	Profile       *UserProfile `json:"profile"`
	ActivePersona *Persona     `json:"activePersona,omitempty"`
}

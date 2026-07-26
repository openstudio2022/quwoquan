package model

// ProfileSnapshot is the closed Persona state needed to audit and safely
// reverse a ProfileUpdateProposal. It is never accepted from a public request.
type ProfileSnapshot struct {
	DisplayName            string `json:"displayName"`
	Bio                    string `json:"bio"`
	AvatarMediaAssetID     string `json:"avatarMediaAssetId"`
	AvatarURL              string `json:"avatarUrl"`
	BackgroundMediaAssetID string `json:"backgroundMediaAssetId"`
	BackgroundURL          string `json:"backgroundUrl"`
	IsPrivate              bool   `json:"isPrivate"`
	IsolationLevel         string `json:"isolationLevel"`
	PurposeHint            string `json:"purposeHint"`
	Version                int64  `json:"version"`
}

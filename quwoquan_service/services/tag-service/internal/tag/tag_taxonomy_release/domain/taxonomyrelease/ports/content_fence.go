package ports

import (
	"context"
	"time"
)

// ContentFence 对应 Content Post 的 ContentActiveReleaseFence 只读契约；revision 只标识 pointer 世代。
type ContentFence struct {
	Found             bool       `json:"found"`
	Environment       string     `json:"environment"`
	SourceOwner       string     `json:"sourceOwner"`
	ReleaseID         string     `json:"releaseId"`
	ManifestDigest    string     `json:"manifestDigest"`
	Revision          int64      `json:"revision"`
	ProjectionVersion int64      `json:"projectionVersion"`
	ActivatedAt       *time.Time `json:"activatedAt"`
}

type ContentFenceReader interface {
	ReadActiveContentFence(context.Context) (ContentFence, error)
}

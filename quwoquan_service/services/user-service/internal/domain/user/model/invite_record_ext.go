package model

import "time"

// IsExpired reports whether the invite has passed its expiry time.
func (r *InviteRecord) IsExpired() bool {
	return time.Now().After(r.ExpireAt)
}

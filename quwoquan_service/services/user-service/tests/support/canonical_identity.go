package support

import useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"

// NewCanonicalOwnerID lets cross-service integration tests obtain a real User
// identity without copying the UserAccount identity grammar or routing hash.
func NewCanonicalOwnerID(originCode, entropy string) (string, error) {
	ownerID, err := useridentity.NewOwnerID(originCode, entropy)
	if err != nil {
		return "", err
	}
	return ownerID.String(), nil
}

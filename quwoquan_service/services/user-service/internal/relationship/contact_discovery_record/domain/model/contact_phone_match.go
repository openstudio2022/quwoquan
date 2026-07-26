package model

// ContactPhoneMatch is a transient (non-persisted) enrichment row for contact
// discovery: a registered, non-strict persona whose active phone/carrier_phone
// credential hash matched one of the initiator's uploaded hashes.
//
// HashedPhone echoes the initiator's own uploaded hash so the client can map a
// match back to the local address-book display name. It never carries another
// user's phone number in plaintext, nor any ownerAccountId.
type ContactPhoneMatch struct {
	HashedPhone   string
	SubAccountID  string
	UserHandle    string
	DisplayName   string
	AvatarURL     string
	AvatarVersion int
	Region        string
}

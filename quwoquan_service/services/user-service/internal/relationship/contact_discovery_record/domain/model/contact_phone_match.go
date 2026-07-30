package model

// ContactPhoneMatch is a transient (non-persisted) enrichment row for contact
// discovery: a registered account whose active phone/carrier_phone
// CredentialBinding matched one of the initiator's uploaded hashes, projected
// onto one of that account's non-strict active Personas.
//
// HashedPhone echoes the initiator's own uploaded hash so the client can map a
// match back to the local address-book display name. It never carries another
// user's phone number in plaintext, nor any ownerAccountId.
type ContactPhoneMatch struct {
	HashedPhone   string
	PersonaID     string
	UserHandle    string
	DisplayName   string
	AvatarURL     string
	AvatarVersion int
	Region        string
}

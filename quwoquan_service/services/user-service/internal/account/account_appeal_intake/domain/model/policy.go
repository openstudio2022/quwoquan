package model

import "time"

const (
	CredentialTTL            = 10 * time.Minute
	CredentialAuditRetention = 24 * time.Hour
	IntakeRetention          = 180 * 24 * time.Hour
	CredentialIssueWindow    = time.Hour
	CredentialIssueLimit     = 3
)

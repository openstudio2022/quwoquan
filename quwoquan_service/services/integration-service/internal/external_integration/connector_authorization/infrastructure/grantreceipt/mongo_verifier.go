package grantreceipt

import (
	"context"
	"errors"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	authorizationmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type MongoVerifier struct {
	receipts *mongo.Collection
	now      func() time.Time
}

func NewMongoVerifier(database *mongo.Database, now func() time.Time) *MongoVerifier {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	if database == nil {
		return &MongoVerifier{now: now}
	}
	return &MongoVerifier{
		receipts: database.Collection("connector_authorization_grant_receipts"),
		now:      now,
	}
}

func (verifier *MongoVerifier) Verify(
	ctx context.Context,
	accountID string,
	definition definitionmodel.Definition,
	receiptRef string,
	requestedCapabilities []string,
) (connectionmodel.VerifiedGrant, error) {
	if verifier == nil || verifier.receipts == nil {
		return connectionmodel.VerifiedGrant{}, connectionmodel.ErrGrantReceiptInvalid
	}
	accountID = strings.TrimSpace(accountID)
	receiptRef = strings.TrimSpace(receiptRef)
	if accountID == "" || receiptRef == "" {
		return connectionmodel.VerifiedGrant{}, connectionmodel.ErrGrantReceiptInvalid
	}
	var document authorizationmodel.GrantReceipt
	err := verifier.receipts.FindOne(ctx, bson.M{
		"grantReceiptDigest": authorizationmodel.Hash(receiptRef),
		"accountId":          accountID,
		"connectorId":        definition.ConnectorID,
		"consumedAt":         bson.M{"$exists": false},
		"expiresAt":          bson.M{"$gt": verifier.now().UTC()},
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) || err != nil {
		return connectionmodel.VerifiedGrant{}, connectionmodel.ErrGrantReceiptInvalid
	}
	requested := canonical(requestedCapabilities)
	granted := canonical(document.GrantedCapabilities)
	if len(requested) != len(granted) || strings.TrimSpace(document.CredentialRef) == "" {
		return connectionmodel.VerifiedGrant{}, connectionmodel.ErrGrantReceiptInvalid
	}
	for index := range requested {
		if requested[index] != granted[index] || !definition.Grants(requested[index]) {
			return connectionmodel.VerifiedGrant{}, connectionmodel.ErrGrantReceiptInvalid
		}
	}
	return connectionmodel.VerifiedGrant{
		AuthorizationID:     document.AuthorizationID,
		CredentialRef:       document.CredentialRef,
		ReceiptDigest:       document.GrantReceiptDigest,
		GrantedCapabilities: granted,
		ExpiresAt:           document.CredentialExpiresAt,
	}, nil
}

func canonical(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

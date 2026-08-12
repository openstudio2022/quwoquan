// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-snapshot-versioning/spec.md
package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestUserProfileSearchProjectionIsDurableAndSearchOwned(t *testing.T) {
	root := userServiceRoot(t)
	raw, err := os.ReadFile(filepath.Join(root, "contracts/account/user_account/events.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var events struct {
		Events []struct {
			Name              string   `yaml:"name"`
			DeliverySemantics string   `yaml:"delivery_semantics"`
			WireEventType     string   `yaml:"wire_event_type"`
			Topic             string   `yaml:"topic"`
			PayloadEntity     string   `yaml:"payload_entity"`
			PayloadFields     []string `yaml:"payload_fields"`
		} `yaml:"events"`
	}
	if err := yaml.Unmarshal(raw, &events); err != nil {
		t.Fatal(err)
	}
	for _, event := range events.Events {
		if event.Name != "UserProfileSearchProjectionRequested" {
			continue
		}
		if event.DeliverySemantics != "transactional_outbox" ||
			event.WireEventType != "UserProfileSearchProjectionRequested" ||
			event.Topic != "events.user.profile_search" ||
			event.PayloadEntity != "UserProfileSearchProjectionEvent" {
			t.Fatalf("durable profile search event binding drifted: %+v", event)
		}
		wantFields := map[string]bool{
			"eventId": true, "userId": true, "profileVersion": true,
			"operation": true, "nickname": true, "avatarUrl": true,
			"bio": true, "identityTags": true, "followerCount": true,
			"postCount": true, "updatedAt": true,
		}
		for _, field := range event.PayloadFields {
			delete(wantFields, field)
		}
		if len(wantFields) != 0 {
			t.Fatalf("profile search event is not self-contained; missing=%v", wantFields)
		}
		return
	}
	t.Fatal("UserProfileSearchProjectionRequested event is not declared")
}

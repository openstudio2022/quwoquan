package persistence

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_membership/domain/model"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// 直接走现役ChangeSet和事务调用的mapper，不复制或伪造producer JSON。
func TestMembershipProducerSixEventsMatchOwningDTO(t *testing.T) {
	now := time.Date(2026, 9, 13, 0, 0, 0, 0, time.UTC)
	change := model.ChangeSet{Kind: model.ChangeJoin, MembershipID: "membership", CircleID: "circle", PersonaID: "persona", Role: model.CircleMemberRoleMember, OccurredAt: now}
	type fact struct {
		Event   string          `json:"event"`
		Payload json.RawMessage `json:"payload"`
	}
	facts := []fact{}
	appendFact := func(value model.CircleMembership, event string) {
		t.Helper()
		for _, owner := range []string{"", "owner"} {
			raw, err := json.Marshal(membershipEventPayload(value, owner))
			if err != nil {
				t.Fatal(err)
			}
			var wire map[string]any
			if err = json.Unmarshal(raw, &wire); err != nil {
				t.Fatal(err)
			}
			if wire["id"] != value.ID || wire["version"] != float64(value.Version) {
				t.Fatal("identity changed")
			}
			if value.JoinedAt.IsZero() && wire["joinedAt"] != nil {
				t.Fatalf("never joined must serialize null, got %v", wire["joinedAt"])
			}
			if _, exists := wire["circleOwnerPersonaId"]; exists != (owner != "") {
				t.Fatal("owner optionality changed")
			}
			if _, exists := wire["leftAt"]; exists != (!value.LeftAt.IsZero()) {
				t.Fatal("leftAt optionality changed")
			}
			facts = append(facts, fact{event, raw})
		}
	}
	apply := func(c model.ChangeSet, current *model.CircleMembership) model.CircleMembership {
		t.Helper()
		value, event, err := c.Apply(current)
		if err != nil {
			t.Fatal(err)
		}
		appendFact(value, event)
		return value
	}
	active := apply(change, nil)
	pendingChange := change
	pendingChange.Pending = true
	pending := apply(pendingChange, nil)
	for _, kind := range []model.ChangeKind{model.ChangeApprove, model.ChangeReject} {
		c := change
		c.Kind = kind
		c.ExpectedVersion = pending.Version
		c.OccurredAt = now.Add(time.Hour)
		apply(c, &pending)
	}
	for _, kind := range []model.ChangeKind{model.ChangeLeave, model.ChangeRole} {
		c := change
		c.Kind = kind
		c.ExpectedVersion = active.Version
		c.OccurredAt = now.Add(2 * time.Hour)
		if kind == model.ChangeRole {
			c.Role = model.CircleMemberRoleAdmin
		}
		apply(c, &active)
	}
	root, err := filepath.Abs(filepath.Join("..", "..", "..", "..", "..", "..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	python := os.Getenv("QWQ_PAYLOAD_TEST_PYTHON")
	if python == "" {
		t.Skip("explicit managed Python required for generated DTO decode")
	}
	raw, _ := json.Marshal(facts)
	script := `import json,sys,importlib.util
from pathlib import Path
from pydantic import ValidationError
root=Path(sys.argv[1])/"services/recommendation-service/generated/recommendation/recommendation_feature_profile_view/events"
facts=json.loads(sys.argv[2]);seen=set()
for fact in facts:
 name=fact["event"];seen.add(name);path=root/("circle_circle_membership_"+name+".py")
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
 cls=module.CircleMembershipLifecyclePayload;assert len(cls.model_fields)==11
 obj=cls.model_validate(fact["payload"]);assert obj.id=="membership" and obj.version==fact["payload"]["version"]
 if name in ("CircleMembershipRequested","CircleMembershipRejected"):assert obj.joinedAt is None
 if name=="CircleMembershipLeft":assert obj.leftAt is not None
 for field in ("leftAt","circleOwnerPersonaId"):
  cls.model_validate({**fact["payload"],field:None})
 for bad in ({**fact["payload"],"unexpected":1},{**fact["payload"],"joinedAt":""},{k:v for k,v in fact["payload"].items() if k!="id"}):
  try:cls.model_validate(bad)
  except ValidationError:pass
  else:raise AssertionError("invalid owning payload accepted")
assert len(seen)==6
print("SIX_REAL_PRODUCER_EVENTS_12_OPTIONAL_VARIANTS_PASS")`
	command := exec.Command(python, "-B", "-c", script, root, string(raw))
	command.Env = append(os.Environ(), "PYTHONDONTWRITEBYTECODE=1")
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("actual producer to owning DTO: %v\n%s", err, output)
	} else {
		t.Log(string(output))
	}
}

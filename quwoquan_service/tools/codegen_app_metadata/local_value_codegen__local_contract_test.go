package main

import (
	"gopkg.in/yaml.v3"
	"os"
	"os/exec"
	"path/filepath"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-013
func TestClientValuesExecuteStrictDartDecoder(t *testing.T) {
	dir := t.TempDir()
	for _, owner := range []string{"authentication_challenge", "account_session"} {
		source := "../../services/user-service/contracts/account/" + owner + "/fields.yaml"
		raw, err := os.ReadFile(source)
		if err != nil {
			t.Fatal(err)
		}
		var doc fieldsFile
		if err := yaml.Unmarshal(raw, &doc); err != nil {
			t.Fatal(err)
		}
		text, err := renderClientValues(source, doc)
		if err != nil {
			t.Fatal(err)
		}
		if strings.Contains(text, "SendOtpCommand") || strings.Contains(text, "LoginWithPhoneCommand") {
			t.Fatal("non-exported HTTP root leaked")
		}
		if err := os.WriteFile(filepath.Join(dir, owner+".dart"), []byte(text), 0600); err != nil {
			t.Fatal(err)
		}
	}
	script := `import 'authentication_challenge.dart';
import 'account_session.dart';
void reject(void Function() f) { try { f(); } catch (_) { return; } throw StateError('invalid accepted'); }
void main() {
 final id='alpha-synthetic:'+('a'*32);
 final value=SyntheticIdentityLabel.fromWire({'value':id});
 BeginSyntheticChallenge.fromWire({'identity':value.toWire(),'requestKey':'b'*32});
 SyntheticChallengeView.fromWire({'challengeId':'alpha-challenge:'+('a'*32),'confirmationHint':'alpha-rehearsal-confirm','expiresInSeconds':300});
 SyntheticLoginEvidence.fromWire({'identityLabel':id,'confirmationHint':'alpha-rehearsal-confirm'});
 CompleteSyntheticChallenge.fromWire({'identityLabel':id,'challengeId':'alpha-challenge:'+('a'*32),'confirmationHint':'alpha-rehearsal-confirm','requestKey':'a'*32});
 SyntheticSessionResult.fromWire({'accountId':'alpha-account:'+('a'*32),'personaId':'alpha-persona:'+('b'*32)});
 final wrong={'identityLabel':id,'challengeId':'alpha-challenge:'+('a'*32),'confirmationHint':'alpha-rehearsal-reject','requestKey':'b'*32};
 if(CompleteSyntheticChallenge.fromWire(wrong).confirmationHint!='alpha-rehearsal-reject') throw StateError('wrong input must reach port');
 for(final v in <Object?>[null,42,'123456','00000000000','synthetic.invalid','alpha-rehearsal-unknown','alpha-rehearsal-'+('a'*100),' alpha-rehearsal-reject','alpha-rehearsal-reject\n','alpha-rehearsal-ｒｅｊｅｃｔ']) {reject(()=>CompleteSyntheticChallenge.fromWire({...wrong,'confirmationHint':v}));}
 reject(()=>SyntheticLoginEvidence.fromWire({'identityLabel':id,'confirmationHint':'alpha-rehearsal-reject'}));
 reject(()=>SyntheticChallengeView.fromWire({'challengeId':wrong['challengeId'],'confirmationHint':'alpha-rehearsal-reject','expiresInSeconds':300}));
 final failure=SyntheticLoginFailure.fromWire({'reason':'expired'});
 if(failure.reason!=SyntheticLoginFailureReason.expired) throw StateError('not typed');
 for(final v in [' '+id,id+' ',id+'\n','１２３４５６', '00000000000', 'alpha-synthetic:'+('A'*32)]) {reject(()=>SyntheticIdentityLabel.fromWire({'value':v}));}
 for(final m in <Map<String,Object?>>[{}, {'value':null},{'value':42},{'value':id,'phone':'x'}]) {reject(()=>SyntheticIdentityLabel.fromWire(m));}
 reject(()=>BeginSyntheticChallenge.fromWire({'identity':{'value':id,'extra':true},'requestKey':'b'*32}));
 reject(()=>BeginSyntheticChallenge.fromWire({'identity':null,'requestKey':'b'*32}));
 reject(()=>SyntheticLoginFailure.fromWire({'reason':'unknown'}));
 reject(()=>SyntheticLoginEvidence.fromWire({'identityLabel':id,'confirmationHint':'123456'}));
 reject(()=>SyntheticChallengeView.fromWire({'challengeId':'alpha-challenge:'+('a'*32),'confirmationHint':'alpha-rehearsal-confirm','expiresInSeconds':301}));
 reject(()=>SyntheticChallengeView.fromWire({'challengeId':'alpha-challenge:'+('a'*32),'confirmationHint':'alpha-rehearsal-confirm','expiresInSeconds':0}));
 print('strict generated values PASS');
}`
	if err := os.WriteFile(filepath.Join(dir, "main.dart"), []byte(script), 0600); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command("dart", filepath.Join(dir, "main.dart"))
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("Dart decoder: %v\n%s", err, out)
	}
}

func TestClientValuesPublicExportGeneratedFromSameRoots(t *testing.T) {
	dir := t.TempDir()
	source, err := contractcodegen.NewDocumentSource("../../services/user-service/contracts", []string{"account/authentication_challenge/fields.yaml", "account/account_session/fields.yaml"})
	if err != nil {
		t.Fatal(err)
	}
	previous := activeMetadataSource
	activeMetadataSource = source
	t.Cleanup(func() { activeMetadataSource = previous })
	// 服务view路径形状由真实Source载入，测试用同源文档建立domain前缀。
	for i := range source.Graph().Documents {
		source.Graph().Documents[i].Path = "user/" + source.Graph().Documents[i].Path
	}
	if err := generateClientValues(dir); err != nil {
		t.Fatal(err)
	}
	for _, owner := range []string{"account_session", "authentication_challenge"} {
		path := filepath.Join(dir, "packages/quwoquan_cloud_contracts/lib/generated/values/user/account", owner+".values.dart")
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatalf("public export missing: %v", err)
		}
		if !strings.Contains(string(raw), "src/generated/values/user/account/"+owner+".values.g.dart") {
			t.Fatal("public export drift")
		}
	}
}

func TestClientValueExportRejectsUnboundAndCyclicTypes(t *testing.T) {
	for _, raw := range []string{
		`types: {Root: {client_value: true, fields: [{name: value, type: Missing, constraints: [NOT_NULL]}]}}`,
		`types: {Root: {client_value: true, fields: [{name: value, type: Root, constraints: [NOT_NULL]}]}}`,
		`types: {Root: {client_value: true, fields: [{name: value, type: string, pattern: partial, constraints: [NOT_NULL]}]}}`,
	} {
		var doc fieldsFile
		if err := yaml.Unmarshal([]byte(raw), &doc); err != nil {
			t.Fatal(err)
		}
		if _, err := renderClientValues("test", doc); err == nil {
			t.Fatal("invalid metadata accepted")
		}
	}
}

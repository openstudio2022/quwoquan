"""spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008"""
import hashlib
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'quwoquan_app/scripts/env'), str(ROOT / 'quwoquan_app/scripts/device'), str(ROOT / 'quwoquan_app/test/support/runtime/launcher')]
import print_app_env_dart_defines as producer
import build_launcher_handoff as handoff
from launcher_package_fixture import _issue_test_signing_material
from quwoquan_ops.cli.commands import app_preflight_uat_launch as launch
from quwoquan_ops.cli.lib.package_reuse.input_capsule import _digest_record, _baseline_id, _capsule_identity_payload, verify_package_input_capsule
from quwoquan_ops.cli.lib.app_launch_manifest_contract import build_runtime_config_trust_envelope, validate_runtime_config_package


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class IsolatedControlTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.projection = self.root / 'projection'
        self.capsule = self.root / 'capsule'
        raw = b'{"privateTestSnapshot":true}\n'
        self.snapshot = 'sha256:' + hashlib.sha256(raw).hexdigest()
        files = {'quwoquan_app/assets/content/alpha/manifest.json': raw,
                 'quwoquan_app/assets/content/alpha/bundle_identity.json': json.dumps({'manifestDigest': self.snapshot}).encode()}
        entries = []
        for path, content in files.items():
            for base, mode in ((self.capsule / 'repo', 0o444), (self.projection, 0o644)):
                dest = base / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                dest.chmod(mode)
            entries.append({'logicalPath': path, 'capsulePath': 'repo/' + path, 'kind': 'file',
                            'digest': 'sha256:' + hashlib.sha256(content).hexdigest(), 'size': len(content), 'mode': 0o444})
        source_digest, count = _digest_record([(p, 'file', v) for p, v in files.items()])
        roots = ['quwoquan_app/assets']
        self.manifest = {'schema': 'stackctl-package-input-capsule.v2', 'dependencyPlatforms': ['android', 'ios'],
            'baselineId': _baseline_id(_capsule_identity_payload(roots=roots, input_digest=source_digest, input_count=count)),
            'sourceRevision': 'b'*40, 'workspaceStatusDigest': 'sha256:'+'c'*64,
            'deploymentInputDigest': source_digest, 'deploymentInputFileCount': count,
            'deploymentInputRoots': roots, 'entries': entries}
        (self.capsule/'manifest.json').write_text(json.dumps(self.manifest))
        verify_package_input_capsule(self.capsule)
        pd, pc = launch._projection_cas(manifest=self.manifest, capsule_root=self.capsule, projection_root=self.projection, reject_unmanifested=True)
        evidence = {'schema': 'quwoquan_ops.app_content_uat_source_projection.v1', 'contentSource': 'bundled_snapshot',
            'candidateDigest': 'sha256:'+'a'*64, 'sourceRevision': self.manifest['sourceRevision'],
            'sourceCapsuleDigest': source_digest, 'sourceCapsuleWorkspaceStatusDigest': self.manifest['workspaceStatusDigest'],
            'sourceCapsuleManifestDigest': digest(self.manifest), 'sourceCapsuleManifestRef': str(self.capsule/'manifest.json'),
            'sourceProjectionRoot': str(self.projection), 'sourceProjectionDigest': pd, 'sourceProjectionFileCount': pc}
        self.evidence = self.root/'projection.json'
        self.evidence.write_text(json.dumps(evidence))
        self.control = launch.write_app_content_launch_control(
            runtime_binding={**evidence, 'environment':'alpha', 'target':'alpha-local'},
            projection={**evidence, 'sourceProjectionEvidenceRef':str(self.evidence), 'sourceProjectionEvidenceDigest':digest(evidence)},
            output_root=self.root, control_path=self.root/'attempt/control.json', attempt_path=self.root/'attempt/attempt.json',
            report_path=self.root/'attempt/report.json', terminal_receipt_path=self.root/'attempt/terminal.json',
            platform='android', device_id='emulator-private', build_projection_policy_id=launch.FLUTTER_ANDROID_3_47_GRADLE_8_14_POLICY_ID,
            build_projection_seal_path=self.root/'attempt/seal.json', expected_build_projection_digest=None,
            rehearsal_space_selection={'mode':'isolated', 'instanceId':'private-space', 'snapshotDigest':self.snapshot,
                'caseId':'login-success', 'lifecycleGeneration':'1', 'observationBinding': 'sha256:' + 'a'*64})
        self.binding = {'control_ref':self.control['controlRef'], 'control_digest':self.control['controlDigest'], 'output_root':str(self.root),
            'device_id':'emulator-private', 'candidate_digest':evidence['candidateDigest'], 'attempt_ref':self.control['launchAttemptRef'],
            'report_ref':self.control['launchReportRef'], 'capsule_ref':str(self.capsule/'manifest.json')}
        self.signing = _issue_test_signing_material(self.root/'keys')

    def build(self, binding=None, isolated=True):
        with mock.patch.object(producer, 'ROOT', self.projection):
            return producer.build_offline_bootstrap_document(environment='alpha', target='alpha-local', launch_policy='test_live',
                source_git_sha=self.manifest['sourceRevision'], source_tree_digest=self.manifest['deploymentInputDigest'],
                signing=self.signing, launch_control=self.binding if binding is None else binding, require_isolated=isolated)

    def test_real_private_signed_isolated_and_standard(self):
        for binding, isolated in ((self.binding,True), ({},False)):
            doc=self.build(binding,isolated)
            trust=build_runtime_config_trust_envelope('nonprod', json.loads(self.signing.trusted_public_keys_path.read_text()))
            self.assertEqual(validate_runtime_config_package(doc,trust),[])
            self.assertEqual(doc['rehearsalSpace']['mode'],'isolated' if isolated else 'standard')
            document_path = self.root / 'signed.json'
            document_path.write_text(json.dumps({'document': doc, 'trust': trust['trustedPublicKeys']}))
            dart = self.root / 'verify.dart'
            dart.write_text("""import 'dart:convert';
import 'dart:io';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
Future<void> main(List<String> args) async {
 final input=jsonDecode(File(args[0]).readAsStringSync()) as Map;
 final resolved=await RuntimePackageResolver().resolve(
  runtimePackage:Map<String,Object?>.from(input['document'] as Map),expectedTarget:'alpha-local',
  trustedBuildProfile:'nonprod',trustedPublicKeys:Map<String,String>.from(input['trust'] as Map),
  expectedOfflineSnapshotDigest:args[1]);
 if(resolved.rehearsalSpace!.mode!=args[2]) throw StateError('mode mismatch');
 print('real builder to resolver PASS');
}
""")
            result = subprocess.run(['dart', '--packages='+str(ROOT/'quwoquan_app/.dart_tool/package_config.json'), str(dart), str(document_path), self.snapshot, 'isolated' if isolated else 'standard'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            doc['rehearsalSpace']['instanceId']='tampered'
            self.assertTrue(validate_runtime_config_package(doc,trust))

    def test_old_control_without_selection_and_handoff_presign_gate(self):
        path=Path(self.binding['control_ref'])
        old=json.loads(path.read_text());old.pop('rehearsalSpaceSelection');path.write_text(json.dumps(old))
        binding={**self.binding,'control_digest':digest(old)}
        self.assertEqual(self.build(binding,False)['rehearsalSpace']['mode'],'standard')
        args=handoff._parser(handoff.load_launch_manifest_contract()).parse_args([
            '--env','alpha','--target','alpha-local','--launch-provenance','canonical_launcher',
            '--isolated-rehearsal','--launch-control-ref',binding['control_ref'],
            '--launch-control-digest',binding['control_digest'],'--launch-output-root',str(self.root),
            '--launch-device-id','wrong-device','--launch-candidate-digest',binding['candidate_digest'],
            '--launch-attempt-ref',binding['attempt_ref'],'--launch-report-ref',binding['report_ref'],
            '--source-capsule-manifest',binding['capsule_ref']])
        with mock.patch.object(producer,'ROOT',self.projection), mock.patch.object(handoff,'_runtime_config_trust_envelope') as trust:
            with self.assertRaises(ValueError): handoff.build_handoff(args)
            trust.assert_not_called()

    def test_binding_failures_precede_signer(self):
        for field in ('control_digest','candidate_digest','device_id','attempt_ref','capsule_ref'):
            with self.subTest(field=field), mock.patch.object(producer,'validate_signing_material') as signer:
                with self.assertRaises((ValueError,OSError)):
                    self.build({**self.binding,field:'wrong'})
                signer.assert_not_called()
        with mock.patch.object(producer,'validate_signing_material') as signer:
            with self.assertRaises(ValueError): self.build({})
            signer.assert_not_called()

    def test_wrong_snapshot_unknown_fields_and_online_rejected_before_signing(self):
        path=Path(self.binding['control_ref'])
        original=path.read_text()
        for mutation in (
            lambda d: d['rehearsalSpaceSelection'].update(snapshotDigest='sha256:'+'f'*64),
            lambda d: d['rehearsalSpaceSelection'].update(instanceId='default'),
            lambda d: d.update(authorized=True),
            lambda d: d.update(contentSource='remote'),
        ):
            doc=json.loads(original);mutation(doc);path.write_text(json.dumps(doc))
            with mock.patch.object(producer,'validate_signing_material') as signer:
                with self.assertRaises(ValueError):self.build({**self.binding,'control_digest':digest(doc)})
                signer.assert_not_called()
        path.write_text(original)
        with mock.patch.object(producer,'validate_signing_material') as signer:
            with self.assertRaises(ValueError):
                producer.build_offline_bootstrap_document(environment='beta',target='beta-local',launch_policy='test_live',source_git_sha='b'*40,source_tree_digest=self.manifest['deploymentInputDigest'],signing=self.signing,launch_control=self.binding,require_isolated=True)
            signer.assert_not_called()

    def test_self_consistent_control_cross_projection_and_missing_selection_reject(self):
        for field, value in (('candidateDigest','sha256:'+'d'*64),('sourceRevision','e'*40),('rehearsalSpaceSelection',None)):
            path=Path(self.binding['control_ref'])
            original=path.read_text()
            doc=json.loads(original)
            if value is None: doc.pop(field)
            else: doc[field]=value
            path.write_text(json.dumps(doc))
            binding={**self.binding,'control_digest':digest(doc)}
            if field=='candidateDigest': binding['candidate_digest']=value
            with mock.patch.object(producer,'validate_signing_material') as signer:
                with self.assertRaises(ValueError): self.build(binding)
                signer.assert_not_called()
            path.write_text(original)

if __name__=='__main__': unittest.main()

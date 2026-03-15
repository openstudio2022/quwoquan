import 'package:quwoquan_app/assistant/internal_legacy/protocol/profile_update_proposal.dart';
import 'package:test/test.dart';

void main() {
  group('ProfileUpdateProposal contract', () {
    test('valid proposal passes contract validation', () {
      final proposal = ProfileUpdateProposal(
        proposalId: 'proposal_001',
        profileVersionRead: 'v12',
        generatedAt: DateTime.parse('2026-02-18T08:00:00Z'),
        sourceRuns: const <String>['run_a', 'run_b'],
        confidence: 0.83,
        requiresUserConfirm: true,
        updates: const <ProfileUpdateItem>[
          ProfileUpdateItem(
            facet: 'basicIdentity',
            path: 'basicIdentity.birthDateLunar',
            operation: 'set',
            newValue: '腊月初八',
            oldValueSnapshot: '',
            reason: 'converted from solar birthday',
            evidenceRefs: <String>['trace_birth'],
            itemConfidence: 0.91,
            riskLevel: 'high',
          ),
        ],
      );

      expect(proposal.isValid, isTrue);
      final decoded = ProfileUpdateProposal.fromJson(proposal.toJson());
      expect(decoded.isValid, isTrue);
      expect(decoded.updates.first.operation, equals('set'));
      expect(decoded.updates.first.riskLevel, equals('high'));
      expect(decoded.requiresUserConfirm, isTrue);
    });

    test('invalid operation is rejected', () {
      const item = ProfileUpdateItem(
        facet: 'tonePreferences',
        path: 'tonePreferences.communication_style_tags',
        operation: 'override',
        newValue: <String>['humorous'],
        oldValueSnapshot: <String>['business_formal'],
        reason: 'invalid operation type',
        evidenceRefs: <String>['trace_2'],
        itemConfidence: 0.2,
        riskLevel: 'low',
      );
      expect(item.isValid, isFalse);
    });

    test('confidence out of range fails validation', () {
      final proposal = ProfileUpdateProposal(
        proposalId: 'proposal_002',
        profileVersionRead: 'v1',
        generatedAt: DateTime.now(),
        sourceRuns: const <String>['run_a'],
        confidence: 1.5,
        requiresUserConfirm: false,
        updates: const <ProfileUpdateItem>[
          ProfileUpdateItem(
            facet: 'interestTopics',
            path: 'interestTopics.news_current_affairs',
            operation: 'set',
            newValue: 0.3,
            oldValueSnapshot: 0.2,
            reason: 'engagement growth',
            evidenceRefs: <String>['trace_3'],
            itemConfidence: 0.7,
            riskLevel: 'low',
          ),
        ],
      );
      expect(proposal.isValid, isFalse);
    });
  });
}

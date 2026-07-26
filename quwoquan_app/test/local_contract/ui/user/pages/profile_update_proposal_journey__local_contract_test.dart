import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_update_proposal_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets('资料提案确认后安全应用并关闭审查面板', (tester) async {
    final writer = _JourneyProposalWriter();
    await _pumpProposalJourney(tester, writer);

    await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(writer.calls, <String>[
      'confirm:proposal-uat',
      'apply:proposal-uat',
    ]);
    expect(
      find.byKey(const ValueKey('profile-proposal-review-sheet')),
      findsNothing,
    );
  });

  testWidgets('资料提案命令失败时保留错误与恢复入口', (tester) async {
    final writer = _JourneyProposalWriter(failApply: true);
    await _pumpProposalJourney(tester, writer);

    await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('profile-proposal-error')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('profile-proposal-review-sheet')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('profile-proposal-approve')),
      findsOneWidget,
    );
  });
}

Future<void> _pumpProposalJourney(
  WidgetTester tester,
  _JourneyProposalWriter writer,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        profileEditProposalCommandWriterProvider.overrideWithValue(writer),
      ],
      child: CupertinoApp(
        home: ProfileUpdateProposalReviewSheet(
          proposal: ProfileUpdateProposalView(
            id: 'proposal-uat',
            personaId: 'persona-uat',
            source: ProfileUpdateProposalSource.assistant,
            reason: 'assistant evidence',
            evidenceRefs: const <String>['assistant-run:run-uat'],
            impactScope: const <String>['bio', 'displayName'],
            createdBy: 'persona-uat',
            status: ProfileUpdateProposalStatus.pending,
            changes: ProfileChangeSet(displayName: '商用昵称', bio: '商用简介'),
            reviewedBy: null,
            applyAuditId: null,
            rollbackDeadline: null,
            rollbackAuditId: null,
            version: 1,
            createdAt: DateTime.utc(2026, 7, 19),
            updatedAt: DateTime.utc(2026, 7, 19),
            resolvedAt: null,
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

final class _JourneyProposalWriter
    implements ProfileUpdateProposalCommandWriter {
  _JourneyProposalWriter({this.failApply = false});

  final bool failApply;
  final List<String> calls = <String>[];

  @override
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  ) {
    throw UnsupportedError('本旅程不创建资料提案');
  }

  @override
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  ) async {
    calls.add('confirm:${command.proposalId}');
    return ProfileUpdateProposalCommandResult(
      proposalId: command.proposalId,
      version: 2,
      status: ProfileUpdateProposalStatus.confirmed,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  ) async {
    calls.add('apply:${command.proposalId}');
    if (failApply) {
      throw StateError('模拟应用失败');
    }
    return ProfileUpdateProposalCommandResult(
      proposalId: command.proposalId,
      version: 3,
      status: ProfileUpdateProposalStatus.applied,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  ) {
    throw UnsupportedError('本旅程不回滚资料提案');
  }

  @override
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  ) async {
    calls.add('reject:${command.proposalId}');
    return ProfileUpdateProposalCommandResult(
      proposalId: command.proposalId,
      version: 2,
      status: ProfileUpdateProposalStatus.rejected,
      replayed: false,
    );
  }
}

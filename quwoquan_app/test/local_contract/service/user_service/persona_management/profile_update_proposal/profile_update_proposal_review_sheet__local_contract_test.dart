// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/application/public/profile_update_proposal_ports.dart';
import 'package:quwoquan_app/runtime/di/presentation/profile_update_proposal_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  testWidgets(
    'pending proposal confirms target version server-side then applies',
    (tester) async {
      final writer = _RecordingWriter();
      await _pumpReview(tester, writer: writer, proposal: _proposal());

      expect(
        find.text(ProfileText.editProfileProposalReviewBasis),
        findsOneWidget,
      );
      expect(find.text('assistant evidence'), findsOneWidget);
      expect(find.text('assistant-run:run-1'), findsOneWidget);
      expect(
        find.text(
          '${ProfileText.editProfileBioLabel}, '
          '${ProfileText.editProfileNicknameLabel}',
        ),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 4));

      expect(writer.calls, <String>['confirm:proposal-1', 'apply:proposal-1']);
      expect(
        find.byKey(const ValueKey('profile-proposal-review-sheet')),
        findsNothing,
      );
    },
  );

  testWidgets(
    'reject is a single aggregate command with no apply side effect',
    (tester) async {
      final writer = _RecordingWriter();
      await _pumpReview(tester, writer: writer, proposal: _proposal());

      await tester.tap(find.byKey(const ValueKey('profile-proposal-reject')));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 4));

      expect(writer.calls, <String>['reject:proposal-1']);
    },
  );

  testWidgets('command failure remains visible and retryable', (tester) async {
    final writer = _RecordingWriter(error: StateError('write failed'));
    await _pumpReview(tester, writer: writer, proposal: _proposal());

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
  });

  testWidgets('applying proposal can resume but cannot be rejected', (
    tester,
  ) async {
    final writer = _RecordingWriter();
    await _pumpReview(
      tester,
      writer: writer,
      proposal: _proposal(status: ProposalStatus.applying),
    );

    expect(
      find.byKey(const ValueKey('profile-proposal-approve')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('profile-proposal-reject')), findsNothing);
    await tester.tap(find.byKey(const ValueKey('profile-proposal-approve')));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(writer.calls, <String>['apply:proposal-1']);
  });

  testWidgets('applied proposal exposes auditable rollback action', (
    tester,
  ) async {
    final writer = _RecordingWriter();
    await _pumpReview(
      tester,
      writer: writer,
      proposal: _proposal(status: ProposalStatus.applied),
    );

    expect(
      find.byKey(const ValueKey('profile-proposal-rollback')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('profile-proposal-approve')),
      findsNothing,
    );
    await tester.tap(find.byKey(const ValueKey('profile-proposal-rollback')));
    await tester.pumpAndSettle();
    await tester.pump(const Duration(seconds: 4));

    expect(writer.calls, <String>['rollback:proposal-1']);
  });
}

Future<void> _pumpReview(
  WidgetTester tester, {
  required _RecordingWriter writer,
  required ProfileUpdateProposalView proposal,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        profileEditProposalCommandWriterProvider.overrideWithValue(writer),
      ],
      child: CupertinoApp(
        initialRoute: '/review',
        routes: <String, WidgetBuilder>{
          '/': (_) => const SizedBox.shrink(),
          '/review': (_) =>
              ProfileUpdateProposalReviewSheet(proposal: proposal),
        },
      ),
    ),
  );
  await tester.pumpAndSettle();
}

ProfileUpdateProposalView _proposal({
  ProposalStatus status = ProposalStatus.pending,
}) => ProfileUpdateProposalView(
  id: 'proposal-1',
  personaId: 'persona-1',
  source: ProposalSource.assistant,
  reason: 'assistant evidence',
  evidenceRefs: const <String>['assistant-run:run-1'],
  impactScope: const <String>['bio', 'displayName'],
  createdBy: 'persona-1',
  status: status,
  displayName: 'new name',
  bio: '',
  reviewedBy: null,
  applyAuditId: status == ProposalStatus.applied ? 'audit-apply-1' : null,
  rollbackDeadline: status == ProposalStatus.applied
      ? DateTime.utc(2026, 7, 23)
      : null,
  rollbackAuditId: null,
  version: 1,
  createdAt: DateTime.utc(2026, 7, 16),
  updatedAt: DateTime.utc(2026, 7, 16),
  resolvedAt: null,
);

final class _RecordingWriter implements ProfileUpdateProposalWriter {
  _RecordingWriter({this.error});

  final Object? error;
  final List<String> calls = <String>[];

  void _throwIfNeeded() {
    final current = error;
    if (current != null) throw current;
  }

  @override
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  ) async {
    calls.add('confirm:${command.proposalId}');
    _throwIfNeeded();
    return ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 2,
      status: ProposalStatus.confirmed,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  ) async {
    calls.add('apply:${command.proposalId}');
    _throwIfNeeded();
    return ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 3,
      status: ProposalStatus.applied,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  ) async {
    calls.add('rollback:${command.proposalId}');
    _throwIfNeeded();
    return ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 4,
      status: ProposalStatus.rolledBack,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  ) async {
    calls.add('reject:${command.proposalId}');
    _throwIfNeeded();
    return ProfileUpdateProposalCommandResult(
      proposalId: 'proposal-1',
      version: 2,
      status: ProposalStatus.rejected,
      replayed: false,
    );
  }

  @override
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  ) => throw UnsupportedError('review sheet cannot create proposals');
}

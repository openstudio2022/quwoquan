import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test('alpha proposal facet follows typed state machine and replay semantics', () async {
    final facet = AlphaProfileUpdateProposalFacet();
    final create = CreateProfileUpdateProposalCommand(
      personaId: 'persona-1',
      proposalId: 'proposal-1',
      source: ProfileUpdateProposalSource.assistant,
      changes: ProfileChangeSet(displayName: '新名字'),
    );

    final created = await facet.create(create);
    final replayedCreate = await facet.create(create);
    expect(created.status, ProfileUpdateProposalStatus.pending);
    expect(replayedCreate.replayed, isTrue);
    expect(replayedCreate.version, created.version);

    final confirmed = await facet.confirm(
      ConfirmProfileUpdateProposalCommand(proposalId: 'proposal-1'),
    );
    final applied = await facet.apply(
      ApplyProfileUpdateProposalCommand(proposalId: 'proposal-1'),
    );
    final replayedApply = await facet.apply(
      ApplyProfileUpdateProposalCommand(proposalId: 'proposal-1'),
    );

    expect(confirmed.status, ProfileUpdateProposalStatus.confirmed);
    expect(applied.status, ProfileUpdateProposalStatus.applied);
    expect(replayedApply.replayed, isTrue);
    expect(replayedApply.version, applied.version);

    final view = await facet.get(
      ProfileUpdateProposalQuery(proposalId: 'proposal-1'),
    );
    final slice = await facet.list(
      ProfileUpdateProposalListQuery(personaId: 'persona-1'),
    );
    expect(view.status, ProfileUpdateProposalStatus.applied);
    expect(slice.items.map((item) => item.id), contains('proposal-1'));
  });

  test('alpha proposal facet blocks reject after applying', () async {
    final facet = AlphaProfileUpdateProposalFacet();
    await facet.create(
      CreateProfileUpdateProposalCommand(
        personaId: 'persona-1',
        proposalId: 'proposal-2',
        source: ProfileUpdateProposalSource.persona,
        changes: ProfileChangeSet(bio: '新的简介'),
      ),
    );
    await facet.confirm(
      ConfirmProfileUpdateProposalCommand(proposalId: 'proposal-2'),
    );
    await facet.apply(
      ApplyProfileUpdateProposalCommand(proposalId: 'proposal-2'),
    );

    expect(
      () => facet.reject(
        RejectProfileUpdateProposalCommand(proposalId: 'proposal-2'),
      ),
      throwsStateError,
    );
  });
}

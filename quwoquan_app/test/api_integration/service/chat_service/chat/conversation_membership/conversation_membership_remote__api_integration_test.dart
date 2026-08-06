// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/member-add-remove-policy/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';

void main() {
  late ChatApiContractHarness harness;
  late String conversationId;

  setUpAll(() async {
    harness = await ChatApiContractHarness.create();
    conversationId = await harness.seedConversation();
  });
  tearDownAll(() => harness.close());

  test('production Remote 对非互关成员执行关系门禁', () async {
    await expectLater(
      harness.repository.addMembers(
        conversationId: conversationId,
        userIds: const <String>['l3_test_member_001'],
      ),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 403)
            .having(
              (error) => error.code,
              'code',
              anyOf(
                'CHAT.USER.group_member_not_mutual',
                'CHAT.USER.group_member_blocked',
              ),
            ),
      ),
    );
  });
}

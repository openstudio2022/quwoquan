import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/conversation/message_bubble_frame.dart';

void main() {
  testWidgets('会话气泡会阻断上层误传的文本下划线装饰', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DefaultTextStyle.merge(
            style: const TextStyle(
              decoration: TextDecoration.underline,
              decorationColor: Colors.yellow,
            ),
            child: const MessageBubbleFrame(
              isRight: false,
              hideAvatarAndName: true,
              senderName: '',
              textColor: Colors.black,
              content: Text('plain conversation text'),
            ),
          ),
        ),
      ),
    );

    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(MessageBubbleFrame),
        matching: find.text('plain conversation text', findRichText: true),
      ),
    );

    expect(richText.text.style?.decoration, TextDecoration.none);
  });
}

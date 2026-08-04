// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/media/generated/content_image_variant_policy.g.dart';

void main() {
  test('图片交付 profile 只消费 metadata 生成的唯一策略', () {
    expect(ContentImageVariantPolicy.derivativePolicyVersion, 1);
    expect(
      ContentImageVariantPolicy.profiles.map(
        (name, profile) => MapEntry(name, <Object>[
          profile.width,
          profile.format,
          profile.quality,
        ]),
      ),
      <String, List<Object>>{
        'thumbnail': <Object>[320, 'webp', 80],
        'display': <Object>[960, 'webp', 82],
        'cover': <Object>[1280, 'webp', 85],
        'full': <Object>[2048, 'webp', 90],
      },
    );
  });

  test('未知图片交付 profile fail closed', () {
    expect(
      () => ContentImageVariantPolicy.profile('original'),
      throwsArgumentError,
    );
  });
}

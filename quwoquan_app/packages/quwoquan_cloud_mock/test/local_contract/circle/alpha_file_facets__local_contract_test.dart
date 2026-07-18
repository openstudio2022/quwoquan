import 'package:test/test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test(
    'alpha CircleFile fixture preserves folder and MediaAsset reference invariants',
    () async {
      final facet = AlphaCircleFileFacet();
      final folder = await facet.create(
        CreateCircleFileCommand(
          circleId: 'circle-1',
          name: '资料',
          fileType: CircleFileType.folder,
        ),
      );
      final file = await facet.create(
        CreateCircleFileCommand(
          circleId: 'circle-1',
          parentFolderId: folder.fileId,
          name: 'contract.pdf',
          fileType: CircleFileType.file,
          assetId: 'alpha-media-1',
        ),
      );

      final page = await facet.list(
        CircleFileListQuery(
          circleId: 'circle-1',
          parentFolderId: folder.fileId,
        ),
      );
      expect(page.items.single.fileId, file.fileId);
      expect(page.items.single.assetId, 'alpha-media-1');

      final deleted = await facet.delete(
        DeleteCircleFileCommand(circleId: 'circle-1', fileId: file.fileId),
      );
      expect(deleted.status, CircleFileStatus.deleted);
      expect(
        (await facet.list(
          CircleFileListQuery(
            circleId: 'circle-1',
            parentFolderId: folder.fileId,
          ),
        )).items,
        isEmpty,
      );
    },
  );
}

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

typedef void (^QWQAliyunOneTapCompletion)(NSDictionary<NSString *, id> *result);

@interface AliyunOneTapRuntimeBridge : NSObject

+ (BOOL)isSDKPresent;
+ (void)configureWithSecretInfo:(NSString *)secretInfo
                     completion:(QWQAliyunOneTapCompletion)completion;
+ (void)requestLoginTokenFromController:(UIViewController *)controller
                             completion:(QWQAliyunOneTapCompletion)completion;

@end

NS_ASSUME_NONNULL_END

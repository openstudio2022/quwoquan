#import "AliyunOneTapRuntimeBridge.h"

#import <objc/message.h>
#import <objc/runtime.h>

@implementation AliyunOneTapRuntimeBridge

+ (Class)handlerClass {
  return NSClassFromString(@"TXCommonHandler");
}

+ (id)sharedHandler {
  Class handlerClass = [self handlerClass];
  SEL selector = NSSelectorFromString(@"sharedInstance");
  if (handlerClass == Nil || ![handlerClass respondsToSelector:selector]) {
    return nil;
  }
  id (*messageSend)(id, SEL) = (void *)objc_msgSend;
  return messageSend(handlerClass, selector);
}

+ (BOOL)isSDKPresent {
  return [self sharedHandler] != nil;
}

+ (void)configureWithSecretInfo:(NSString *)secretInfo
                     completion:(QWQAliyunOneTapCompletion)completion {
  id handler = [self sharedHandler];
  SEL selector = NSSelectorFromString(@"setAuthSDKInfo:complete:");
  if (handler == nil || secretInfo.length == 0 || ![handler respondsToSelector:selector]) {
    completion(@{@"resultCode": @"sdk_not_configured"});
    return;
  }
  void (*messageSend)(id, SEL, NSString *, QWQAliyunOneTapCompletion) =
      (void *)objc_msgSend;
  messageSend(handler, selector, secretInfo, completion);
}

+ (void)requestLoginTokenFromController:(UIViewController *)controller
                             completion:(QWQAliyunOneTapCompletion)completion {
  id handler = [self sharedHandler];
  SEL selector =
      NSSelectorFromString(@"getLoginTokenWithTimeout:controller:model:complete:");
  if (handler == nil || controller == nil || ![handler respondsToSelector:selector]) {
    completion(@{@"resultCode": @"sdk_not_configured"});
    return;
  }
  void (*messageSend)(
      id,
      SEL,
      NSTimeInterval,
      UIViewController *,
      id,
      QWQAliyunOneTapCompletion) = (void *)objc_msgSend;
  messageSend(handler, selector, 5.0, controller, nil, completion);
}

@end

{{flutter_js}}
{{flutter_build_config}}

(function () {
  "use strict";

  function startFlutter() {
    return _flutter.loader.load({
      config: {
        canvasKitBaseUrl: "canvaskit/",
      },
    });
  }

  if (!window.__qwqRuntimeConfigReady) {
    window.__qwqShowRuntimeConfigError("bootstrap-not-installed");
    return;
  }

  window.__qwqRuntimeConfigReady.then(startFlutter).catch(function (error) {
    var reason = error && error.code ? error.code : "runtime-config-invalid";
    window.__qwqShowRuntimeConfigError(reason);
  });
})();

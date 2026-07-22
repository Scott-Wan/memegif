(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RangePreview = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const MIN_RANGE_SECONDS = 0.1;
  const END_EPSILON_SECONDS = 0.04;

  function playbackAction(currentTime, startSec, endSec) {
    if (endSec - startSec < MIN_RANGE_SECONDS) {
      return { pause: true, seekTo: startSec };
    }
    if (
      !Number.isFinite(currentTime) ||
      currentTime < startSec - END_EPSILON_SECONDS ||
      currentTime >= endSec - END_EPSILON_SECONDS
    ) {
      return { pause: false, seekTo: startSec };
    }
    return { pause: false, seekTo: null };
  }

  function isCurrentPreviewRequest(requestId, activeId, requestPath, activePath) {
    return requestId === activeId && requestPath === activePath;
  }

  return {
    MIN_RANGE_SECONDS,
    END_EPSILON_SECONDS,
    playbackAction,
    isCurrentPreviewRequest,
  };
});

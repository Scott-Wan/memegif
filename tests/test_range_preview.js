const test = require("node:test");
const assert = require("node:assert/strict");
const {
  playbackAction,
  isCurrentPreviewRequest,
  END_EPSILON_SECONDS,
} = require("../web/range-preview.js");

test("播放位置在所选区间内时不跳转", () => {
  assert.deepEqual(playbackAction(1.5, 1, 2), {
    pause: false,
    seekTo: null,
  });
});

test("播放到终点附近时回到起点", () => {
  assert.deepEqual(playbackAction(1.97, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("恰好落在终点阈值边界时也会回到起点", () => {
  assert.deepEqual(playbackAction(2 - END_EPSILON_SECONDS, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("播放位置为 NaN 时会回到起点", () => {
  assert.deepEqual(playbackAction(Number.NaN, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("播放位置落在起点前时回到起点", () => {
  assert.deepEqual(playbackAction(0.5, 1, 2), {
    pause: false,
    seekTo: 1,
  });
});

test("过短区间暂停并停在起点", () => {
  assert.deepEqual(playbackAction(1.03, 1, 1.05), {
    pause: true,
    seekTo: 1,
  });
});

test("只有请求编号和路径都匹配时才接受异步响应", () => {
  assert.equal(isCurrentPreviewRequest(3, 3, "a.gif", "a.gif"), true);
  assert.equal(isCurrentPreviewRequest(2, 3, "a.gif", "a.gif"), false);
  assert.equal(isCurrentPreviewRequest(3, 3, "old.gif", "a.gif"), false);
});

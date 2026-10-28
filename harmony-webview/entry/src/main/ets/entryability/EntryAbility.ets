// Copyright (c) 2026 TeleVideo / LMBrewer
// SPDX-License-Identifier: MIT

import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';

export default class EntryAbility extends UIAbility {
  onCreate(want, launchParam) {
    // 应用启动时不需要额外初始化 —— WebView 页面会自行加载 SimChat 服务
  }

  onDestroy() {
    // 不需要清理，WebView 跟着 Activity 一起销毁
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index', (err) => {
      if (err.code) {
        // 真实项目里这里应该 hilog 一下；作为 Phase 0 骨架，保持最小
        console.error('SimChat: loadContent failed ' + JSON.stringify(err));
        return;
      }
      // 窗口创建成功 —— Index.ets 会自动打开 WebView
    });
  }

  onWindowStageDestroy(): void {}
  onForeground(): void {}
  onBackground(): void {}
}

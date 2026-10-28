// Copyright (c) 2026 TeleVideo / LMBrewer
// SPDX-License-Identifier: MIT

/**
 * SimChat WebView 壳 — Phase 0 骨架
 *
 * 这个页面只做三件事：
 *   1. 打开一个 WebView 指向 SimChat 后端服务
 *   2. 允许用户修改后端 URL（融合开发引擎内网地址 / 127.0.0.1 / 远端云服务）
 *   3. 显示加载状态和错误提示
 *
 * 后端启动：在融合开发引擎的 Linux 子系统里运行
 *     cd /mnt/linux_share/<你的项目目录>
 *     pip install -r simchat/scripts/requirements-simchat.txt
 *     python -m simchat.web
 *
 * 然后在融合开发引擎里跑 `ip addr` 看一下 NAT 网段的内网 IP（一般是 192.168.x.x），
 * 在本应用的输入框里填上 http://<那个 IP>:5000 即可。
 */

import { webview } from '@kit.ArkWeb';
import { promptAction } from '@kit.ArkUI';

// ----------------- 默认配置 -----------------
// 融合开发引擎（openEuler Linux）通过 NAT 和鸿蒙宿主互通。
// 运行 `ip addr` 后能看到一个 192.168.x.x 网段的地址，用那个替换下面的 IP。
const DEFAULT_URL = 'http://127.0.0.1:5000';

@Entry
@Component
struct Index {
  // WebView 控制器 —— ArkTS 和 Web 页面交互的桥梁
  controller: webview.WebviewController = new webview.WebviewController();

  // 用户可编辑的后端地址（@State 让 UI 跟着刷新）
  @State serverUrl: string = DEFAULT_URL;
  // WebView 当前加载的地址（只有点了"连接"才更新）
  @State currentUrl: string = DEFAULT_URL;
  // 加载状态
  @State isLoading: boolean = true;
  @State errorMsg: string = '';
  @State showSetup: boolean = true;  // 首次启动显示配置卡片

  build() {
    Column() {
      // --- 顶部标题栏 ---
      Row() {
        Text('SimChat')
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.White)
        Spacer()
        Text(this.isLoading ? '加载中…' : this.errorMsg ? '连接失败' : '已连接')
          .fontSize(12)
          .fontColor(this.errorMsg ? '#ff6b6b' : this.isLoading ? '#ffd93d' : '#6bcb77')
        Button('设置')
          .fontSize(12)
          .height(28)
          .margin({ left: 8 })
          .onClick(() => { this.showSetup = !this.showSetup })
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 12, bottom: 8 })
      .backgroundColor('#1a1a2e')

      // --- 配置卡片 ---
      if (this.showSetup) {
        Column() {
          Text('SimChat 后端地址')
            .fontSize(14)
            .fontWeight(FontWeight.Medium)
            .margin({ bottom: 6 })
          TextInput({ placeholder: DEFAULT_URL, text: this.serverUrl })
            .width('100%')
            .height(36)
            .backgroundColor('#2a2a3e')
            .fontColor(Color.White)
            .onChange((v: string) => { this.serverUrl = v })
          Row() {
            Button('连接')
              .type(ButtonType.Primary)
              .onClick(() => this.connect())
            Button('使用默认')
              .margin({ left: 8 })
              .onClick(() => {
                this.serverUrl = DEFAULT_URL
                this.connect()
              })
          }
          .margin({ top: 10 })
          .justifyContent(FlexAlign.Start)

          Text('提示: 在融合开发引擎里启动 python -m simchat.web 后，\n用 ip addr 查看 Linux 子系统的 192.168.x.x 地址填在这里。')
            .fontSize(11)
            .fontColor('#888899')
            .margin({ top: 10 })
        }
        .width('100%')
        .padding(16)
        .backgroundColor('#16213e')
        .borderRadius(0)
      }

      // --- WebView ---
      Stack() {
        Web({ src: this.currentUrl, controller: this.controller })
          .width('100%')
          .height('100%')
          .domStorageAccess(true)
          .javaScriptAccess(true)
          .cacheMode(CacheMode.None)
          .backgroundColor('#0f0f1e')
          .onPageBegin(() => {
            this.isLoading = true
            this.errorMsg = ''
          })
          .onPageEnd(() => {
            this.isLoading = false
          })
          .onErrorReceive((event) => {
            this.isLoading = false
            this.errorMsg = `错误 ${event.errorCode}: ${event.errorDescription}`
          })

        if (this.isLoading) {
          LoadingProgress().width(40).height(40).color('#6bcb77')
        }

        if (this.errorMsg && !this.isLoading) {
          Column() {
            Text('无法连接到 SimChat 后端')
              .fontSize(16)
              .fontColor('#ff6b6b')
              .margin({ bottom: 8 })
            Text(this.errorMsg)
              .fontSize(12)
              .fontColor('#aaaaaa')
            Button('重试')
              .margin({ top: 12 })
              .onClick(() => this.connect())
          }
          .padding(20)
          .backgroundColor('#1a1a2e')
          .borderRadius(12)
        }
      }
      .width('100%')
      .layoutWeight(1)
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#0f0f1e')
  }

  connect() {
    let url = this.serverUrl.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://' + url
    }
    if (url === this.currentUrl) {
      this.controller.refresh()
    } else {
      this.currentUrl = url
    }
    this.showSetup = false
    promptAction.showToast({ message: '正在连接 ' + url })
  }
}

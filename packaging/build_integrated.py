"""Single portable client containing the host service and pinned tunnel helper."""
import argparse
import shutil
from pathlib import Path
import build_release as release

release.DIST = release.ROOT / 'dist' / 'integrated-preview'
release.WORK = release.ROOT / 'build' / 'integrated-preview'
release.CLIENT_HELP = '''超时空会夜机 · 一体化预览（2026-10-17）
Windows 10 / 11 64 位；无需安装 Python、Qt、mpv 或独立服务端。

1. 完整解压后运行 EXE，保留 _internal 文件夹。
2. 左侧「房间」输入昵称。异地选「公共通道」，创建后复制邀请链接给朋友。
   朋友粘贴完整邀请链接即可加入，无需自行部署服务器或配置内网穿透。
   首次建通道最多等待 60 秒；新域名生效可能延迟，加入最多等待 90 秒，可随时取消。
3. 同一 Wi-Fi / 有线局域网可选择「直接连接」。多网卡时选择朋友可访问的网卡。
   Windows 防火墙若询问，请允许所用的专用网络；本软件不会修改防火墙规则。
4. 原服务器和外部穿透仍在「原服务器 / 外部内网穿透」模式，使用原地址及四位房间号。
5. 房主离开或关闭软件会解散内置房间，不自动转移房主。成员短暂掉线会自动恢复。
   公共通道断开时先等待自动恢复；必要时房主重新生成邀请，成员离开后粘贴新链接。
6. 每位成员在「播放影厅」自行打开相同视频，房间只传播放控制与聊天，不共享视频文件。
   底部控制栏悬停显示、离开延迟隐藏。右侧可选画质、音轨、分 P，并扫码登录 Bilibili。
   点击时间块输入时间回车跳转，左右键每次 5 秒并同步；点击喇叭静音 / 恢复。
7. 邀请含房间密钥，只分享给想邀请的人；会话与邀请不写入配置。
   个人登录保存到 EXE 旁 config.json，重新分发时请移除 config.json 和 crash.log。

公共通道使用 Cloudflare Quick Tunnel，属于无可用性保证的临时服务。
聊天和控制经第三方通道转发（传输加密，非端到端加密）；不传视频、不建立系统虚拟网卡。
不保证所有地区和运营商均可连接；可退回局域网或原服务器方式。
组件 cloudflared 2026.10.1 随包提供，不安装系统服务、不需要账号，退出后清理进程。
本预览版尚未在独立的 Windows 10 和 Windows 11 全新机器上分别验收。
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'archive'])
    parser.add_argument('--output', type=Path, default=release.ROOT / 'dist/integrated-archives')
    args = parser.parse_args()
    if args.action == 'build':
        release.build(components=['client'])
        package = release.DIST / release.CLIENT_NAME
        shutil.copy2(release.ROOT / '一体化方案与验收.txt', package / '发行检查.txt')
        with (package / '第三方依赖说明.txt').open('a', encoding='utf-8') as notices:
            notices.write('\ncloudflared 2026.10.1 (Apache-2.0): https://github.com/cloudflare/cloudflared\n'
                          'License: _internal/THIRD-PARTY-CLOUDFLARED.txt\n')
    else:
        release.archive(args.output, names=[release.CLIENT_NAME])

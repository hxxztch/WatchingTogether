"""Single portable client containing the host service and pinned tunnel helper."""
import argparse
import shutil
from pathlib import Path
import build_release as release

release.DIST = release.ROOT / 'dist' / release.CLIENT_VERSION
release.WORK = release.ROOT / 'build' / release.CLIENT_VERSION
release.CLIENT_HELP = f'''超时空会夜机 {release.CLIENT_VERSION}
Windows 10 / 11 64 位；无需安装 Python、Qt、mpv 或独立服务端。

1. 完整解压后运行 EXE，保留 _internal 文件夹。
2. 先在「个人中心」填写昵称，离开输入框即自动保存。再到「房间」选「公共通道」，创建后复制邀请链接给朋友。
   朋友粘贴完整邀请链接即可加入，无需自行部署服务器或配置内网穿透。
   首次建通道最多等待 60 秒；新域名生效可能延迟，加入最多等待 90 秒，可随时取消。
3. 同一 Wi-Fi / 有线局域网可选择「直接连接」。多网卡时选择朋友可访问的网卡。
   Windows 防火墙若询问，请允许所用的专用网络；本软件不会修改防火墙规则。
4. 原服务器和外部穿透仍在「原服务器 / 外部内网穿透」模式，使用原地址及四位房间号。
5. 房主离开或关闭软件会解散内置房间，不自动转移房主。成员短暂掉线会自动恢复。
   公共通道断开时先等待自动恢复；必要时房主退出并重新创建，成员粘贴新邀请加入。
6. 每位成员在「播放影厅」自行打开相同视频，房间只传播放控制与聊天，不共享视频文件。
   底部单行控制栏悬停显示、离开延迟隐藏，支持输入弹幕并回车发送。右侧可选画质、音轨、分 P。
   点击时间块输入时间回车跳转，左右键每次 5 秒并同步；点击喇叭静音 / 恢复。
7. 邀请含房间密钥，只分享给想邀请的人；会话与邀请不写入配置。
   个人登录保存到 EXE 旁 config.json，重新分发时请移除 config.json 和 crash.log。
8. 「个人中心」管理昵称和 Bilibili 登录；空昵称不能入房，新昵称从下一次加入生效。
   小窗标题显示影片名，底部显示播放进度；长标题按完整行省略，悬停查看全名。
9. 影厅右侧「导入字幕」支持 SRT / ASS / SSA / SUB / VTT / TXT，亦可拖入。
   「撤销字幕」移除最近手动导入的外挂字幕，不删除原文件、不影响内嵌字幕。
10. 创建公共通道时显示转圈提示并锁定其他操作，可用提示框内「取消」中止。
11. 视频底部控制栏的「弹」图标开关只影响本机显示；蓝色对勾为开启、灰色叉号为关闭。关闭立即清空，再开启只显示新收到的弹幕，聊天室仍保留消息。
12. 聊天室输入框旁的「表情」可选系统emoji插入文字，或单独发送图片，也可直接上传图片发送。底部控制栏仅发送文字弹幕。
    个人中心的「表情包管理」可添加自定义图片、导入文件夹/ZIP外部表情包集，重命名图片/表情包、删除图片；系统emoji不可改动。
    影厅「收起视频功能」可收起登录、音轨、分P和字幕，增加聊天空间；右上角「详情」查看成员，离开房间请前往侧栏「房间」。
    PNG/JPG/WebP/BMP/GIF均可导入，GIF仅显示首帧。发送前自动压缩；单图原文件最多8MB，尺寸最多1600万像素。
    表情保存在EXE旁stickers文件夹，升级时保留；重新分发前请移除个人表情库。图片消息需要新版房主/服务器支持。
13. 播放中最小化主窗口会弹出小窗，已有小窗不会随主窗口最小化；点小窗「返回影厅」恢复主窗口。

公共通道使用 Cloudflare Quick Tunnel，属于无可用性保证的临时服务。
聊天和控制经第三方通道转发（传输加密，非端到端加密）；不传视频、不建立系统虚拟网卡。
不保证所有地区和运营商均可连接；可退回局域网或原服务器方式。
组件 cloudflared 2026.10.1 随包提供，不安装系统服务、不需要账号，退出后清理进程。
本预览版尚未在独立的 Windows 10 和 Windows 11 全新机器上分别验收。
'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'archive'])
    parser.add_argument('--output', type=Path, default=release.ROOT / 'dist/beta-archives')
    args = parser.parse_args()
    if args.action == 'build':
        release.build(components=['client'])
        package = release.DIST / release.CLIENT_NAME
        with (package / '第三方依赖说明.txt').open('a', encoding='utf-8') as notices:
            notices.write('\ncloudflared 2026.10.1 (Apache-2.0): https://github.com/cloudflare/cloudflared\n'
                          'License: _internal/THIRD-PARTY-CLOUDFLARED.txt\n')
    else:
        release.archive(args.output, names=[release.CLIENT_NAME],
                        filenames={release.CLIENT_NAME: release.CLIENT_VERSION + '.zip'})

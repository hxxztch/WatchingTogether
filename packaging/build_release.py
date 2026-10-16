"""Reproducible portable Windows builds; never includes personal config or logs."""
import argparse
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.version import CLIENT_NAME, SERVER_NAME, CLIENT_VERSION, SERVER_VERSION

DIST = ROOT / 'dist' / ('release-' + CLIENT_VERSION)
WORK = ROOT / 'build' / ('release-' + CLIENT_VERSION)

CLIENT_HELP = f'''{CLIENT_NAME} / Windows 10、11 64位便携版

1. 完整解压本文件夹到可写目录，再双击“{CLIENT_NAME}.exe”。
2. 无需安装Python、Qt、mpv或其他依赖。请保留_internal文件夹，不能只复制EXE。
3. 先由一人启动server-1.2.0，在客户端填写ws://服务端电脑的局域网IP:9877，点击刷新连接，创建或加入房间。
4. 服务端在同一电脑时填ws://127.0.0.1:9877。跨网段可使用已有虚拟局域网IP，所有成员仍需各自打开同一视频。
5. 点击时间块输入秒数、分:秒或时:分:秒，回车跳转；左右键每次点按5秒，同步房间在线成员；点击喇叭静音/恢复。
6. B站登录请打开“其他功能”，使用手机APP扫码确认；可用清晰度取决于账号与视频权限，登录后重新打开视频刷新画质列表。
7. 配置和登录信息首次运行后自动保存在EXE旁config.json。分发此文件夹前请勿带上个人config.json和crash.log。

联网观看和联机需要正常网络；操作系统显卡/声卡驱动需正常。首次运行如果Windows防火墙询问，请允许需要使用的网络。
本包不包含VPN或公网穿透账号；同一局域网联机无需额外工具。
'''
SERVER_HELP = '''server-1.2.0 / Windows 10、11 64位便携版

1. 完整解压后双击“server-1.2.0.exe”，保持服务窗口打开即可。
2. 无需安装Python或任何第三方依赖，请保留_internal文件夹。
3. 默认监听0.0.0.0:9877。客户端填写ws://这台电脑的局域网或虚拟局域网IP:9877。
4. 同一电脑的客户端可填写ws://127.0.0.1:9877。首次启动如有防火墙提示，请允许所使用的网络。
5. 在客户端创建/加入房间。服务端只同步控制与聊天，不传输视频，每位成员自行打开相同视频。
6. 关闭服务窗口或按Ctrl+C可停止。服务端重启后原房间需要重新创建。

可选命令行参数：
  server-1.2.0.exe --port 9878
  server-1.2.0.exe --host 127.0.0.1 --port 9877
  server-1.2.0.exe --version
如果启动提示端口占用，请关闭旧服务端或换端口。修改端口后客户端地址也要相应修改。
本包不需要ngrok；公网或跨局域网接入请使用已有虚拟局域网或自行配置转发。
'''


def build(components=None):
    WORK.mkdir(parents=True, exist_ok=True)
    for component, name, help_text in [('server', SERVER_NAME, SERVER_HELP), ('client', CLIENT_NAME, CLIENT_HELP)]:
        if components is not None and component not in components:
            continue
        log = WORK / (component + '-build.log')
        with log.open('w', encoding='utf-8') as output:
            completed = subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                '--distpath', str(DIST), '--workpath', str(WORK / component),
                str(ROOT / 'packaging' / (component + '.spec'))], cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT)
        if completed.returncode:
            print(log.read_text(encoding='utf-8')[-6000:])
            raise RuntimeError(component + ' build failed')
        package = DIST / name
        (package / '使用说明.txt').write_text(help_text, encoding='utf-8-sig')
        shutil.copy2(ROOT / '更新日志.txt', package / '更新日志.txt')
        shutil.copy2(ROOT / 'packaging/发行检查.txt', package / '发行检查.txt')
        license_path = Path(sys.base_prefix) / 'LICENSE_PYTHON.txt'
        if license_path.is_file():
            shutil.copy2(license_path, package / 'LICENSE_PYTHON.txt')
        distributions = ['websockets'] if component == 'server' else [
            'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'python-mpv',
            'websockets', 'yt-dlp', 'segno', 'certifi', 'brotli', 'pycryptodomex', 'requests', 'urllib3', 'mutagen']
        versions = {'Python': sys.version.split()[0], **{p: metadata.version(p) for p in distributions}}
        (package / '依赖版本.json').write_text(json.dumps(versions, ensure_ascii=False, indent=2), encoding='utf-8')
        notices = ('随包依赖信息及许可证见_internal中的各*.dist-info目录。\n'
                   'Qt / PySide6: https://www.qt.io/qt-for-python\n'
                   'mpv: https://mpv.io/ ; python-mpv: https://github.com/jaseg/python-mpv\n'
                   'Python: https://www.python.org/ ; websockets: https://github.com/python-websockets/websockets\n'
                   'yt-dlp: https://github.com/yt-dlp/yt-dlp ; segno: https://github.com/heuer/segno\n'
                   'Microsoft C/C++运行库随应用部署，无需单独安装。\n')
        (package / '第三方依赖说明.txt').write_text(notices, encoding='utf-8-sig')
        print('Built: ' + str(package), flush=True)


def archive(output, names=None):
    import hashlib
    output.mkdir(parents=True, exist_ok=True)
    hashes = []
    for name in (names or (CLIENT_NAME, SERVER_NAME)):
        package = DIST / name
        target = output / (name + '.zip')
        if target.exists():
            raise FileExistsError(target)
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    if path.name in ('config.json', 'crash.log'):
                        continue
                    archive.write(path, path.relative_to(DIST))
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        hashes.append(digest + '  ' + target.name)
        print(str(target) + '  ' + str(target.stat().st_size) + ' bytes', flush=True)
    (output / ('SHA256-' + CLIENT_VERSION + '.txt')).write_text('\n'.join(hashes) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['build', 'archive'])
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'archives')
    args = parser.parse_args()
    build() if args.action == 'build' else archive(args.output)

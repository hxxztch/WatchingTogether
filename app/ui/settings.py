"""Version and GitHub update controls."""
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkProxyFactory,
                               QNetworkReply, QNetworkRequest)
from PySide6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.updates import RELEASES_API, RELEASES_FEED, RELEASES_PAGE, find_update
from app.version import CLIENT_VERSION
from app.diagnostics import record_action, recent_actions
from app.ui.shell import card, label


class SettingsPage(QWidget):
    update_available = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self._network = QNetworkAccessManager(self)
        self._check_reply = None
        self._check_source = ""
        self._manifest_reply = None
        self._download_reply = None
        self._output = None
        self._partial = None
        self._target = None
        self._hash = None
        self._release = None
        self._download_is_delta = False
        self._expected_digest = ""
        self._manifest_redirects = 0
        self._download_redirects = 0
        self._automatic = False
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 26, 32, 24)
        layout.setSpacing(22)
        layout.addWidget(label("设置", "heading"))
        version_card, version_layout = card("版本更新")
        version_layout.addWidget(label("当前版本：" + CLIENT_VERSION, "cardTitle"))
        self.status = label("尚未检查更新", "subtle", True)
        version_layout.addWidget(self.status)
        self.release_label = label("", "subtle", True)
        self.release_label.hide()
        version_layout.addWidget(self.release_label)
        self.diff_files = QTextEdit()
        self.diff_files.setReadOnly(True)
        self.diff_files.setMaximumHeight(220)
        self.diff_files.hide()
        version_layout.addWidget(self.diff_files)

        actions = QHBoxLayout()
        self.check_button = QPushButton("检查更新")
        self.check_button.clicked.connect(self.check_updates)
        actions.addWidget(self.check_button)
        self.download_button = QPushButton("下载更新")
        self.download_button.setObjectName("primary")
        self.download_button.hide()
        self.download_button.clicked.connect(self.download_update)
        actions.addWidget(self.download_button)
        self.install_button = QPushButton("安装更新并重启")
        self.install_button.setObjectName("primary")
        self.install_button.hide()
        self.install_button.clicked.connect(self.install_update)
        actions.addWidget(self.install_button)
        self.release_button = QPushButton("查看 GitHub 发布页")
        self.release_button.clicked.connect(self.open_release)
        actions.addWidget(self.release_button)
        actions.addStretch()
        version_layout.addLayout(actions)

        self.folder_button = QPushButton("打开下载文件夹")
        self.folder_button.hide()
        self.folder_button.clicked.connect(self.open_download_folder)
        version_layout.addWidget(self.folder_button)
        version_layout.addWidget(label(
            "便携版优先下载差异文件，在退出客户端后安装；源码运行时可下载完整便携包。",
            "subtle", True))
        layout.addWidget(version_card)
        layout.addStretch()

    def _request(self, url, timeout):
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(b"User-Agent", b"WatchingTogether-Updater")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute,
                             QNetworkRequest.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(timeout)
        return request

    @staticmethod
    def _redirect_target(reply, redirects):
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if status not in (301, 302, 303, 307, 308):
            return None
        target = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
        if not isinstance(target, QUrl) or target.isEmpty():
            raise ValueError("GitHub 未提供下载跳转地址")
        url = reply.url().resolved(target)
        host = url.host().lower()
        if (redirects >= 5 or url.scheme().lower() != "https" or
                not (host == "github.com" or host.endswith(".githubusercontent.com"))):
            raise ValueError("GitHub 返回了不安全的下载跳转")
        return url

    def check_updates(self, automatic=False):
        if self._closing or self._check_reply is not None or self._download_reply is not None:
            return
        self.check_button.setEnabled(False)
        self._automatic = automatic is True
        record_action("update.check", automatic=self._automatic)
        self.status.setText("正在从 GitHub 检查更新…")
        self._start_check(RELEASES_FEED, "static_feed")

    def _start_check(self, url, source):
        self._check_source = source
        reply = self._network.get(self._request(url, 12000))
        self._check_reply = reply
        reply.finished.connect(lambda: self._finish_check(reply))

    def _finish_check(self, reply):
        if reply is not self._check_reply:
            reply.deleteLater()
            return
        self._check_reply = None
        self.check_button.setEnabled(True)
        if self._closing:
            reply.deleteLater()
            return
        try:
            if reply.error() != QNetworkReply.NoError:
                raise OSError(reply.errorString())
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status != 200:
                raise OSError("HTTP {}".format(status))
            releases = json.loads(bytes(reply.readAll()).decode("utf-8"))
            if not isinstance(releases, list):
                raise ValueError("GitHub 返回了无效的发布信息")
            self._release = find_update(releases)
            logging.info("Update check success source=%s latest=%s", self._check_source,
                         self._release.tag if self._release else "current")
            if self._release is None:
                self.status.setText("已是当前通道的最新版本")
                self.release_label.hide()
                self.diff_files.hide()
                self.download_button.hide()
                self.install_button.hide()
                self.update_available.emit("")
            else:
                self.status.setText("发现新版本：" + self._release.tag)
                self.diff_files.hide()
                self.install_button.hide()
                has_delta = bool(getattr(sys, "frozen", False) and self._release.delta_url)
                self.release_label.setText("可用差异包：" + self._release.delta_name if has_delta else
                                           "完整便携包：" + self._release.asset_name)
                self.release_label.show()
                self.download_button.setText("下载差异更新" if has_delta else "下载完整便携包")
                self.download_button.show()
                self.update_available.emit(self._release.tag)
                if self._release.manifest_url:
                    self._load_manifest()
                if has_delta and self._automatic:
                    self.download_update()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            logging.warning("Update check failed source=%s http=%s error=%s recent_actions=%s",
                            self._check_source, status, exc, recent_actions())
            if self._check_source == "static_feed":
                record_action("update.check_fallback")
                self._start_check(RELEASES_API, "github_api")
                return
            remaining = bytes(reply.rawHeader(b"X-RateLimit-Remaining"))
            if status in (403, 429) and remaining == b"0":
                self.status.setText("GitHub 检查请求受限，请稍后再试。")
            elif status:
                self.status.setText("检查失败（HTTP {}），请稍后重试。".format(status))
            else:
                self.status.setText("检查失败，请确认网络连接后重试。")
        finally:
            reply.deleteLater()

    def _load_manifest(self):
        if self._manifest_reply is not None:
            self._manifest_reply.abort()
        self._manifest_redirects = 0
        reply = self._network.get(self._request(self._release.manifest_url, 12000))
        self._manifest_reply = reply
        reply.finished.connect(lambda: self._finish_manifest(reply))

    def _finish_manifest(self, reply):
        if reply is not self._manifest_reply:
            reply.deleteLater()
            return
        if not self._closing:
            try:
                target = self._redirect_target(reply, self._manifest_redirects)
                if target is not None:
                    self._manifest_redirects += 1
                    next_reply = self._network.get(self._request(target, 12000))
                    self._manifest_reply = next_reply
                    next_reply.finished.connect(lambda: self._finish_manifest(next_reply))
                    reply.deleteLater()
                    return
            except ValueError as exc:
                logging.warning("Invalid update manifest redirect: %s", exc)
                self._manifest_reply = None
                reply.deleteLater()
                return
        self._manifest_reply = None
        if not self._closing and reply.error() == QNetworkReply.NoError:
            try:
                manifest = json.loads(bytes(reply.readAll()).decode("utf-8"))
                if (manifest.get("from_version") == CLIENT_VERSION and
                        manifest.get("to_version") == self._release.tag):
                    changed = [item["path"] for item in manifest["files"]]
                    removed = [item["path"] for item in manifest["removed"]]
                    self.diff_files.setPlainText("更新文件（{}）：\n{}\n\n移除文件（{}）：\n{}".format(
                        len(changed), "\n".join(changed) or "无",
                        len(removed), "\n".join(removed) or "无"))
                    self.diff_files.show()
            except (ValueError, TypeError, KeyError):
                logging.warning("Invalid update manifest")
        reply.deleteLater()

    def download_update(self):
        if self._closing or self._download_reply is not None or self._release is None:
            return
        self._download_is_delta = bool(getattr(sys, "frozen", False) and self._release.delta_url)
        record_action("update.download", version=self._release.tag,
                      kind="delta" if self._download_is_delta else "full")
        self.install_button.hide()
        asset_name = self._release.delta_name if self._download_is_delta else self._release.asset_name
        asset_url = self._release.delta_url if self._download_is_delta else self._release.asset_url
        self._expected_digest = self._release.delta_digest if self._download_is_delta else self._release.digest
        if self._download_is_delta and not self._expected_digest.startswith("sha256:"):
            self.status.setText("差异包缺少 SHA256 校验值，请从 GitHub 发布页获取更新。")
            return
        folder = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        directory = Path(folder or str(Path.home() / "Downloads")) / "WatchingTogether"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._target = directory / asset_name
            self._partial = directory / (asset_name + ".part-" + str(os.getpid()))
            self._output = self._partial.open("wb")
        except OSError as exc:
            logging.warning("Update download could not start: %s", exc)
            self.status.setText("无法创建下载文件，请检查下载目录。")
            return
        self._hash = hashlib.sha256()
        self._download_redirects = 0
        self.download_button.setEnabled(False)
        self.status.setText("正在下载 " + asset_name + "…")
        self._start_download_request(asset_url)

    def _start_download_request(self, url):
        reply = self._network.get(self._request(url, 120000))
        self._download_reply = reply
        reply.readyRead.connect(lambda: self._read_download(reply))
        reply.downloadProgress.connect(self._download_progress)
        reply.finished.connect(lambda: self._finish_download(reply))

    def _read_download(self, reply):
        if reply is not self._download_reply or self._output is None:
            return
        if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) in (301, 302, 303, 307, 308):
            reply.readAll()
            return
        try:
            data = bytes(reply.readAll())
            self._output.write(data)
            self._hash.update(data)
        except OSError as exc:
            logging.warning("Update download write failed: %s", exc)
            reply.abort()

    def _download_progress(self, received, total):
        if total > 0:
            self.status.setText("正在下载：{}%".format(int(received * 100 / total)))

    def _finish_download(self, reply):
        if reply is not self._download_reply:
            reply.deleteLater()
            return
        self._read_download(reply)
        redirect_error = None
        if not self._closing:
            try:
                target = self._redirect_target(reply, self._download_redirects)
                if target is not None:
                    self._output.seek(0)
                    self._output.truncate(0)
                    self._hash = hashlib.sha256()
                    self._download_redirects += 1
                    self._start_download_request(target)
                    reply.deleteLater()
                    return
            except (OSError, ValueError) as exc:
                redirect_error = exc
        self._download_reply = None
        self.download_button.setEnabled(True)
        if self._output is not None:
            self._output.close()
            self._output = None
        try:
            if self._closing:
                return
            if redirect_error is not None:
                raise redirect_error
            if reply.error() != QNetworkReply.NoError:
                raise OSError(reply.errorString())
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if status != 200:
                raise OSError("GitHub 下载失败（HTTP {}）".format(status))
            expected = self._expected_digest
            if expected and expected.startswith("sha256:") and self._hash.hexdigest() != expected[7:]:
                raise ValueError("下载文件校验失败")
            os.replace(str(self._partial), str(self._target))
            self.status.setText("下载完成：" + self._target.name)
            logging.info("Update download verified version=%s kind=%s bytes=%s",
                         self._release.tag, "delta" if self._download_is_delta else "full",
                         self._target.stat().st_size)
            self.folder_button.show()
            self.install_button.setVisible(self._download_is_delta)
        except (OSError, ValueError) as exc:
            logging.warning("Update download failed: %s", exc)
            self.status.setText("下载失败：" + str(exc))
        finally:
            if self._partial and self._partial.exists():
                try:
                    self._partial.unlink()
                except OSError:
                    pass
            reply.deleteLater()

    def install_update(self):
        if not self._download_is_delta or self._target is None or not self._target.is_file():
            return
        record_action("update.install", from_version=CLIENT_VERSION, to_version=self._release.tag)
        script = Path(getattr(sys, "_MEIPASS", "")) / "updater" / "apply_update.ps1"
        if not script.is_file():
            self.status.setText("更新程序缺失，请下载完整便携包。")
            return
        try:
            helper_dir = Path(tempfile.mkdtemp(prefix="wt-update-helper-"))
            helper = helper_dir / "apply_update.ps1"
            shutil.copyfile(str(script), str(helper))
            subprocess.Popen([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(helper), "-InstallDir", str(Path(sys.executable).resolve().parent),
                "-DeltaZip", str(self._target), "-FromVersion", CLIENT_VERSION,
                "-ToVersion", self._release.tag, "-TargetProcessId", str(os.getpid()),
            ], creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            logging.warning("Could not start updater: %s", exc)
            self.status.setText("无法启动更新程序，请手动下载完整便携包。")
            return
        # MiniPlayer's close button returns to the theatre; closeAllWindows can
        # stop at that ignored close event and leave the updater waiting forever.
        self.window().close()
        QApplication.quit()

    def open_release(self):
        QDesktopServices.openUrl(QUrl(self._release.page_url if self._release else RELEASES_PAGE))

    def open_download_folder(self):
        if self._target is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._target.parent)))

    def stop(self):
        self._closing = True
        if self._check_reply is not None:
            self._check_reply.abort()
        if self._manifest_reply is not None:
            self._manifest_reply.abort()
        if self._download_reply is not None:
            self._download_reply.abort()

import sys
import os
import subprocess
import time
import shutil
import threading

import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QTextEdit,
    QLabel, QStatusBar, QMessageBox, QTabWidget, QComboBox, QProgressBar
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

MIRRORS = {
    "清华源": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/",
    "中科大": "https://mirrors.ustc.edu.cn/ubuntu/",
    "阿里云": "https://mirrors.aliyun.com/ubuntu/",
    "华为云": "https://mirrors.huaweicloud.com/ubuntu/",
    "官方源": "http://archive.ubuntu.com/ubuntu/",
}

SPEED_TEST_FILE = "dists/noble/InRelease"
HEADERS = {"User-Agent": "curl/8.5.0"}


def detect_distro():
    try:
        with open("/etc/os-release") as f:
            info = {}
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v.strip('"')
        return info.get("PRETTY_NAME", info.get("NAME", "未知系统"))
    except Exception:
        return "未知系统"


class SearchThread(QThread):
    result_ready = pyqtSignal(str, list)
    finished_all = pyqtSignal()

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        for name, fn in [("apt", self.search_apt), ("snap", self.search_snap), ("flatpak", self.search_flatpak)]:
            try:
                results = fn(self.keyword)
                self.result_ready.emit(name, results)
            except Exception:
                self.result_ready.emit(name, [])

    def search_apt(self, kw):
        result = subprocess.run(["apt-cache", "search", kw], capture_output=True, text=True, timeout=15)
        pkgs = []
        for line in result.stdout.strip().split("\n"):
            if " - " in line:
                name, desc = line.split(" - ", 1)
                pkgs.append((name.strip(), desc.strip()))
        return pkgs

    def search_snap(self, kw):
        result = subprocess.run(["snap", "find", kw], capture_output=True, text=True, timeout=15)
        pkgs = []
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    desc = " ".join(parts[1:]) if len(parts) > 2 else parts[1]
                    pkgs.append((name, desc))
        return pkgs

    def search_flatpak(self, kw):
        try:
            subprocess.run(
                ["flatpak", "remote-add", "--if-not-exists", "flathub",
                 "https://flathub.org/repo/flathub.flatpakrepo"],
                capture_output=True, timeout=10
            )
        except Exception:
            pass
        result = subprocess.run(
            ["flatpak", "search", kw, "--columns=name,description"],
            capture_output=True, text=True, timeout=15
        )
        pkgs = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                pkgs.append((parts[0].strip(), parts[1].strip()))
        return pkgs


class SpeedTestThread(QThread):
    speed_result = pyqtSignal(str, float)
    speed_done = pyqtSignal(str, float)

    def run(self):
        best_name, best_speed = "", 0.0
        for name, url in MIRRORS.items():
            try:
                test_url = url + SPEED_TEST_FILE
                r = requests.get(test_url, timeout=10, stream=True, headers=HEADERS)
                r.raise_for_status()
                total = 0
                start = time.time()
                for chunk in r.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if time.time() - start > 5:
                        break
                elapsed = time.time() - start
                r.close()
                speed = total / elapsed / 1024 / 1024 if elapsed > 0 else 0
                self.speed_result.emit(name, speed)
                if speed > best_speed:
                    best_speed = speed
                    best_name = name
            except Exception:
                self.speed_result.emit(name, 0)
        self.speed_done.emit(best_name, best_speed)


class InstallThread(QThread):
    output = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, cmd):
        super().__init__()
        self.cmd = cmd

    def run(self):
        try:
            proc = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                self.output.emit(line.rstrip())
            proc.wait()
            self.finished.emit(proc.returncode == 0)
        except Exception as e:
            self.output.emit(f"错误: {e}")
            self.finished.emit(False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("软件安装器 v0.2")
        self.setMinimumSize(800, 600)
        self.search_thread = None
        self.speed_thread = None
        self.install_thread = None
        self.best_mirror = ""
        self.best_speed = 0.0
        self.init_ui()
        self.statusBar().showMessage(f"检测到 {detect_distro()}")

    def closeEvent(self, event):
        for t in [self.search_thread, self.speed_thread, self.install_thread]:
            if t and t.isRunning():
                t.quit()
                t.wait(2000)
        event.accept()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        tabs = QTabWidget()
        tabs.addTab(self.create_search_tab(), "搜索安装")
        tabs.addTab(self.create_mirror_tab(), "镜像源")
        tabs.addTab(self.create_local_tab(), "本地包")
        tabs.addTab(self.create_setup_tab(), "一键装机")
        layout.addWidget(tabs)

    def create_search_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入软件名搜索...")
        self.search_input.returnPressed.connect(self.do_search)
        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.do_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)

        self.result_list = QListWidget()
        self.result_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self.result_list)

        btn_layout = QHBoxLayout()
        self.install_btn = QPushButton("一键安装")
        self.install_btn.clicked.connect(self.do_install)
        btn_layout.addWidget(self.install_btn)
        layout.addLayout(btn_layout)

        self.search_log = QTextEdit()
        self.search_log.setReadOnly(True)
        self.search_log.setMaximumHeight(120)
        layout.addWidget(self.search_log)

        return widget

    def create_mirror_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel("测试各镜像源速度，选择最快的切换")
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        self.mirror_list = QListWidget()
        layout.addWidget(self.mirror_list)

        btn_layout = QHBoxLayout()
        self.speed_btn = QPushButton("测速")
        self.speed_btn.clicked.connect(self.do_speed_test)
        self.switch_btn = QPushButton("切换到最快源")
        self.switch_btn.clicked.connect(self.do_switch_mirror)
        self.switch_btn.setEnabled(False)
        btn_layout.addWidget(self.speed_btn)
        btn_layout.addWidget(self.switch_btn)
        layout.addLayout(btn_layout)

        self.mirror_progress = QProgressBar()
        self.mirror_progress.setVisible(False)
        layout.addWidget(self.mirror_progress)

        self.mirror_log = QTextEdit()
        self.mirror_log.setReadOnly(True)
        self.mirror_log.setMaximumHeight(100)
        layout.addWidget(self.mirror_log)

        return widget

    def create_local_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel("支持 .deb / .rpm / .AppImage / .flatpak / .exe (Wine)")
        info.setStyleSheet("color: gray;")
        layout.addWidget(info)

        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("拖入文件或输入路径...")
        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self.browse_file)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        self.local_install_btn = QPushButton("安装")
        self.local_install_btn.clicked.connect(self.do_local_install)
        layout.addWidget(self.local_install_btn)

        self.local_log = QTextEdit()
        self.local_log.setReadOnly(True)
        layout.addWidget(self.local_log)

        return widget

    def create_setup_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        presets = [
            ("包管理器", "snapd flatpak"),
            ("基础工具", "git curl wget vim htop tree unzip build-essential"),
            ("Python 开发", "python3 python3-pip python3-venv"),
            ("Node.js 开发", "nodejs npm"),
            ("C/C++ 开发", "gcc g++ gdb cmake make"),
            ("Docker", "docker.io"),
        ]

        for name, pkgs in presets:
            row = QHBoxLayout()
            btn = QPushButton(f"安装 {name}")
            btn.clicked.connect(lambda checked, p=pkgs, n=name: self.do_preset_install(n, p))
            label = QLabel(pkgs)
            label.setStyleSheet("color: gray; font-size: 11px;")
            row.addWidget(btn)
            row.addWidget(label)
            layout.addLayout(row)

        layout.addStretch()

        self.setup_log = QTextEdit()
        self.setup_log.setReadOnly(True)
        self.setup_log.setMaximumHeight(150)
        layout.addWidget(self.setup_log)

        return widget

    def log(self, box, msg):
        box.append(f"> {msg}")

    def do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            return
        self.search_btn.setEnabled(False)
        self.result_list.clear()
        self.log(self.search_log, f"搜索: {keyword}")

        self.search_thread = SearchThread(keyword)
        self.search_thread.result_ready.connect(self.on_search_result)
        self.search_thread.finished.connect(lambda: self.search_btn.setEnabled(True))
        self.search_thread.start()

    def on_search_result(self, src, results):
        src_colors = {"apt": QColor(0, 200, 0), "snap": QColor(200, 200, 0), "flatpak": QColor(0, 200, 200)}
        src_icons = {"apt": "◆", "snap": "●", "flatpak": "▲"}
        for name, desc in results:
            display = f"{src_icons.get(src, '·')} [{src}] {name} - {desc}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, (name, src))
            item.setForeground(src_colors.get(src, QColor(255, 255, 255)))
            self.result_list.addItem(item)
        self.log(self.search_log, f"{src}: 找到 {len(results)} 条")

    def do_install(self):
        selected = self.result_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选择要安装的软件")
            return
        for item in selected:
            name, src = item.data(Qt.ItemDataRole.UserRole)
            if src == "apt":
                cmd = ["pkexec", "apt", "install", "-y", name]
            elif src == "snap":
                cmd = ["pkexec", "snap", "install", name]
            elif src == "flatpak":
                cmd = ["pkexec", "flatpak", "install", "-y", "flathub", name]
            else:
                continue
            self.log(self.search_log, f"安装 {name} ({src})...")
            self.run_cmd(cmd, self.search_log)

    def do_speed_test(self):
        self.speed_btn.setEnabled(False)
        self.mirror_list.clear()
        self.mirror_progress.setVisible(True)
        self.mirror_progress.setRange(0, len(MIRRORS))
        self.mirror_progress.setValue(0)
        self.log(self.mirror_log, "测速中...")

        self.speed_thread = SpeedTestThread()
        self.speed_thread.speed_result.connect(self.on_speed_result)
        self.speed_thread.speed_done.connect(self.on_speed_done)
        self.speed_thread.start()

    def on_speed_result(self, name, speed):
        item = QListWidgetItem(f"{name}: {speed:.2f} MB/s")
        if speed >= 2:
            item.setForeground(QColor(0, 200, 0))
        elif speed >= 1:
            item.setForeground(QColor(200, 200, 0))
        else:
            item.setForeground(QColor(200, 0, 0))
        self.mirror_list.addItem(item)
        self.mirror_progress.setValue(self.mirror_progress.value() + 1)

    def on_speed_done(self, best_name, best_speed):
        self.best_mirror = best_name
        self.best_speed = best_speed
        if best_name:
            self.statusBar().showMessage(f"最快: {best_name} ({best_speed:.2f} MB/s)")
            self.switch_btn.setEnabled(True)
            self.log(self.mirror_log, f"最快: {best_name} ({best_speed:.2f} MB/s)")
        else:
            self.log(self.mirror_log, "测速完成，无可用镜像")
        self.speed_btn.setEnabled(True)
        self.mirror_progress.setVisible(False)

    def do_switch_mirror(self):
        if not self.best_mirror:
            return
        reply = QMessageBox.question(
            self, "确认切换",
            f"将切换到 {self.best_mirror}，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        mirror_url = MIRRORS[self.best_mirror]
        codename = "jammy"
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("VERSION_CODENAME="):
                        codename = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass

        content = f"deb {mirror_url} {codename} main restricted universe multiverse\n"
        content += f"deb {mirror_url} {codename}-updates main restricted universe multiverse\n"
        content += f"deb {mirror_url} {codename}-backports main restricted universe multiverse\n"
        content += f"deb http://security.ubuntu.com/ubuntu/ {codename}-security main restricted universe multiverse\n"

        tmp = "/tmp/sources.list.new"
        with open(tmp, "w") as f:
            f.write(content)

        backup = "/etc/apt/sources.list.backup"
        cmds = []
        if not os.path.exists(backup):
            cmds.append(["pkexec", "cp", "/etc/apt/sources.list", backup])
        cmds.append(["pkexec", "cp", tmp, "/etc/apt/sources.list"])
        cmds.append(["pkexec", "apt", "update"])

        self.log(self.mirror_log, f"切换到 {self.best_mirror}...")
        for cmd in cmds:
            self.run_cmd(cmd, self.mirror_log)
        self.log(self.mirror_log, "切换完成")

    def browse_file(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择软件包", os.path.expanduser("~"),
            "软件包 (*.deb *.rpm *.AppImage *.flatpak *.flatpakref *.exe);;所有文件 (*)"
        )
        if path:
            self.path_input.setText(path)

    def do_local_install(self):
        path = self.path_input.text().strip()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "提示", "请输入有效的文件路径")
            return

        ext = os.path.splitext(path)[1].lower()
        distro = detect_distro().lower()
        is_deb = any(x in distro for x in ["ubuntu", "debian", "mint"])

        if ext == ".deb":
            if not is_deb:
                reply = QMessageBox.question(
                    self, "兼容性提示",
                    f"当前系统 ({detect_distro()}) 不原生支持 .deb\n是否尝试安装？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            self.run_cmd(["pkexec", "apt", "install", "-y", path], self.local_log)

        elif ext == ".rpm":
            if is_deb:
                reply = QMessageBox.question(
                    self, "兼容性提示",
                    f"当前系统 ({detect_distro()}) 不原生支持 .rpm\n是否用 alien 转换安装？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self.run_cmd(["pkexec", "apt", "install", "-y", "alien"], self.local_log)
                tmp = path.replace(".rpm", ".deb")
                self.run_cmd(["pkexec", "alien", "-d", "--to-deb", path, "-o", tmp], self.local_log)
                if os.path.exists(tmp):
                    self.run_cmd(["pkexec", "apt", "install", "-y", tmp], self.local_log)
                    os.remove(tmp)
            else:
                self.run_cmd(["pkexec", "rpm", "-i", path], self.local_log)

        elif ext in [".appimage"] or "appimage" in path.lower():
            dest = os.path.expanduser(f"~/.local/bin/{os.path.basename(path)}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(path, dest)
            os.chmod(dest, 0o755)
            self.log(self.local_log, f"已复制到 {dest}")
            self.log(self.local_log, f"可直接运行: {dest}")

        elif ext in [".flatpak", ".flatpakref"]:
            self.run_cmd(
                ["flatpak", "remote-add", "--if-not-exists", "flathub",
                 "https://flathub.org/repo/flathub.flatpakrepo"],
                self.local_log
            )
            self.run_cmd(["pkexec", "flatpak", "install", "-y", path], self.local_log)

        elif ext == ".exe":
            reply = QMessageBox.question(
                self, "Windows 兼容性提示",
                "Wine 运行 .exe 的注意事项：\n\n"
                "• 带 ACE 反作弊的游戏完全无法运行\n"
                "• Windows 游戏可能不兼容或性能较差\n"
                "• 部分专业软件可能无法正常工作\n"
                "• 老游戏和简单工具兼容性较好\n\n"
                "是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            has_wine = subprocess.run(["which", "wine"], capture_output=True).returncode == 0
            if not has_wine:
                self.log(self.local_log, "安装 Wine...")
                self.run_cmd(["pkexec", "apt", "install", "-y", "wine"], self.local_log)
            self.log(self.local_log, f"启动 {os.path.basename(path)}...")
            subprocess.Popen(["wine", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        else:
            QMessageBox.warning(self, "提示", f"不支持的格式: {ext}")

    def do_preset_install(self, name, pkgs):
        reply = QMessageBox.question(
            self, "确认安装",
            f"安装 {name}：\n{pkgs}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.run_cmd(["pkexec", "apt", "install", "-y"] + pkgs.split(), self.setup_log)

    def run_cmd(self, cmd, log_box):
        self.install_thread = InstallThread(cmd)
        self.install_thread.output.connect(lambda msg: self.log(log_box, msg))
        self.install_thread.start()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont()
    font.setPointSize(10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()

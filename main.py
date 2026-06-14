import subprocess
import time
import os
import shutil
import sys
import threading

import requests

MIRRORS = {
    "清华源": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/",
    "中科大": "https://mirrors.ustc.edu.cn/ubuntu/",
    "阿里云": "https://mirrors.aliyun.com/ubuntu/",
    "华为云": "https://mirrors.huaweicloud.com/ubuntu/",
    "官方源": "http://archive.ubuntu.com/ubuntu/",
}

SPEED_TEST_FILE = "dists/noble/InRelease"
HEADERS = {"User-Agent": "curl/8.5.0"}

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

lock = threading.Lock()
total_count = 0


def clear():
    os.system("clear" if os.name != "nt" else "cls")


def banner():
    print(f"""{CYAN}{BOLD}
  ╔══════════════════════════════════════════╗
  ║        {RESET}{BOLD}📦 软件安装器 v0.1{CYAN}{BOLD}               ║
  ╚══════════════════════════════════════════╝{RESET}""")


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


def search_apt(keyword):
    try:
        result = subprocess.run(
            ["apt-cache", "search", keyword],
            capture_output=True, text=True, timeout=15
        )
        packages = []
        for line in result.stdout.strip().split("\n"):
            if " - " in line:
                name, desc = line.split(" - ", 1)
                packages.append((name.strip(), desc.strip(), "apt"))
        return packages
    except Exception:
        return []


def search_snap(keyword):
    try:
        result = subprocess.run(
            ["snap", "find", keyword],
            capture_output=True, text=True, timeout=15
        )
        packages = []
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    desc = " ".join(parts[1:]) if len(parts) > 2 else parts[1]
                    packages.append((name, desc, "snap"))
        return packages
    except Exception:
        return []


def search_flatpak(keyword):
    try:
        subprocess.run(
            ["flatpak", "remote-add", "--if-not-exists", "flathub",
             "https://flathub.org/repo/flathub.flatpakrepo"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["flatpak", "search", keyword, "--columns=name,description"],
            capture_output=True, text=True, timeout=15
        )
        packages = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                packages.append((parts[0].strip(), parts[1].strip(), "flatpak"))
        return packages
    except Exception:
        return []


def print_result(idx, name, desc, src):
    src_colors = {"apt": GREEN, "snap": YELLOW, "flatpak": CYAN}
    src_icons = {"apt": "◆", "snap": "●", "flatpak": "▲"}
    color = src_colors.get(src, RESET)
    icon = src_icons.get(src, "·")
    desc_short = desc[:45] + "..." if len(desc) > 45 else desc
    print(f"  {DIM}{idx:>3}{RESET}  {color}{icon} {src:<8}{RESET} {BOLD}{name:<25}{RESET} {DIM}{desc_short}{RESET}")


def search_with_progress(keyword, src_name, search_fn):
    global total_count
    packages = search_fn(keyword)
    with lock:
        for name, desc, src in packages:
            total_count += 1
            print_result(total_count, name, desc, src)
    return packages


def test_mirrors():
    results = {}
    print(f"\n{BOLD}  镜像测速中...{RESET}\n")
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
            if elapsed > 0 and total > 0:
                speed = total / elapsed / 1024 / 1024
            else:
                speed = 0
            results[name] = speed
            bar_len = int(speed * 10)
            bar = "█" * min(bar_len, 30)
            color = GREEN if speed >= 2 else (YELLOW if speed >= 1 else RED)
            print(f"    {CYAN}{name:>6}{RESET}  {color}{bar:<30}{RESET} {speed:.2f} MB/s")
            time.sleep(0.2)
        except Exception as e:
            results[name] = 0
            print(f"    {CYAN}{name:>6}{RESET}  {RED}{'失败':<30}{RESET} {DIM}{e}{RESET}")
    return results


def switch_mirror(mirror_name, mirror_url):
    sources_path = "/etc/apt/sources.list"
    try:
        codename = "jammy"
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("VERSION_CODENAME="):
                    codename = line.split("=", 1)[1].strip()
                    break
        content = f"deb {mirror_url} {codename} main restricted universe multiverse\n"
        content += f"deb {mirror_url} {codename}-updates main restricted universe multiverse\n"
        content += f"deb {mirror_url} {codename}-backports main restricted universe multiverse\n"
        content += f"deb http://security.ubuntu.com/ubuntu/ {codename}-security main restricted universe multiverse\n"
        print(f"\n  {YELLOW}codename: {codename}{RESET}")
        print(f"  {YELLOW}新源:{RESET}")
        for line in content.strip().split("\n"):
            print(f"    {DIM}{line}{RESET}")
        print(f"\n  {DIM}(CLI模式不实际修改文件，需GUI模式配合pkexec){RESET}")
        return True
    except Exception as e:
        print(f"  {RED}失败: {e}{RESET}")
        return False


def search_all_parallel(keyword):
    global total_count
    total_count = 0

    print(f"\n  {BOLD}搜索: {keyword}{RESET}\n")
    print(f"  {DIM}{'─'*68}{RESET}")
    print(f"  {DIM}{'#':>3}  {'来源':<10}  {'包名':<25}  描述{RESET}")
    print(f"  {DIM}{'─'*68}{RESET}")

    results = {"apt": [], "snap": [], "flatpak": []}
    event = threading.Event()

    def run_search(name, fn):
        pkgs = search_with_progress(keyword, name, fn)
        results[name] = pkgs
        event.set()

    threads = []
    for name, fn in [("apt", search_apt), ("snap", search_snap), ("flatpak", search_flatpak)]:
        t = threading.Thread(target=run_search, args=(name, fn), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=30)

    print(f"  {DIM}{'─'*68}{RESET}")
    total = sum(len(v) for v in results.values())
    apt_n = len(results["apt"])
    snap_n = len(results["snap"])
    fp_n = len(results["flatpak"])
    print(f"  {DIM}共 {total} 条  {GREEN}apt:{apt_n}{RESET}  {YELLOW}snap:{snap_n}{RESET}  {CYAN}flatpak:{fp_n}{RESET}")


def one_click_setup():
    print(f"\n  {BOLD}一键装机{RESET}\n")
    envs = [
        ("1", "包管理器", ["snapd", "flatpak"], [], []),
        ("2", "基础工具", ["git", "curl", "wget", "vim", "htop", "tree", "unzip", "build-essential"], [], []),
        ("3", "Python 开发", ["python3", "python3-pip", "python3-venv"], [], []),
        ("4", "Node.js 开发", ["nodejs", "npm"], [], []),
        ("5", "C/C++ 开发", ["gcc", "g++", "gdb", "cmake", "make"], [], []),
        ("6", "Docker", ["docker.io"], ["docker"], []),
        ("7", "浏览器", [], [], ["org.mozilla.firefox", "com.google.Chrome"]),
        ("8", "办公套件", [], ["libreoffice"], []),
        ("9", "多媒体", ["vlc", "ffmpeg"], ["vlc"], []),
        ("0", "全部安装", None, None, None),
    ]

    def pad(s, width):
        w = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in s)
        return s + " " * max(0, width - w)

    def m(ok):
        return "✓" if ok else "-"

    print(f"  {DIM}{'─'*56}{RESET}")
    print(f"  {'#':>3}  {pad('名称', 14)} apt    snap   flatpak")
    print(f"  {DIM}{'─'*56}{RESET}")
    for num, name, apt_pkgs, snap_pkgs, flat_pkgs in envs:
        print(f"  {BOLD}{num:>3}{RESET}  {pad(name, 14)}  {m(apt_pkgs):<6}{m(snap_pkgs):<6}{m(flat_pkgs)}")
    print(f"  {DIM}{'─'*56}{RESET}")

    choice = input(f"  {BOLD}❯{RESET} ").strip()
    selected = None
    for num, name, apt_pkgs, snap_pkgs, flat_pkgs in envs:
        if choice == num:
            selected = (name, apt_pkgs, snap_pkgs, flat_pkgs)
            break
    if not selected:
        print(f"  {RED}无效选项{RESET}")
        return

    name, apt_pkgs, snap_pkgs, flat_pkgs = selected
    if apt_pkgs is None:
        apt_pkgs = []
        snap_pkgs = []
        flat_pkgs = []
        for _, _, a, s, f in envs:
            if a: apt_pkgs.extend(a)
            if s: snap_pkgs.extend(s)
            if f: flat_pkgs.extend(f)
        name = "全部"

    print(f"\n  {YELLOW}安装 {name}:{RESET}")
    if apt_pkgs:
        print(f"    {GREEN}apt:{RESET} {DIM}{' '.join(apt_pkgs)}{RESET}")
    if snap_pkgs:
        print(f"    {YELLOW}snap:{RESET} {DIM}{' '.join(snap_pkgs)}{RESET}")
    if flat_pkgs:
        print(f"    {CYAN}flatpak:{RESET} {DIM}{' '.join(flat_pkgs)}{RESET}")

    confirm = input(f"\n  确认安装? {YELLOW}[y/N]{RESET} ").strip().lower()
    if confirm != "y":
        print(f"  {DIM}已取消{RESET}")
        return

    print(f"\n  {BOLD}开始安装...{RESET}\n")
    ok = True

    if apt_pkgs:
        print(f"  {GREEN}▸ 安装 apt 包...{RESET}")
        result = subprocess.run(
            ["pkexec", "apt", "install", "-y"] + apt_pkgs,
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  {GREEN}  ✓ apt 安装完成{RESET}")
        else:
            print(f"  {RED}  ✗ apt 安装失败{RESET}")
            ok = False

    if snap_pkgs:
        print(f"  {YELLOW}▸ 安装 snap 包...{RESET}")
        for pkg in snap_pkgs:
            result = subprocess.run(
                ["pkexec", "snap", "install", pkg],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  {YELLOW}  ✓ {pkg}{RESET}")
            else:
                print(f"  {RED}  ✗ {pkg}{RESET}")
                ok = False

    if flat_pkgs:
        print(f"  {CYAN}▸ 安装 flatpak 包...{RESET}")
        subprocess.run(
            ["flatpak", "remote-add", "--if-not-exists", "flathub",
             "https://flathub.org/repo/flathub.flatpakrepo"],
            capture_output=True, timeout=10
        )
        for pkg in flat_pkgs:
            result = subprocess.run(
                ["pkexec", "flatpak", "install", "-y", "flathub", pkg],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  {CYAN}  ✓ {pkg}{RESET}")
            else:
                print(f"  {RED}  ✗ {pkg}{RESET}")
                ok = False

    if ok:
        print(f"\n  {GREEN}{BOLD}✓ {name} 全部安装完成{RESET}")
    else:
        print(f"\n  {YELLOW}{BOLD}⚠ 部分安装失败{RESET}")


def install_local_package():
    distro_info = detect_distro().lower()
    is_deb_based = any(x in distro_info for x in ["ubuntu", "debian", "linux mint", "pop!_os", "deepin"])
    is_rpm_based = any(x in distro_info for x in ["fedora", "red hat", "centos", "rhel", "opensuse", "manjaro"])

    print(f"\n  {BOLD}安装本地软件包{RESET}\n")
    print(f"  {DIM}当前系统:{RESET} {BOLD}{detect_distro()}{RESET}")
    if is_deb_based:
        print(f"  {DIM}包格式:{RESET} {GREEN}.deb{RESET} (原生) / {YELLOW}.rpm{RESET} (需转换) / {CYAN}.AppImage{RESET} / {MAGENTA}.flatpak{RESET} / {BLUE}.exe{RESET} (Wine)")
    elif is_rpm_based:
        print(f"  {DIM}包格式:{RESET} {YELLOW}.rpm{RESET} (原生) / {GREEN}.deb{RESET} (需转换) / {CYAN}.AppImage{RESET} / {MAGENTA}.flatpak{RESET} / {BLUE}.exe{RESET} (Wine)")
    else:
        print(f"  {DIM}包格式:{RESET} {CYAN}.AppImage{RESET} / {MAGENTA}.flatpak{RESET} / {BLUE}.exe{RESET} (Wine)")
    print(f"\n  {DIM}拖入文件路径，或手动输入路径:{RESET}")
    path = input(f"  {BOLD}❯{RESET} ").strip().strip("'\"")
    if not path:
        print(f"  {RED}未输入路径{RESET}")
        return
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        print(f"  {RED}文件不存在: {path}{RESET}")
        return

    filename = os.path.basename(path)
    ext = os.path.splitext(filename)[1].lower()

    print(f"\n  {BOLD}文件:{RESET} {filename}")

    if ext == ".deb":
        if is_rpm_based:
            print(f"  {YELLOW}⚠ 警告: 当前系统为 {detect_distro()}，不原生支持 .deb 包{RESET}")
            confirm = input(f"  是否尝试用 alien 转换安装? {YELLOW}[y/N]{RESET} ").strip().lower()
            if confirm != "y":
                print(f"  {DIM}已取消{RESET}")
                return
            print(f"  {YELLOW}使用 alien 转换...{RESET}")
            has_alien = subprocess.run(["which", "alien"], capture_output=True).returncode == 0
            if not has_alien:
                print(f"  {RED}未安装 alien，请先运行: dnf install alien{RESET}")
                return
            tmp = f"/tmp/{os.path.splitext(filename)[0]}.rpm"
            r = subprocess.run(["pkexec", "alien", "-r", "--to-rpm", path, "-o", tmp],
                               capture_output=True, text=True)
            if r.returncode == 0 and os.path.exists(tmp):
                r2 = subprocess.run(["pkexec", "rpm", "-i", tmp],
                                    capture_output=True, text=True)
                os.remove(tmp)
                if r2.returncode == 0:
                    print(f"  {GREEN}{BOLD}✓ 安装成功{RESET}")
                else:
                    print(f"  {RED}✗ 安装失败{RESET}")
            else:
                print(f"  {RED}转换失败{RESET}")
        else:
            print(f"  {GREEN}检测到 .deb 包，使用 apt 安装...{RESET}")
            result = subprocess.run(
                ["pkexec", "apt", "install", "-y", path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  {GREEN}{BOLD}✓ 安装成功{RESET}")
            else:
                print(f"  {RED}✗ 安装失败{RESET}")
                if result.stderr:
                    for line in result.stderr.strip().split("\n")[-3:]:
                        print(f"    {DIM}{line}{RESET}")

    elif ext == ".rpm":
        if is_deb_based:
            print(f"  {YELLOW}⚠ 警告: 当前系统为 {detect_distro()}，不原生支持 .rpm 包{RESET}")
            confirm = input(f"  是否尝试用 alien 转换安装? {YELLOW}[y/N]{RESET} ").strip().lower()
            if confirm != "y":
                print(f"  {DIM}已取消{RESET}")
                return
            has_alien = subprocess.run(["which", "alien"], capture_output=True).returncode == 0
            if not has_alien:
                print(f"  {YELLOW}未安装 alien，正在安装...{RESET}")
                subprocess.run(["pkexec", "apt", "install", "-y", "alien"], capture_output=True)
                has_alien = subprocess.run(["which", "alien"], capture_output=True).returncode == 0
            if has_alien:
                print(f"  {DIM}使用 alien 转换为 deb...{RESET}")
                tmp = f"/tmp/{os.path.splitext(filename)[0]}.deb"
                r = subprocess.run(["pkexec", "alien", "-d", "--to-deb", path, "-o", tmp],
                                   capture_output=True, text=True)
                if r.returncode == 0 and os.path.exists(tmp):
                    r2 = subprocess.run(["pkexec", "apt", "install", "-y", tmp],
                                        capture_output=True, text=True)
                    os.remove(tmp)
                    if r2.returncode == 0:
                        print(f"  {GREEN}{BOLD}✓ 安装成功{RESET}")
                    else:
                        print(f"  {RED}✗ 安装失败{RESET}")
                else:
                    print(f"  {RED}转换失败{RESET}")
            else:
                print(f"  {RED}无法安装 alien{RESET}")
        else:
            print(f"  {YELLOW}检测到 .rpm 包，使用 rpm 安装...{RESET}")
            result = subprocess.run(
                ["pkexec", "rpm", "-i", path],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  {GREEN}{BOLD}✓ 安装成功{RESET}")
            else:
                print(f"  {RED}✗ 安装失败{RESET}")
                if result.stderr:
                    for line in result.stderr.strip().split("\n")[-3:]:
                        print(f"    {DIM}{line}{RESET}")

    elif ext.lower() == ".appimage" or "appimage" in filename.lower():
        print(f"  {CYAN}检测到 AppImage...{RESET}")
        dest = os.path.expanduser(f"~/.local/bin/{filename}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        os.chmod(dest, 0o755)
        print(f"  {GREEN}已复制到 {dest}{RESET}")
        print(f"  {GREEN}可直接运行: {dest}{RESET}")

    elif ext == ".flatpak" or ext == ".flatpakref":
        print(f"  {MAGENTA}检测到 Flatpak 包...{RESET}")
        subprocess.run(
            ["flatpak", "remote-add", "--if-not-exists", "flathub",
             "https://flathub.org/repo/flathub.flatpakrepo"],
            capture_output=True, timeout=10
        )
        result = subprocess.run(
            ["pkexec", "flatpak", "install", "-y", path],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  {GREEN}{BOLD}✓ 安装成功{RESET}")
        else:
            print(f"  {RED}✗ 安装失败{RESET}")

    elif ext == ".exe":
        print(f"  {BLUE}检测到 Windows 可执行文件{RESET}")
        print(f"\n  {YELLOW}⚠ Windows 兼容性提示:{RESET}")
        print(f"    {RED}✗ 带 ACE 反作弊的游戏完全无法运行{RESET}")
        print(f"    {YELLOW}△ Windows 游戏可能不兼容或性能较差{RESET}")
        print(f"    {YELLOW}△ 部分专业软件可能无法正常工作{RESET}")
        print(f"    {GREEN}✓ 老游戏和简单工具兼容性较好{RESET}")
        print(f"\n  {DIM}参考: https://www.protondb.com/{RESET}")

        has_wine = subprocess.run(["which", "wine"], capture_output=True).returncode == 0
        if not has_wine:
            print(f"\n  {YELLOW}未安装 Wine，正在安装...{RESET}")
            result = subprocess.run(
                ["pkexec", "apt", "install", "-y", "wine"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"  {RED}Wine 安装失败{RESET}")
                return
            print(f"  {GREEN}Wine 安装完成{RESET}")

        confirm = input(f"\n  是否尝试运行 {filename}? {YELLOW}[y/N]{RESET} ").strip().lower()
        if confirm != "y":
            print(f"  {DIM}已取消{RESET}")
            return

        print(f"\n  {DIM}正在启动 Wine 安装程序...{RESET}")
        print(f"  {DIM}(安装窗口将在桌面弹出){RESET}")
        subprocess.Popen(
            ["wine", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    else:
        print(f"  {RED}不支持的格式: {ext}{RESET}")
        print(f"  {DIM}支持: .deb .rpm .AppImage .flatpak .exe{RESET}")


def menu():
    print(f"""
  {BOLD}{'─'*42}{RESET}
    {GREEN}1{RESET}  搜索软件
    {GREEN}2{RESET}  镜像测速
    {GREEN}3{RESET}  切换源
    {GREEN}4{RESET}  一键装机
    {GREEN}5{RESET}  安装本地包
    {RED}0{RESET}  退出
  {BOLD}{'─'*42}{RESET}""")


def main():
    clear()
    banner()
    distro = detect_distro()
    print(f"  {GREEN}系统:{RESET} {BOLD}{distro}{RESET}")
    print(f"  {GREEN}支持:{RESET} apt · snap · flatpak")

    while True:
        menu()
        try:
            choice = input(f"  {BOLD}❯{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if choice == "1":
            keyword = input(f"  {CYAN}搜索关键词:{RESET} ").strip()
            if not keyword:
                continue
            search_all_parallel(keyword)

        elif choice == "2":
            results = test_mirrors()
            if results:
                best = max(results, key=results.get)
                print(f"\n  {GREEN}{BOLD}🏆 最快: {best} ({results[best]:.2f} MB/s){RESET}")

        elif choice == "3":
            results = test_mirrors()
            if results:
                best = max(results, key=results.get)
                print(f"\n  {GREEN}{BOLD}最快: {best} ({results[best]:.2f} MB/s){RESET}")
                confirm = input(f"  确认切换到 {best}? {YELLOW}[y/N]{RESET} ").strip().lower()
                if confirm == "y":
                    switch_mirror(best, MIRRORS[best])
                else:
                    print(f"  {DIM}已取消{RESET}")

        elif choice == "4":
            one_click_setup()

        elif choice == "5":
            install_local_package()

        elif choice == "0":
            print(f"\n  {GREEN}👋 再见{RESET}\n")
            break
        else:
            print(f"  {RED}无效选项{RESET}")


if __name__ == "__main__":
    main()

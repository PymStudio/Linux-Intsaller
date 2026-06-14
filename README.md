# Linux Installer

Ubuntu/Debian 软件安装器，一键搜索、安装、换源。

## 功能

- **软件搜索** - 同时搜索 apt/snap/flatpak 三个源
- **本地包安装** - 支持 .deb/.rpm/.AppImage/.flatpak/.exe
- **镜像测速** - 测试清华/中科大/阿里/华为/官方源速度
- **一键换源** - 自动备份并切换最快镜像
- **一键装机** - 基础工具/开发环境/Docker 等
- **Wine 支持** - 运行 Windows .exe 文件（含兼容性提示）

## 使用方法

```bash
git clone https://github.com/PymStudio/Linux-Intsaller.git
cd Linux-Intsaller
chmod +x installer.sh
./installer.sh
```

## 系统要求

- Ubuntu 20.04+ / Debian 10+
- Bash 4.0+
- curl（镜像测速需要）

## 功能菜单

```
1  搜索软件      同时搜索 apt/snap/flatpak
2  镜像测速      测试国内镜像速度
3  切换源        自动切换到最快镜像
4  一键装机      批量安装开发环境
5  安装本地包    安装 deb/rpm/AppImage/exe
0  退出
```

## 本地包安装说明

| 格式 | 说明 |
|------|------|
| .deb | Debian/Ubuntu 软件包，直接安装 |
| .rpm | RedHat/Fedora 软件包，自动用 alien 转换 |
| .AppImage | 便携式应用，复制到 ~/.local/bin/ |
| .flatpak | Flatpak 包，自动添加 flathub 源 |
| .exe | Windows 程序，通过 Wine 运行 |

## Windows 兼容性

通过 Wine 运行 .exe 时会提示兼容性：
- ✗ 带 ACE 反作弊的游戏完全无法运行
- △ Windows 游戏可能不兼容或性能较差
- △ 部分专业软件可能无法正常工作
- ✓ 老游戏和简单工具兼容性较好

参考: https://www.protondb.com/

## 注意事项

- 安装软件需要 sudo 权限，会弹出密码框
- 换源前会自动备份原 sources.list
- 测速结果仅供参考，实际速度可能有差异

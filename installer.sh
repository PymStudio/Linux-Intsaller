#!/bin/bash

MIRRORS=(
    "清华源|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"
    "中科大|https://mirrors.ustc.edu.cn/ubuntu/"
    "阿里云|https://mirrors.aliyun.com/ubuntu/"
    "华为云|https://mirrors.huaweicloud.com/ubuntu/"
    "官方源|http://archive.ubuntu.com/ubuntu/"
)

SPEED_TEST_FILE="dists/noble/InRelease"
HEADERS="User-Agent: curl/8.5.0"

RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
BLUE='\033[94m'
MAGENTA='\033[95m'
CYAN='\033[96m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

clear_screen() { echo -e "\033[2J\033[H"; }

detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "${PRETTY_NAME:-$NAME}"
    else
        echo "未知系统"
    fi
}

pad() {
    local s="$1" width="$2"
    local w=0
    for (( i=0; i<${#s}; i++ )); do
        local c="${s:$i:1}"
        if LC_ALL=C grep -qP '[^\x00-\x7F]' <<< "$c"; then
            ((w+=2))
        else
            ((w+=1))
        fi
    done
    printf "%s%*s" "$s" $((width - w)) ""
}

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║        📦 软件安装器 v0.1               ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${RESET}"
}

print_menu() {
    echo ""
    echo -e "  ${BOLD}──────────────────────────────────────────${RESET}"
    echo -e "    ${GREEN}1${RESET}  搜索软件"
    echo -e "    ${GREEN}2${RESET}  镜像测速"
    echo -e "    ${GREEN}3${RESET}  切换源"
    echo -e "    ${GREEN}4${RESET}  一键装机"
    echo -e "    ${GREEN}5${RESET}  安装本地包"
    echo -e "    ${RED}0${RESET}  退出"
    echo -e "  ${BOLD}──────────────────────────────────────────${RESET}"
}

search_apt() {
    local keyword="$1"
    apt-cache search "$keyword" 2>/dev/null | while read -r line; do
        local name="${line%% - *}"
        local desc="${line#* - }"
        [ "$name" != "$line" ] && [ -n "$name" ] && echo "apt|$name|$desc"
    done
}

search_snap() {
    local keyword="$1"
    snap find "$keyword" 2>/dev/null | tail -n +2 | while read -r line; do
        local name=$(echo "$line" | awk '{print $1}')
        local desc=$(echo "$line" | cut -d' ' -f3-)
        [ -n "$name" ] && echo "snap|$name|$desc"
    done
}

search_flatpak() {
    local keyword="$1"
    flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo 2>/dev/null
    flatpak search "$keyword" --columns=name,description 2>/dev/null | while IFS=$'\t' read -r name desc; do
        [ -n "$name" ] && echo "flatpak|$name|$desc"
    done
}

display_line() {
    local i=$1 src=$2 name=$3 desc=$4
    local color="$GREEN"
    [ "$src" = "snap" ] && color="$YELLOW"
    [ "$src" = "flatpak" ] && color="$CYAN"
    local desc_short="${desc:0:40}"
    [ ${#desc} -gt 40 ] && desc_short="${desc_short}..."
    printf "  ${DIM}%3d${RESET}  ${color}%-10s${RESET} ${BOLD}%-28s${RESET} ${DIM}%s${RESET}\n" "$i" "$src" "$name" "$desc_short"
}

do_search() {
    local keyword
    echo -ne "  ${CYAN}搜索关键词:${RESET} "
    read -r keyword
    [ -z "$keyword" ] && return

    local tmpfile=$(mktemp)
    local count=0

    echo ""
    echo -e "  ${BOLD}搜索: ${keyword}${RESET}\n"

    echo -e "  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"
    printf "  ${DIM}%-3s  %-10s %-28s %s${RESET}\n" "#" "来源" "包名" "描述"
    echo -e "  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"

    echo -e "  ${DIM}▸ 搜索 apt ...${RESET}"
    while IFS='|' read -r src name desc; do
        ((count++))
        echo "$src|$name|$desc" >> "$tmpfile"
        display_line "$count" "$src" "$name" "$desc"
    done < <(search_apt "$keyword")
    echo -e "\r  ${GREEN}✓ apt${RESET}       ${DIM}(${count} 条)${RESET}              "

    local snap_start=$count
    echo -e "  ${DIM}▸ 搜索 snap ...${RESET}"
    while IFS='|' read -r src name desc; do
        ((count++))
        echo "$src|$name|$desc" >> "$tmpfile"
        display_line "$count" "$src" "$name" "$desc"
    done < <(search_snap "$keyword")
    echo -e "\r  ${GREEN}✓ snap${RESET}      ${DIM}($((count - snap_start)) 条)${RESET}              "

    local fp_start=$count
    echo -e "  ${DIM}▸ 搜索 flatpak ...${RESET}"
    while IFS='|' read -r src name desc; do
        ((count++))
        echo "$src|$name|$desc" >> "$tmpfile"
        display_line "$count" "$src" "$name" "$desc"
    done < <(search_flatpak "$keyword")
    echo -e "\r  ${GREEN}✓ flatpak${RESET}   ${DIM}($((count - fp_start)) 条)${RESET}              "

    local total=$count
    echo -e "\n  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"
    echo -e "  ${BOLD}共 ${total} 条结果${RESET}\n"

    if [ "$total" -eq 0 ]; then
        rm -f "$tmpfile"
        return
    fi

    local page_size=20
    local current_page=1
    local total_pages=$(( (total + page_size - 1) / page_size ))

    show_page() {
        local page=$1
        local start=$(( (page - 1) * page_size + 1 ))
        local end=$(( page * page_size ))
        [ "$end" -gt "$total" ] && end=$total

        clear_screen
        echo -e "  ${BOLD}搜索: ${keyword}${RESET}  ${DIM}(共 ${total} 条)${RESET}\n"
        echo -e "  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"
        printf "  ${DIM}%-3s  %-10s %-28s %s${RESET}\n" "#" "来源" "包名" "描述"
        echo -e "  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"

        local i=0
        while IFS='|' read -r src name desc; do
            ((i++))
            [ "$i" -lt "$start" ] && continue
            [ "$i" -gt "$end" ] && break
            display_line "$i" "$src" "$name" "$desc"
        done < "$tmpfile"

        echo -e "  ${DIM}────────────────────────────────────────────────────────────────────${RESET}"
        echo -e "  ${DIM}第 ${page}/${total_pages} 页  共 ${total} 条${RESET}"
    }

    while true; do
        show_page $current_page
        echo ""
        echo -e "  ${GREEN}n${RESET}=下一页 ${GREEN}p${RESET}=上一页 ${GREEN}数字${RESET}=安装 ${RED}q${RESET}=返回"
        echo -ne "  ${BOLD}❯${RESET} "
        read -r input

        case "$input" in
            n|N) [ "$current_page" -lt "$total_pages" ] && ((current_page++)) ;;
            p|P) [ "$current_page" -gt 1 ] && ((current_page--)) ;;
            q|Q|"") break ;;
            *)
                if [[ "$input" =~ ^[0-9]+$ ]] && [ "$input" -ge 1 ] && [ "$input" -le "$total" ]; then
                    local line=$(sed -n "${input}p" "$tmpfile")
                    local pkg_name=$(echo "$line" | cut -d'|' -f2)
                    local pkg_src=$(echo "$line" | cut -d'|' -f1)
                    echo ""
                    echo -e "  安装 ${BOLD}${pkg_name}${RESET} (${pkg_src})?"
                    echo -ne "  确认? ${YELLOW}[y/N]${RESET} "
                    read -r confirm
                    if [ "$confirm" = "y" ]; then
                        case "$pkg_src" in
                            apt) sudo apt install -y "$pkg_name" ;;
                            snap) sudo snap install "$pkg_name" ;;
                            flatpak) sudo flatpak install -y flathub "$pkg_name" ;;
                        esac
                    fi
                    echo ""
                else
                    echo -e "  ${RED}无效输入${RESET}"
                fi
                ;;
        esac
    done

    rm -f "$tmpfile"
}

test_mirrors() {
    echo ""
    echo -e "  ${BOLD}镜像测速中...${RESET}"
    echo ""

    local best_name="" best_speed="0.00"

    for mirror in "${MIRRORS[@]}"; do
        IFS='|' read -r name url <<< "$mirror"
        local test_url="${url}${SPEED_TEST_FILE}"
        local start_time=$(date +%s%N)
        local data_size=$(curl -s -o /dev/null -w '%{size_download}' --max-time 5 -H "$HEADERS" "$test_url" 2>/dev/null)
        local end_time=$(date +%s%N)
        local elapsed_ms=$(( (end_time - start_time) / 1000000 ))

        if [ "$elapsed_ms" -gt 0 ] && [ -n "$data_size" ] && [ "$data_size" != "0" ]; then
            local speed_int=$(( data_size * 1000 / elapsed_ms / 1024 / 1024 ))
            local speed_frac=$(( (data_size * 1000 / elapsed_ms * 100 / 1024 / 1024) % 100 ))
            local speed_str=$(printf "%d.%02d" "$speed_int" "$speed_frac")

            local bar_len=$speed_int
            [ "$bar_len" -gt 30 ] && bar_len=30
            [ "$bar_len" -lt 1 ] && bar_len=1
            local bar=$(printf '█%.0s' $(seq 1 $bar_len))

            local color="$GREEN"
            [ "$speed_int" -lt 1 ] && color="$RED"
            [ "$speed_int" -ge 1 ] && [ "$speed_int" -lt 2 ] && color="$YELLOW"

            printf "    ${CYAN}%6s${RESET}  ${color}%-30s${RESET} %s MB/s\n" "$name" "$bar" "$speed_str"

            local total_score=$(( speed_int * 100 + speed_frac ))
            local best_int=${best_speed%.*}
            local best_frac=${best_speed#*.}
            best_frac=${best_frac:-0}
            best_frac=$((10#${best_frac}))
            local best_score=$(( best_int * 100 + best_frac ))

            if [ "$total_score" -gt "$best_score" ]; then
                best_speed="$speed_str"
                best_name="$name"
            fi
        else
            printf "    ${CYAN}%6s${RESET}  ${RED}%-30s${RESET} 失败\n" "$name" "-"
        fi
    done

    if [ -n "$best_name" ]; then
        echo ""
        echo -e "  ${GREEN}${BOLD}🏆 最快: ${best_name} (${best_speed} MB/s)${RESET}"
    fi

    echo "$best_name" > /tmp/.mirror_best_name
    echo "$best_speed" > /tmp/.mirror_best_speed

    echo "$best_name|$best_speed"
}

do_switch_mirror() {
    test_mirrors
    local best_name=$(cat /tmp/.mirror_best_name 2>/dev/null)
    local best_speed=$(cat /tmp/.mirror_best_speed 2>/dev/null)

    [ -z "$best_name" ] && return

    echo ""
    echo -ne "  确认切换到 ${best_name}? ${YELLOW}[y/N]${RESET} "
    read -r confirm
    [ "$confirm" != "y" ] && echo -e "  ${DIM}已取消${RESET}" && return

    local mirror_url=""
    for mirror in "${MIRRORS[@]}"; do
        IFS='|' read -r name url <<< "$mirror"
        [ "$name" = "$best_name" ] && mirror_url="$url" && break
    done

    local codename=$(grep VERSION_CODENAME /etc/os-release 2>/dev/null | cut -d= -f2)
    [ -z "$codename" ] && codename="jammy"

    echo -e "\n  ${YELLOW}切换到 ${best_name}...${RESET}"

    local sources="/etc/apt/sources.list"
    local backup="${sources}.backup"

    if [ -f "$sources" ] && [ ! -f "$backup" ]; then
        sudo cp "$sources" "$backup"
        echo -e "  ${DIM}已备份到 ${backup}${RESET}"
    fi

    cat <<EOF | sudo tee "$sources" > /dev/null
deb ${mirror_url} ${codename} main restricted universe multiverse
deb ${mirror_url} ${codename}-updates main restricted universe multiverse
deb ${mirror_url} ${codename}-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu/ ${codename}-security main restricted universe multiverse
EOF

    echo -e "  ${DIM}正在更新...${RESET}"
    sudo apt update -qq 2>/dev/null
    echo -e "  ${GREEN}${BOLD}✓ 已切换到 ${best_name}${RESET}"
}

one_click_setup() {
    echo ""
    echo -e "  ${BOLD}一键装机${RESET}"
    echo ""

    local envs=(
        "1|包管理器|snapd flatpak||"
        "2|基础工具|git curl wget vim htop tree unzip build-essential||"
        "3|Python 开发|python3 python3-pip python3-venv||"
        "4|Node.js 开发|nodejs npm||"
        "5|C/C++ 开发|gcc g++ gdb cmake make||"
        "6|Docker|docker.io|docker|"
        "7|浏览器|||org.mozilla.firefox com.google.Chrome"
        "8|办公套件||libreoffice|"
        "9|多媒体|vlc ffmpeg|vlc|"
        "0|全部安装|||"
    )

    echo -e "  ${DIM}────────────────────────────────────────────────────────${RESET}"
    printf "  ${DIM}%3s  %-14s %-6s %-6s %-6s${RESET}\n" "#" "名称" "apt" "snap" "flatpak"
    echo -e "  ${DIM}────────────────────────────────────────────────────────${RESET}"

    for env in "${envs[@]}"; do
        IFS='|' read -r num name apt_pkgs snap_pkgs flat_pkgs <<< "$env"
        local a="-" s="-" f="-"
        [ -n "$apt_pkgs" ] && a="✓"
        [ -n "$snap_pkgs" ] && s="✓"
        [ -n "$flat_pkgs" ] && f="✓"
        printf "  ${BOLD}%3s${RESET}  $(pad "$name" 14)  %-6s %-6s %-6s\n" "$num" "$a" "$s" "$f"
    done
    echo -e "  ${DIM}────────────────────────────────────────────────────────${RESET}"

    echo -ne "  ${BOLD}❯${RESET} "
    read -r choice

    local apt_pkgs="" snap_pkgs="" flat_pkgs="" name=""
    for env in "${envs[@]}"; do
        IFS='|' read -r num n a s f <<< "$env"
        [ "$num" = "$choice" ] && name="$n" && apt_pkgs="$a" && snap_pkgs="$s" && flat_pkgs="$f" && break
    done

    [ -z "$name" ] && echo -e "  ${RED}无效选项${RESET}" && return

    if [ "$name" = "全部安装" ]; then
        for env in "${envs[@]}"; do
            IFS='|' read -r num n a s f <<< "$env"
            [ "$num" = "0" ] && continue
            apt_pkgs="$apt_pkgs $a"
            snap_pkgs="$snap_pkgs $s"
            flat_pkgs="$flat_pkgs $f"
        done
        name="全部"
    fi

    echo ""
    echo -e "  ${YELLOW}安装 ${name}:${RESET}"
    [ -n "$apt_pkgs" ] && echo -e "    ${GREEN}apt:${RESET} ${DIM}${apt_pkgs}${RESET}"
    [ -n "$snap_pkgs" ] && echo -e "    ${YELLOW}snap:${RESET} ${DIM}${snap_pkgs}${RESET}"
    [ -n "$flat_pkgs" ] && echo -e "    ${CYAN}flatpak:${RESET} ${DIM}${flat_pkgs}${RESET}"

    echo -ne "\n  确认安装? ${YELLOW}[y/N]${RESET} "
    read -r confirm
    [ "$confirm" != "y" ] && echo -e "  ${DIM}已取消${RESET}" && return

    echo -e "\n  ${BOLD}开始安装...${RESET}\n"

    if [ -n "$apt_pkgs" ]; then
        echo -e "  ${GREEN}▸ 安装 apt 包...${RESET}"
        sudo apt install -y $apt_pkgs 2>/dev/null && echo -e "  ${GREEN}  ✓ apt 安装完成${RESET}" || echo -e "  ${RED}  ✗ apt 安装失败${RESET}"
    fi

    if [ -n "$snap_pkgs" ]; then
        echo -e "  ${YELLOW}▸ 安装 snap 包...${RESET}"
        for pkg in $snap_pkgs; do
            [ -z "$pkg" ] && continue
            sudo snap install "$pkg" 2>/dev/null && echo -e "  ${YELLOW}  ✓ ${pkg}${RESET}" || echo -e "  ${RED}  ✗ ${pkg}${RESET}"
        done
    fi

    if [ -n "$flat_pkgs" ]; then
        echo -e "  ${CYAN}▸ 安装 flatpak 包...${RESET}"
        flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo 2>/dev/null
        for pkg in $flat_pkgs; do
            [ -z "$pkg" ] && continue
            sudo flatpak install -y flathub "$pkg" 2>/dev/null && echo -e "  ${CYAN}  ✓ ${pkg}${RESET}" || echo -e "  ${RED}  ✗ ${pkg}${RESET}"
        done
    fi

    echo -e "\n  ${GREEN}${BOLD}✓ ${name} 安装完成${RESET}"
}

install_local_package() {
    local distro=$(detect_distro | tr '[:upper:]' '[:lower:]')
    local is_deb=0 is_rpm=0
    echo "$distro" | grep -qiE "ubuntu|debian|mint|pop|deepin" && is_deb=1
    echo "$distro" | grep -qiE "fedora|red.hat|centos|rhel|opensuse|manjaro" && is_rpm=1

    echo ""
    echo -e "  ${BOLD}安装本地软件包${RESET}"
    echo ""
    echo -e "  ${DIM}当前系统:${RESET} ${BOLD}$(detect_distro)${RESET}"

    if [ "$is_deb" -eq 1 ]; then
        echo -e "  ${DIM}包格式:${RESET} ${GREEN}.deb${RESET} (原生) / ${YELLOW}.rpm${RESET} (需转换) / ${CYAN}.AppImage${RESET} / ${MAGENTA}.flatpak${RESET} / ${BLUE}.exe${RESET} (Wine)"
    elif [ "$is_rpm" -eq 1 ]; then
        echo -e "  ${DIM}包格式:${RESET} ${YELLOW}.rpm${RESET} (原生) / ${GREEN}.deb${RESET} (需转换) / ${CYAN}.AppImage${RESET} / ${MAGENTA}.flatpak${RESET} / ${BLUE}.exe${RESET} (Wine)"
    else
        echo -e "  ${DIM}包格式:${RESET} ${CYAN}.AppImage${RESET} / ${MAGENTA}.flatpak${RESET} / ${BLUE}.exe${RESET} (Wine)"
    fi

    echo ""
    echo -e "  ${DIM}拖入文件路径，或手动输入路径:${RESET}"
    echo -ne "  ${BOLD}❯${RESET} "
    read -r path
    path=$(echo "$path" | tr -d "'\"")

    [ -z "$path" ] && echo -e "  ${RED}未输入路径${RESET}" && return
    path=$(eval echo "$path")

    [ ! -f "$path" ] && echo -e "  ${RED}文件不存在: ${path}${RESET}" && return

    local filename=$(basename "$path")
    local ext="${filename##*.}"
    ext=$(echo "$ext" | tr '[:upper:]' '[:lower:]')

    echo ""
    echo -e "  ${BOLD}文件:${RESET} ${filename}"

    case "$ext" in
        deb)
            if [ "$is_rpm" -eq 1 ]; then
                echo -e "  ${YELLOW}⚠ 警告: 当前系统为 $(detect_distro)，不原生支持 .deb 包${RESET}"
                echo -ne "  是否尝试用 alien 转换安装? ${YELLOW}[y/N]${RESET} "
                read -r confirm
                [ "$confirm" != "y" ] && echo -e "  ${DIM}已取消${RESET}" && return
                sudo apt install -y alien 2>/dev/null
                local tmp="/tmp/${filename%.deb}.rpm"
                sudo alien -r --to-rpm "$path" -o "$tmp" 2>/dev/null
                [ -f "$tmp" ] && sudo rpm -i "$tmp" && echo -e "  ${GREEN}${BOLD}✓ 安装成功${RESET}" || echo -e "  ${RED}✗ 安装失败${RESET}"
                rm -f "$tmp"
            else
                echo -e "  ${GREEN}检测到 .deb 包，使用 apt 安装...${RESET}"
                sudo apt install -y "$path" 2>/dev/null && echo -e "  ${GREEN}${BOLD}✓ 安装成功${RESET}" || echo -e "  ${RED}✗ 安装失败${RESET}"
            fi
            ;;
        rpm)
            if [ "$is_deb" -eq 1 ]; then
                echo -e "  ${YELLOW}⚠ 警告: 当前系统为 $(detect_distro)，不原生支持 .rpm 包${RESET}"
                echo -ne "  是否尝试用 alien 转换安装? ${YELLOW}[y/N]${RESET} "
                read -r confirm
                [ "$confirm" != "y" ] && echo -e "  ${DIM}已取消${RESET}" && return
                sudo apt install -y alien 2>/dev/null
                local tmp="/tmp/${filename%.rpm}.deb"
                sudo alien -d --to-deb "$path" -o "$tmp" 2>/dev/null
                [ -f "$tmp" ] && sudo apt install -y "$tmp" && echo -e "  ${GREEN}${BOLD}✓ 安装成功${RESET}" || echo -e "  ${RED}✗ 安装失败${RESET}"
                rm -f "$tmp"
            else
                echo -e "  ${YELLOW}检测到 .rpm 包，使用 rpm 安装...${RESET}"
                sudo rpm -i "$path" 2>/dev/null && echo -e "  ${GREEN}${BOLD}✓ 安装成功${RESET}" || echo -e "  ${RED}✗ 安装失败${RESET}"
            fi
            ;;
        AppImage|appimage)
            echo -e "  ${CYAN}检测到 AppImage...${RESET}"
            local dest="$HOME/.local/bin/$filename"
            mkdir -p "$(dirname "$dest")"
            cp "$path" "$dest"
            chmod +x "$dest"
            echo -e "  ${GREEN}已复制到 ${dest}${RESET}"
            echo -e "  ${GREEN}可直接运行: ${dest}${RESET}"
            ;;
        flatpak|flatpakref)
            echo -e "  ${MAGENTA}检测到 Flatpak 包...${RESET}"
            flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo 2>/dev/null
            sudo flatpak install -y "$path" 2>/dev/null && echo -e "  ${GREEN}${BOLD}✓ 安装成功${RESET}" || echo -e "  ${RED}✗ 安装失败${RESET}"
            ;;
        exe)
            echo -e "  ${BLUE}检测到 Windows 可执行文件${RESET}"
            echo ""
            echo -e "  ${YELLOW}⚠ Windows 兼容性提示:${RESET}"
            echo -e "    ${RED}✗ 带 ACE 反作弊的游戏完全无法运行${RESET}"
            echo -e "    ${YELLOW}△ Windows 游戏可能不兼容或性能较差${RESET}"
            echo -e "    ${YELLOW}△ 部分专业软件可能无法正常工作${RESET}"
            echo -e "    ${GREEN}✓ 老游戏和简单工具兼容性较好${RESET}"
            echo ""
            echo -e "  ${DIM}参考: https://www.protondb.com/${RESET}"

            if ! command -v wine &>/dev/null; then
                echo ""
                echo -e "  ${YELLOW}未安装 Wine，正在安装...${RESET}"
                sudo apt install -y wine 2>/dev/null && echo -e "  ${GREEN}Wine 安装完成${RESET}" || { echo -e "  ${RED}Wine 安装失败${RESET}"; return; }
            fi

            echo ""
            echo -ne "  是否尝试运行 ${filename}? ${YELLOW}[y/N]${RESET} "
            read -r confirm
            [ "$confirm" != "y" ] && echo -e "  ${DIM}已取消${RESET}" && return

            echo ""
            echo -e "  ${DIM}正在启动 Wine 安装程序...${RESET}"
            echo -e "  ${DIM}(安装窗口将在桌面弹出){RESET}"
            wine "$path" &>/dev/null &
            ;;
        *)
            echo -e "  ${RED}不支持的格式: .${ext}${RESET}"
            echo -e "  ${DIM}支持: .deb .rpm .AppImage .flatpak .exe${RESET}"
            ;;
    esac
}

main() {
    clear_screen
    print_banner

    local distro=$(detect_distro)
    echo -e "  ${GREEN}系统:${RESET} ${BOLD}${distro}${RESET}"
    echo -e "  ${GREEN}支持:${RESET} apt · snap · flatpak"

    while true; do
        print_menu
        echo -ne "  ${BOLD}❯${RESET} "
        read -r choice

        case "$choice" in
            1) do_search ;;
            2) test_mirrors ;;
            3) do_switch_mirror ;;
            4) one_click_setup ;;
            5) install_local_package ;;
            0) echo -e "\n  ${GREEN}👋 再见${RESET}\n"; break ;;
            *) echo -e "  ${RED}无效选项${RESET}" ;;
        esac
    done
}

main

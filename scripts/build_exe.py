#!/usr/bin/env python3
import subprocess
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 清理之前的打包结果
def clean_build():
    print("清理之前的打包结果...")
    try:
        build_dir = PROJECT_ROOT / 'build'
        dist_dir = PROJECT_ROOT / 'dist'
        root_spec = PROJECT_ROOT / 'aim_assist.spec'
        if build_dir.exists():
            shutil.rmtree(build_dir)
            print("已删除 build 目录")
        if dist_dir.exists():
            try:
                shutil.rmtree(dist_dir)
                print("已删除 dist 目录")
            except PermissionError:
                print("警告：无法删除 dist 目录，可能文件正在被使用")
        if root_spec.exists():
            root_spec.unlink()
            print("已删除 aim_assist.spec 文件")
    except Exception as e:
        print(f"清理目录时出错：{e}")

# 打包命令
def build_exe():
    print("开始打包...")
    # 使用兼容的打包命令，确保所有依赖都被正确包含
    cmd = [
        'pyinstaller',
        '--onefile',
        '--name', 'aim_assist',
        '--paths', 'src',
        '--specpath', 'packaging',
        '--add-data', 'config.json;.',
        '--add-data', 'models;models',
        '--hidden-import', 'cv2',
        '--hidden-import', 'numpy',
        '--hidden-import', 'pyautogui',
        '--hidden-import', 'keyboard',
        '--hidden-import', 'mss',
        '--hidden-import', 'pkg_resources.py2_warn',
        '--hidden-import', 'setuptools',
        'main.py'
    ]
    
    print("正在执行命令: " + " ".join(cmd))
    
    # 实时显示打包日志
    print("\n打包过程日志：")
    print("=" * 60)
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=PROJECT_ROOT,
    )
    
    for line in process.stdout:
        print(line.strip())
    
    process.wait()
    
    if process.returncode == 0:
        print("\n" + "=" * 60)
        print("打包成功！")
        print(f"可执行文件位于: dist/aim_assist.exe")
        return True
    else:
        print("\n" + "=" * 60)
        print("打包失败！")
        return False

# 复制必要文件到dist目录
def copy_files():
    print("\n复制必要文件到 dist 目录...")
    dist_dir = PROJECT_ROOT / 'dist'
    if not dist_dir.exists():
        print("错误：dist 目录不存在")
        return
    
    files_to_copy = ['config.json']
    for file in files_to_copy:
        source = PROJECT_ROOT / file
        if source.exists():
            try:
                shutil.copy(source, dist_dir)
                print(f"已复制 {file} 到 dist 目录")
            except Exception as e:
                print(f"复制 {file} 时出错：{e}")
        else:
            print(f"警告：{file} 文件不存在")

# 主函数
def main():
    print("=== 瞄准吸附工具打包脚本 ===")
    print("=" * 40)
    
    # 清理之前的构建
    clean_build()
    
    # 执行打包
    success = build_exe()
    
    # 如果打包成功，复制必要文件
    if success:
        copy_files()
    
    print("\n=== 打包过程完成 ===")
    print("使用说明：")
    print("1. 运行 dist/aim_assist.exe 启动程序")
    print("2. 程序需要管理员权限运行")
    print("3. 首次运行会自动生成配置文件")
    print("4. 按 Ctrl+Q 退出程序")

if __name__ == "__main__":
    main()

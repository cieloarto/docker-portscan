from enum import Enum
import docker
import yaml
import os
import re
import subprocess

class PortIndex(Enum):
    HOST = 0  # ホスト側のポート
    CONTAINER = 1  # コンテナ側のポート

def find_docker_compose_files(root_path=".", max_depth=2, exclude_patterns=None):
    """指定したディレクトリ以下の一定の深さまでのdocker-compose.ymlファイルを見つける。
    exclude_patterns に一致するフォルダを除外する。
    """
    exclude_patterns = exclude_patterns or []
    docker_compose_files = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # 探索の深さを制限
        if dirpath[len(root_path):].count(os.sep) < max_depth:
            # 除外パターンに一致するディレクトリをスキップ
            if any(re.search(pattern, dirpath) for pattern in exclude_patterns):
                dirnames[:] = []  # 子ディレクトリも探索しない
                continue

            if "docker-compose.yml" in filenames:
                docker_compose_files.append(os.path.join(dirpath, "docker-compose.yml"))
        else:
            dirnames[:] = []  # 深さを超えたディレクトリは無視
    return docker_compose_files

def get_ports_from_docker_compose(files):
    """複数のdocker-compose.ymlファイルから定義されているポートを抽出する"""
    ports = {}
    for file_path in files:
        try:
            with open(file_path, "r") as file:
                compose_data = yaml.safe_load(file)
                services = compose_data.get("services", {})
                file_ports = {}
                for service_name, service_data in services.items():
                    if "ports" in service_data:
                        file_ports[service_name] = [port.split(":")[PortIndex.HOST.value] for port in service_data["ports"]]
                if file_ports:
                    ports[file_path] = file_ports
        except Exception as e:
            print(f"{file_path} の読み込み中にエラーが発生しました: {e}")
    return ports

def get_ports_from_running_containers():
    """現在稼働中のコンテナのポートを取得する"""
    client = docker.from_env()
    running_ports = {}
    containers = client.containers.list()
    for container in containers:
        container_ports = []
        for port_data in container.attrs["NetworkSettings"]["Ports"].values():
            if port_data:
                container_ports.extend([port["HostPort"] for port in port_data if "HostPort" in port])
        running_ports[container.name] = container_ports
    return running_ports

def execute_docker_compose_command(file_path, command):
    """指定されたdocker-composeファイルでコマンドを実行"""
    try:
        subprocess.run(["docker-compose", "-f", file_path, command], check=True)
        print(f"{command} コマンドが正常に完了しました: {file_path}")
    except subprocess.CalledProcessError as e:
        print(f"{file_path} で {command} コマンドの実行中にエラーが発生しました: {e}")

def prompt_user_action(docker_compose_files):
    """ユーザーに対して docker-compose の操作を選択させるプロンプトを表示"""
    while True:
        print("\n=== Docker Compose ファイル一覧 ===")
        for idx, file_path in enumerate(docker_compose_files, 1):
            print(f"{idx}: {file_path}")
        print("a: 全てのファイルに対して一括操作")
        print("0: 終了")

        choice = input("\n操作したいファイルの番号を選択してください (Enter または 0 で終了): ").strip()
        if choice in {"0", ""}:
            break
        elif choice.lower() == "a":
            action = input("一括操作を選択してください (start/stop/restart): ").strip().lower()
            if action in ["start", "stop", "restart"]:
                for file_path in docker_compose_files:
                    execute_docker_compose_command(file_path, action)
            else:
                print("無効な操作です。start, stop, restart のいずれかを入力してください。")
        else:
            try:
                choice = int(choice)
                file_path = docker_compose_files[choice - 1]
                action = input("操作を選択してください (start/stop/restart): ").strip().lower()

                if action in ["start", "stop", "restart"]:
                    execute_docker_compose_command(file_path, action)
                else:
                    print("無効な操作です。start, stop, restart のいずれかを入力してください。")
            except (ValueError, IndexError):
                print("無効な選択です。もう一度お試しください。")

def list_ports(root_path=".", max_depth=2, exclude_patterns=None):
    docker_compose_files = find_docker_compose_files(root_path, max_depth, exclude_patterns)
    if not docker_compose_files:
        print("docker-compose.yml が見つかりませんでした。")
        return

    compose_ports = get_ports_from_docker_compose(docker_compose_files)
    running_ports = get_ports_from_running_containers()

    print("\n=== docker-compose.yml 定義ポート ===")
    for file_path, services in compose_ports.items():
        print(f"\nファイル: {file_path}")
        for service, ports in services.items():
            print(f"  {service}: {', '.join(ports)}")

    print("\n=== 使用されていないポート ===")
    for file_path, services in compose_ports.items():
        print(f"\nファイル: {file_path}")
        for service, ports in services.items():
            unused_ports = [port for port in ports if port not in [p for c in running_ports.values() for p in c]]
            if unused_ports:
                print(f"  {service}: {', '.join(unused_ports)}")

    print("\n=== 稼働中のコンテナのポート ===")
    if running_ports:
        for container, ports in running_ports.items():
            print(f"{container}: {', '.join(ports)}")
    else:
        print("稼働中のコンテナがありません")

    prompt_user_action(docker_compose_files)

if __name__ == "__main__":
    root_path = os.path.expanduser("~/dev")
    exclude_patterns = [r"_bk", r"_old"]  # 除外したいパターンを追加
    exclude_patterns = []  # 除外したいパターンを追加
    list_ports(root_path=root_path, max_depth=4, exclude_patterns=exclude_patterns)
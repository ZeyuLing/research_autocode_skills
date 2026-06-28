#!/usr/bin/env python3
"""
太极平台守护进程：监控任务状态、失败重试、企业微信通知。

用法:
    SCRIPT=".claude/skills/taiji/taiji_monitor.py"

    python $SCRIPT --once       # 单轮检查
    python $SCRIPT --daemon     # 后台运行（写 PID 到 logs/monitor.pid）
    python $SCRIPT --stop       # 停止守护进程
    python $SCRIPT --status     # 查看守护进程状态
"""

import argparse
import datetime
import json
import logging
import os
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler

# ── 路径 ──────────────────────────────────────────────────
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
CONFIG_DIR = os.path.join(SKILL_DIR, "config")
HISTORY_FILE = os.path.join(SKILL_DIR, "task_history.jsonl")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
PID_FILE = os.path.join(LOG_DIR, "monitor.pid")
LOG_FILE = os.path.join(LOG_DIR, "monitor.log")


def load_defaults():
    """加载 defaults.json 中的 daemon 配置。"""
    path = os.path.join(CONFIG_DIR, "defaults.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("daemon", {})


def setup_logging():
    """配置 rotating 日志。"""
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("taiji_monitor")
    logger.setLevel(logging.INFO)

    # Rotating file handler: 5MB per file, keep 3 backups
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(ch)

    return logger


# ── 任务历史读写 ──────────────────────────────────────────

def load_history():
    """读取 task_history.jsonl，返回列表。"""
    records = []
    if not os.path.exists(HISTORY_FILE):
        return records
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def save_history(records):
    """覆盖写 task_history.jsonl。"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def append_history(record):
    """追加一条记录。"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 太极客户端操作 ────────────────────────────────────────

def taiji_task_detail(task_flag):
    """调用 taiji_client td 获取任务详情，返回 stdout。"""
    try:
        result = subprocess.run(
            ["taiji_client", "td", task_flag],
            text=True, capture_output=True, timeout=30,
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return str(e), -1


def parse_task_status(td_output):
    """
    从 taiji_client td 输出中解析任务状态。
    常见状态: running, finished, failed, stopped, pending, queuing
    """
    output_lower = td_output.lower()
    # 尝试从输出中提取状态关键词
    for status in ["running", "finished", "failed", "stopped", "pending", "queuing", "creating"]:
        if status in output_lower:
            return status
    return "unknown"


def taiji_submit_config(config_path):
    """调用 taiji_client start -scfg 提交任务。"""
    try:
        result = subprocess.run(
            ["taiji_client", "start", "-scfg", config_path],
            text=True, capture_output=True, timeout=60,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except Exception as e:
        return "", str(e), -1


# ── 企业微信通知 ──────────────────────────────────────────

def send_wechat_notification(webhook_url, title, content, logger):
    """发送企业微信机器人 markdown 消息。"""
    if not webhook_url:
        return

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"## {title}\n{content}"
        }
    }

    try:
        import urllib.request
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        resp_data = json.loads(resp.read().decode("utf-8"))
        if resp_data.get("errcode") != 0:
            logger.warning(f"WeChat webhook error: {resp_data}")
    except Exception as e:
        logger.warning(f"Failed to send WeChat notification: {e}")


# ── 重试逻辑 ──────────────────────────────────────────────

def retry_task(record, retry_count, logger):
    """
    重试失败的任务。
    生成新的 task_flag 带 -retry{N} 后缀，重新提交。
    """
    token = os.environ.get("TOKEN", "")
    if not token:
        logger.error("Cannot retry: TOKEN not set")
        return None

    # 从原始记录重建配置
    defaults_path = os.path.join(CONFIG_DIR, "defaults.json")
    with open(defaults_path, "r", encoding="utf-8") as f:
        defaults = json.load(f)

    base = dict(defaults["base_config"])
    original_flag = record.get("task_flag", "unknown")

    # 去掉之前的 -retry 后缀
    base_flag = original_flag
    for i in range(10):
        suffix = f"-retry{i}"
        if base_flag.endswith(suffix):
            base_flag = base_flag[: -len(suffix)]
            break

    new_flag = f"{base_flag}-retry{retry_count}"

    config = {
        "Token": token,
        "business_flag": record.get("business_flag", "AILab_DHC_DC"),
        **base,
        "host_num": record.get("hosts", 1),
        "host_gpu_num": record.get("gpus", 1),
        "image_full_name": record.get("docker", defaults.get("default", "")),
        "task_flag": new_flag,
        "GPUName": record.get("gpu", "V100"),
        "start_cmd": record.get("cmd", "sleep infinity"),
    }

    # 写临时配置
    tmp_path = os.path.join(SKILL_DIR, f"_tmp_retry_{os.getpid()}.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    logger.info(f"Retrying task: {original_flag} -> {new_flag} (attempt {retry_count})")

    stdout, stderr, rc = taiji_submit_config(tmp_path)

    try:
        os.remove(tmp_path)
    except OSError:
        pass

    if rc != 0:
        logger.error(f"Retry failed: {stderr}")
        return None

    # 解析新的 task_flag 和 instance_id
    parts = stdout.split()
    actual_flag = new_flag
    instance_id = ""
    try:
        if "task_flag:" in parts:
            actual_flag = parts[parts.index("task_flag:") + 1]
        if "instance_id:" in parts:
            instance_id = parts[parts.index("instance_id:") + 1]
    except (ValueError, IndexError):
        pass

    logger.info(f"Retry submitted: {actual_flag} instance={instance_id}")

    new_record = {
        "task_flag": actual_flag,
        "instance_id": instance_id,
        "name": record.get("name", "retry"),
        "gpu": record.get("gpu", "V100"),
        "hosts": record.get("hosts", 1),
        "gpus": record.get("gpus", 1),
        "business_flag": record.get("business_flag", "AILab_DHC_DC"),
        "cmd": record.get("cmd", ""),
        "docker": record.get("docker", ""),
        "submitted_at": datetime.datetime.now().isoformat(),
        "status": "submitted",
        "retry_of": original_flag,
        "retry_count": retry_count,
    }
    append_history(new_record)
    return new_record


# ── 监控循环 ──────────────────────────────────────────────

def monitor_once(logger, daemon_config):
    """单轮监控检查。"""
    webhook_url = daemon_config.get("webhook_url", "")
    max_retries = daemon_config.get("max_retries", 3)

    records = load_history()
    if not records:
        logger.info("No tasks in history.")
        return

    # 找出需要监控的任务 (submitted/running)
    active_indices = []
    for i, r in enumerate(records):
        if r.get("status") in ("submitted", "running"):
            active_indices.append(i)

    if not active_indices:
        logger.info("No active tasks to monitor.")
        return

    logger.info(f"Checking {len(active_indices)} active task(s)...")
    changed = False

    for idx in active_indices:
        r = records[idx]
        task_flag = r.get("task_flag", "")
        old_status = r.get("status", "unknown")

        td_output, rc = taiji_task_detail(task_flag)
        if rc != 0:
            logger.warning(f"  [{task_flag}] Failed to query status: {td_output}")
            continue

        new_status = parse_task_status(td_output)
        logger.info(f"  [{task_flag}] {old_status} -> {new_status}")

        if new_status != old_status and new_status != "unknown":
            records[idx]["status"] = new_status
            records[idx]["last_checked"] = datetime.datetime.now().isoformat()
            changed = True

            # 通知
            msg = (
                f"- **Task**: `{task_flag}`\n"
                f"- **Status**: {old_status} -> **{new_status}**\n"
                f"- **GPU**: {r.get('gpu', '?')} {r.get('hosts', '?')}x{r.get('gpus', '?')}\n"
                f"- **Command**: `{r.get('cmd', '?')[:60]}`"
            )
            send_wechat_notification(webhook_url, f"Taiji Task Status: {new_status}", msg, logger)
            logger.info(f"  [{task_flag}] Status changed: {old_status} -> {new_status}")

            # 失败重试
            if new_status == "failed":
                retry_count = r.get("retry_count", 0) + 1
                if retry_count <= max_retries and r.get("status") != "stopped":
                    # 指数退避: 5min, 10min, 20min
                    backoff = 300 * (2 ** (retry_count - 1))
                    logger.info(f"  [{task_flag}] Will retry in {backoff}s (attempt {retry_count}/{max_retries})")
                    time.sleep(backoff)
                    new_rec = retry_task(r, retry_count, logger)
                    if new_rec:
                        send_wechat_notification(
                            webhook_url,
                            "Taiji Task Retry",
                            f"- **Original**: `{task_flag}`\n- **New**: `{new_rec['task_flag']}`\n- **Attempt**: {retry_count}/{max_retries}",
                            logger,
                        )
                else:
                    logger.info(f"  [{task_flag}] Max retries reached or manually stopped, not retrying.")

    if changed:
        save_history(records)


def daemon_loop(logger, daemon_config):
    """守护进程主循环。"""
    poll_interval = daemon_config.get("poll_interval", 120)
    logger.info(f"Monitor daemon started (poll_interval={poll_interval}s)")

    # 写 PID 文件
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # 信号处理
    running = [True]

    def _handle_signal(signum, frame):
        logger.info(f"Received signal {signum}, stopping...")
        running[0] = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        while running[0]:
            try:
                monitor_once(logger, daemon_config)
            except Exception as e:
                logger.error(f"Monitor error: {e}", exc_info=True)
            # 等待下一轮
            for _ in range(poll_interval):
                if not running[0]:
                    break
                time.sleep(1)
    finally:
        # 清理 PID 文件
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        logger.info("Monitor daemon stopped.")


def cmd_daemon(logger, daemon_config):
    """启动守护进程（fork 到后台）。"""
    # 检查是否已经在运行
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            pid = f.read().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            print(f"Monitor daemon already running (PID {pid})")
            return
        # PID 文件存在但进程不在了
        os.remove(PID_FILE)

    # Fork 到后台
    pid = os.fork()
    if pid > 0:
        # 父进程
        print(f"Monitor daemon started (PID {pid})")
        print(f"PID file: {PID_FILE}")
        print(f"Log file: {LOG_FILE}")
        return

    # 子进程：创建新会话
    os.setsid()

    # 再 fork 一次（防止重新获取终端）
    pid2 = os.fork()
    if pid2 > 0:
        os._exit(0)

    # 重定向标准流
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = open(os.devnull, "r")
    os.dup2(devnull.fileno(), sys.stdin.fileno())

    log_out = open(os.path.join(LOG_DIR, "monitor_stdout.log"), "a")
    os.dup2(log_out.fileno(), sys.stdout.fileno())
    os.dup2(log_out.fileno(), sys.stderr.fileno())

    daemon_loop(logger, daemon_config)


def cmd_stop():
    """停止守护进程。"""
    if not os.path.exists(PID_FILE):
        print("No monitor daemon running (PID file not found).")
        return

    with open(PID_FILE, "r") as f:
        pid = f.read().strip()

    if not pid:
        print("PID file is empty.")
        os.remove(PID_FILE)
        return

    pid = int(pid)
    if os.path.exists(f"/proc/{pid}"):
        os.kill(pid, signal.SIGTERM)
        print(f"Sent SIGTERM to monitor daemon (PID {pid})")
        # 等待进程退出
        for _ in range(10):
            time.sleep(1)
            if not os.path.exists(f"/proc/{pid}"):
                print("Monitor daemon stopped.")
                return
        print(f"Warning: daemon (PID {pid}) did not stop within 10s")
    else:
        print(f"Monitor daemon (PID {pid}) is not running.")
        os.remove(PID_FILE)


def cmd_status():
    """查看守护进程状态。"""
    if not os.path.exists(PID_FILE):
        print("Monitor daemon: NOT RUNNING")
        return

    with open(PID_FILE, "r") as f:
        pid = f.read().strip()

    if pid and os.path.exists(f"/proc/{pid}"):
        print(f"Monitor daemon: RUNNING (PID {pid})")
    else:
        print(f"Monitor daemon: NOT RUNNING (stale PID file)")
        try:
            os.remove(PID_FILE)
        except OSError:
            pass

    # 显示最近日志
    if os.path.exists(LOG_FILE):
        print(f"\nRecent log ({LOG_FILE}):")
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-10:]:
                    print(f"  {line.rstrip()}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Taiji task monitor daemon")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Run a single monitoring check")
    group.add_argument("--daemon", action="store_true", help="Start as background daemon")
    group.add_argument("--stop", action="store_true", help="Stop the daemon")
    group.add_argument("--status", action="store_true", help="Show daemon status")
    args = parser.parse_args()

    if args.stop:
        cmd_stop()
        return

    if args.status:
        cmd_status()
        return

    logger = setup_logging()
    daemon_config = load_defaults()

    if args.once:
        monitor_once(logger, daemon_config)
    elif args.daemon:
        cmd_daemon(logger, daemon_config)


if __name__ == "__main__":
    main()

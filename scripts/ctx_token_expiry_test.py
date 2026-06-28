"""
context_token 过期时间测试脚本

每 30 分钟通过 bridge API 发送一条测试消息，记录成功/失败和时间戳。
当 ret=-2 出现时，可以精确判断 context_token 的过期时限。

使用方法：python scripts/ctx_token_expiry_test.py
结果写入：data/ctx_token_expiry_test.log
"""
import urllib.request
import json
import time
import os
from datetime import datetime

BRIDGE_URL = "http://127.0.0.1:18012"
CONVERSATION_ID = "1ad29ca6d061-im-bot:o9cq802henxdQ7AEnwzRrkRtX0Rg@im.wechat"
LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "ctx_token_expiry_test.log")
INTERVAL_SECONDS = 30 * 60  # 30 minutes


def get_conversation():
    """Get current conversation info from bridge."""
    try:
        resp = urllib.request.urlopen(f"{BRIDGE_URL}/api/wechat/conversations", timeout=10)
        data = json.loads(resp.read().decode())
        for conv in data.get("data", []):
            if conv["id"] == CONVERSATION_ID:
                return conv
    except Exception as e:
        return {"error": str(e)}
    return None


def send_test_message():
    """Send a test message via bridge API."""
    body = json.dumps({
        "conversation_id": CONVERSATION_ID,
        "text": f"ctx_token expiry test - {datetime.now().strftime('%H:%M')}"
    }).encode()
    req = urllib.request.Request(
        f"{BRIDGE_URL}/api/wechat/send",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"success": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def log_result(result, conv_info):
    """Append a line to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success = result.get("success", False)
    status = "OK" if success else "FAIL"
    error = ""
    if not success:
        for r in result.get("results", []):
            error = r.get("error", "")
            break
        if not error:
            error = result.get("error", "")

    last_seen = ""
    msg_count = ""
    if conv_info and isinstance(conv_info, dict):
        last_seen = conv_info.get("last_seen_at", "")
        msg_count = str(conv_info.get("message_count", ""))

    line = f"{timestamp} | {status} | error={error} | last_seen={last_seen} | msg_count={msg_count}\n"
    print(line.strip())
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def main():
    print(f"=== context_token expiry test started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"Interval: {INTERVAL_SECONDS // 60} minutes")
    print(f"Log file: {os.path.abspath(LOG_FILE)}")
    print(f"Conversation: {CONVERSATION_ID}")
    print()

    # Record start time
    start_line = f"\n=== Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n"
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(start_line)

    round_num = 0
    while True:
        round_num += 1
        print(f"\n--- Round {round_num} at {datetime.now().strftime('%H:%M:%S')} ---")

        conv_info = get_conversation()
        result = send_test_message()
        log_result(result, conv_info)

        if not result.get("success"):
            print(f"FAILED! Waiting for manual user message to bot, then continuing...")
            # On failure, wait longer before next attempt to avoid spamming
            time.sleep(INTERVAL_SECONDS)
        else:
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()

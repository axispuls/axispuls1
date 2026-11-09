import os
import time
import requests
import mimetypes
import threading
from typing import Tuple, Dict, Any, List, Optional, Callable

try:
    from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor
    HAS_TOOLBELT = True
except Exception:
    HAS_TOOLBELT = False

from .security_utils import mask_token
from .ssl_helper import apply_ssl_fix, get_permanent_ca_bundle
from .state_manager import set_last_upload_speed

BALE_BASE_URL = "https://tapi.bale.ai/bot"

apply_ssl_fix()

def get_bot_info(bot_token: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Checks token validity by calling getMe.
    Returns: (is_valid, message, bot_data)
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    if not token:
        return False, "توکن ربات وارد نشده است.", {}

    url = f"{BALE_BASE_URL}{token}/getMe"
    try:
        response = requests.get(url, timeout=12, verify=ca_bundle)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            result = data.get("result", {})
            bot_name = result.get("first_name", "ربات بله")
            username = result.get("username", "")
            return True, f"اتصال به ربات موفقیت‌آمیز بود: {bot_name} (@{username})", result
        else:
            err_desc = data.get("description", "توکن نامعتبر است.")
            return False, f"خطای بله ({response.status_code}): {err_desc}", {}
    except requests.exceptions.RequestException as e:
        return False, f"خطا در اتصال به سرور بله: {str(e)}", {}
    except Exception as e:
        return False, f"خطای ناشناخته: {str(e)}", {}

def verify_bot_token_and_username(bot_token: str, expected_username: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Inquires Bale API to verify that:
    1. The bot_token is valid and can connect to Bale.
    2. The bot username returned by Bale getMe matches the expected_username entered by the user.
    """
    token = str(bot_token).strip()
    if not token:
        return False, "توکن بازو (ربات) وارد نشده است.", {}

    exp_clean = str(expected_username).strip().lstrip('@').lower()
    if not exp_clean:
        return False, "آیدی بازو (ربات) وارد نشده است. لطفاً آیدی بازو را وارد نمایید (مثال: @my_bot).", {}

    ok, msg, result = get_bot_info(token)
    if not ok:
        return False, f"استعلام توکن ناموفق بود: {msg}", {}

    actual_raw = str(result.get("username", "")).strip()
    actual_clean = actual_raw.lstrip('@').lower()

    if actual_clean != exp_clean:
        return False, (
            f"عدم تطابق آیدی ربات با توکن:\n"
            f"• آیدی وارد شده توسط شما: @{exp_clean}\n"
            f"• آیدی واقعی ثبت‌شده در بله برای این توکن: @{actual_raw}\n\n"
            f"لطفاً یا آیدی بازو را اصلاح فرمایید یا توکن صحیح مربوط به بازوی @{exp_clean} را وارد نمایید."
        ), result

    bot_name = result.get("first_name", "بازوی بله")
    return True, f"استعلام موفقیت‌آمیز بود: بازوی {bot_name} (@{actual_raw}) تایید شد.", result

def send_message(
    bot_token: str,
    chat_id: str,
    text: str,
    retries: int = 3,
    reply_markup: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Sends a text message to the specified chat_id with optional reply_markup.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    cid = str(chat_id).strip()
    if not token or not cid:
        return False, "توکن یا شناسه کاربر خالی است."

    url = f"{BALE_BASE_URL}{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": cid,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=20, verify=ca_bundle)
            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code == 200 and data.get("ok"):
                return True, "پیام با موفقیت ارسال شد."
            else:
                last_error = data.get("description", f"کد خطا: {response.status_code}")
                if response.status_code in (400, 403, 404):
                    break
        except requests.exceptions.RequestException as e:
            last_error = f"خطای شبکه: {str(e)}"
        except Exception as e:
            last_error = f"خطای غیرمنتظره در ارسال پیام: {str(e)}"
        time.sleep(2)

    return False, f"عدم موفقیت در ارسال پیام به {cid}: {last_error}"

def send_message_with_id(
    bot_token: str,
    chat_id: str,
    text: str,
    retries: int = 3,
    reply_markup: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str, Optional[int]]:
    """
    Sends a text message to chat_id and returns (success, message, message_id).
    Used to track message IDs for clean deletion after completion.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    cid = str(chat_id).strip()
    if not token or not cid:
        return False, "توکن یا شناسه کاربر خالی است.", None

    url = f"{BALE_BASE_URL}{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": cid,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=20, verify=ca_bundle)
            try:
                data = response.json()
            except Exception:
                data = {}

            if response.status_code == 200 and data.get("ok"):
                msg_id = data.get("result", {}).get("message_id")
                return True, "پیام با موفقیت ارسال شد.", msg_id
            else:
                last_error = data.get("description", f"کد خطا: {response.status_code}")
                if response.status_code in (400, 403, 404):
                    break
        except requests.exceptions.RequestException as e:
            last_error = f"خطای شبکه: {str(e)}"
        except Exception as e:
            last_error = f"خطای غیرمنتظره در ارسال پیام: {str(e)}"
        time.sleep(2)

    return False, f"عدم موفقیت در ارسال پیام به {cid}: {last_error}", None

def delete_message(bot_token: str, chat_id: str, message_id: int) -> bool:
    """
    Deletes a message from Bale chat via /deleteMessage API.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    cid = str(chat_id).strip()
    if not token or not cid or not message_id:
        return False

    url = f"{BALE_BASE_URL}{token}/deleteMessage"
    payload = {
        "chat_id": cid,
        "message_id": message_id
    }
    try:
        response = requests.post(url, json=payload, timeout=10, verify=ca_bundle)
        if response.status_code == 200:
            return bool(response.json().get("ok"))
    except Exception:
        pass
    return False

def delete_messages_async(bot_token: str, items: List[Tuple[str, int]]) -> None:
    """
    Deletes a list of (chat_id, message_id) items asynchronously in background
    so user chat is cleaned without blocking.
    """
    if not items:
        return

    def _worker():
        for cid, mid in items:
            try:
                delete_message(bot_token, cid, mid)
                time.sleep(0.08)
            except Exception:
                pass

    t = threading.Thread(target=_worker, daemon=True, name="BaleMsgDeleter")
    t.start()

def answer_callback_query(bot_token: str, callback_query_id: str, text: Optional[str] = None) -> bool:
    """
    Answers an incoming callback_query from inline buttons in Bale.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    cqid = str(callback_query_id).strip()
    if not token or not cqid:
        return False

    url = f"{BALE_BASE_URL}{token}/answerCallbackQuery"
    payload: Dict[str, Any] = {"callback_query_id": cqid}
    if text:
        payload["text"] = text
    try:
        resp = requests.post(url, json=payload, timeout=8, verify=ca_bundle)
        return resp.status_code == 200
    except Exception:
        return False

def send_message_async(bot_token: str, chat_id: str, text: str) -> None:
    """
    Sends a text message asynchronously in a background daemon thread
    so that it does not block ongoing file uploads or socket execution.
    """
    t = threading.Thread(target=send_message, args=(bot_token, chat_id, text), daemon=True)
    t.start()

def broadcast_message_async(bot_token: str, user_ids: List[str], text: str) -> None:
    """
    Broadcasts a message to all user IDs asynchronously in daemon threads.
    """
    for uid in user_ids:
        cid = str(uid).strip()
        if cid:
            send_message_async(bot_token, cid, text)

def send_document(
    bot_token: str,
    chat_id: str,
    file_path: str,
    caption: str = "",
    retries: int = 3,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, int], None]] = None
) -> Tuple[bool, str]:
    """
    Sends a file/document to the specified chat_id with upload speed metrics,
    per-attempt logging, real-time 20% progress milestones, and a 300-second resilient timeout.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    cid = str(chat_id).strip()
    if not token or not cid:
        return False, "توکن یا شناسه کاربر خالی است."

    if not os.path.isfile(file_path):
        return False, f"فایل یافت نشد: {file_path}"

    filename = os.path.basename(file_path)
    file_size_bytes = os.path.getsize(file_path)
    url = f"{BALE_BASE_URL}{token}/sendDocument"

    # Handle 0-byte files: Bale server rejects 0-byte uploads with 413 Request Entity Too Large.
    # Auto-wrap in-memory zip if size is 0.
    is_empty_file = (file_size_bytes == 0)
    if is_empty_file:
        import io, zipfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, b'')
        upload_bytes = zip_buf.getvalue()
        upload_filename = f"{filename}.zip"
        content_type = "application/zip"
        actual_bytes_to_send = len(upload_bytes)
    else:
        upload_bytes = None
        upload_filename = filename
        actual_bytes_to_send = file_size_bytes
        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"

    last_error = ""
    for attempt in range(1, retries + 1):
        f_handle = None
        t_start = time.time()
        last_reported_pct = [0]
        last_reported_time = [0.0]

        try:
            if is_empty_file or not HAS_TOOLBELT:
                if is_empty_file:
                    files = {
                        "document": (upload_filename, upload_bytes, content_type)
                    }
                else:
                    f_handle = open(file_path, "rb")
                    files = {
                        "document": (upload_filename, f_handle, content_type)
                    }
                data = {
                    "chat_id": cid
                }
                if caption:
                    data["caption"] = caption

                response = requests.post(url, data=data, files=files, timeout=(20, 300), verify=ca_bundle)
            else:
                f_handle = open(file_path, "rb")
                fields = {
                    "chat_id": cid,
                    "document": (upload_filename, f_handle, content_type)
                }
                if caption:
                    fields["caption"] = caption

                def _on_upload_progress(monitor):
                    if not progress_callback or monitor.len <= 0:
                        return
                    pct = int((monitor.bytes_read / monitor.len) * 100)
                    milestone = (pct // 20) * 20
                    now = time.time()
                    if 20 <= milestone <= 80 and milestone > last_reported_pct[0]:
                        if (now - last_reported_time[0]) >= 0.8:
                            last_reported_pct[0] = milestone
                            last_reported_time[0] = now
                            try:
                                progress_callback(milestone, monitor.bytes_read, monitor.len)
                            except Exception:
                                pass

                encoder = MultipartEncoder(fields=fields)
                monitor = MultipartEncoderMonitor(encoder, _on_upload_progress)
                headers = {"Content-Type": monitor.content_type}
                response = requests.post(url, data=monitor, headers=headers, timeout=(20, 300), verify=ca_bundle)

            try:
                res_data = response.json()
            except Exception:
                res_data = {}

            elapsed_sec = max(0.1, time.time() - t_start)
            speed_kbps = (actual_bytes_to_send / 1024) / elapsed_sec

            if response.status_code == 200 and res_data.get("ok"):
                # Record measured real-time upload speed for adaptive part sizing
                try:
                    speed_bps = actual_bytes_to_send / elapsed_sec
                    set_last_upload_speed(speed_bps)
                except Exception:
                    pass

                # Report 100% completion if progress callback was registered
                if progress_callback:
                    try:
                        progress_callback(100, actual_bytes_to_send, actual_bytes_to_send)
                    except Exception:
                        pass

                speed_text = f"{speed_kbps:.1f} KB/s" if speed_kbps >= 1 else f"{speed_kbps * 1024:.0f} B/s"
                time_text = f"{elapsed_sec:.1f} ثانیه" if elapsed_sec < 60 else f"{int(elapsed_sec // 60)} دقیقه و {int(elapsed_sec % 60)} ثانیه"
                return True, f"فایل {filename} با موفقیت به کاربر {cid} ارسال شد (زمان آپلود: {time_text} | سرعت: {speed_text})."
            else:
                last_error = res_data.get("description", f"کد خطا: {response.status_code}")
                if response.status_code in (400, 403, 404):
                    break
        except requests.exceptions.Timeout:
            elapsed_sec = int(time.time() - t_start)
            last_error = f"خطای وقفه زمانی (Timeout بعد از {elapsed_sec} ثانیه) - کندی سرعت آپلود یا اختلال اینترنت"
            if log_callback and attempt < retries:
                log_callback(f"⚠️ تلاش {attempt}/{retries} با وقفه زمانی (Timeout) مواجه شد. در حال تلاش مجدد...")
        except requests.exceptions.RequestException as e:
            last_error = f"خطای شبکه در ارسال فایل: {str(e)}"
            if log_callback and attempt < retries:
                log_callback(f"⚠️ تلاش {attempt}/{retries} به دلیل اختلال شبکه ناموفق بود: {str(e)} - تلاش بعدی...")
        except Exception as e:
            last_error = f"خطای غیرمنتظره در ارسال فایل: {str(e)}"
            if log_callback and attempt < retries:
                log_callback(f"⚠️ تلاش {attempt}/{retries} با خطای غیرمنتظره مواجه شد: {str(e)}")
        finally:
            if f_handle:
                try:
                    f_handle.close()
                except Exception:
                    pass

        if attempt < retries:
            time.sleep(4)

    return False, f"خطا در ارسال فایل به {cid}: {last_error}"

def broadcast_document(
    bot_token: str,
    user_ids: List[str],
    file_path: str,
    caption: str = "",
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[str, int, int, int], None]] = None
) -> Dict[str, Tuple[bool, str]]:
    """
    Sends the document to all provided user IDs with per-user progress reporting.
    Returns a dict mapping chat_id to (success, message).
    """
    results = {}
    for uid in user_ids:
        cid = str(uid).strip()
        if not cid:
            continue

        user_cb = None
        if progress_callback:
            user_cb = lambda pct, b_read, b_tot, target_cid=cid: progress_callback(target_cid, pct, b_read, b_tot)

        success, msg = send_document(
            bot_token,
            cid,
            file_path,
            caption=caption,
            log_callback=log_callback,
            progress_callback=user_cb
        )
        results[cid] = (success, msg)
    return results

def broadcast_message(bot_token: str, user_ids: List[str], text: str) -> Dict[str, Tuple[bool, str]]:
    """
    Sends a text message to all provided user IDs.
    Returns a dict mapping chat_id to (success, message).
    """
    results = {}
    for uid in user_ids:
        cid = str(uid).strip()
        if not cid:
            continue
        success, msg = send_message(bot_token, cid, text)
        results[cid] = (success, msg)
    return results

def get_file(bot_token: str, file_id: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Calls getFile on Bale Bot API to obtain file metadata and download path.
    """
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    fid = str(file_id).strip()
    if not token or not fid:
        return False, "توکن یا شناسه فایل خالی است.", {}

    url = f"{BALE_BASE_URL}{token}/getFile"
    try:
        response = requests.get(url, params={"file_id": fid}, timeout=20, verify=ca_bundle)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            result = data.get("result", {})
            return True, "اطلاعات فایل دریافت شد.", result
        else:
            err = data.get("description", f"کد خطا: {response.status_code}")
            return False, f"خطای بله در getFile: {err}", {}
    except Exception as e:
        return False, f"خطا در دریافت اطلاعات فایل: {e}", {}

def download_file(
    bot_token: str,
    file_id: str,
    dest_path: str,
    progress_callback: Optional[Callable[[int, int, int], None]] = None
) -> Tuple[bool, str]:
    """
    Downloads a file by file_id from Bale to dest_path using chunked streaming.
    """
    from pathlib import Path
    ca_bundle = apply_ssl_fix()
    token = str(bot_token).strip()
    ok, msg, file_data = get_file(token, file_id)
    if not ok:
        return False, msg

    file_path = file_data.get("file_path", "")
    if not file_path:
        return False, "مسیر فایل (file_path) در پاسخ سرور یافت نشد."

    if file_path.startswith("http://") or file_path.startswith("https://"):
        download_url = file_path
    else:
        download_url = f"https://tapi.bale.ai/file/bot{token}/{file_path}"

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest.with_suffix(".tmp_download")

    try:
        with requests.get(download_url, stream=True, timeout=90, verify=ca_bundle) as r:
            r.raise_for_status()
            total_length = int(r.headers.get("content-length", 0)) or file_data.get("file_size", 0)
            downloaded = 0
            with open(temp_dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_length > 0:
                            pct = min(100, int((downloaded / total_length) * 100))
                            progress_callback(pct, downloaded, total_length)

        if temp_dest.exists():
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass
            temp_dest.rename(dest)
            return True, f"فایل با موفقیت دانلود و در {dest.name} ذخیره شد."
        return False, "فایل دانلودشده در مسیر موقت یافت نشد."
    except Exception as e:
        if temp_dest.exists():
            try:
                temp_dest.unlink()
            except Exception:
                pass
        return False, f"خطا در دانلود فایل: {e}"

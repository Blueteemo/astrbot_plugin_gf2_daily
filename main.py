# -*- coding: utf-8 -*-
"""少前2社区每日任务插件"""

import hashlib
import asyncio
import base64
import aiohttp
from typing import Optional, List, Dict, Any, Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

BASE_API = "https://gf2-bbs-api.exiliumgf.com"
ENCRYPTION_KEY = "a86a86^oH$04r6A1"
COMMON_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def _encrypt_data(text: str, key: str) -> str:
    """AES-128-CBC encrypt + URL-safe base64 (matches official website JS)"""
    key_bytes = key.encode("utf-8")
    cipher = AES.new(key_bytes, AES.MODE_CBC, key_bytes)
    padded = pad(text.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded)
    b64 = base64.b64encode(encrypted).decode("utf-8")
    return b64.replace("+", "-").replace("/", "_").rstrip("=")


@register("astrbot_plugin_gf2_daily", "Blueteemo", "少前2社区每日任务", "1.0.1")
class GF2DailyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def _request(
        self,
        session: aiohttp.ClientSession,
        method: str,
        url: str,
        headers: dict = None,
        data: dict = None,
    ) -> Optional[dict]:
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            if method == "GET":
                async with session.get(url, headers=headers, timeout=timeout) as resp:
                    return await resp.json()
            else:
                async with session.post(url, headers=headers, json=data, timeout=timeout) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"GF2 API 请求失败: {e}")
            return None

    async def _login(self, session: aiohttp.ClientSession, account: str, password: str) -> Optional[str]:
        url = f"{BASE_API}/login/account"
        # Official website flow: MD5 password first, then AES-128-CBC encrypt both fields
        passwd_md5 = hashlib.md5(password.encode()).hexdigest()
        payload = {
            "account_name": _encrypt_data(account, ENCRYPTION_KEY),
            "passwd": _encrypt_data(passwd_md5, ENCRYPTION_KEY),
            "source": "phone",
        }
        headers = {**COMMON_HEADERS, "Content-Type": "application/json"}
        data = await self._request(session, "POST", url, headers, payload)
        if data and data.get("Code") == 0:
            return data.get("data", {}).get("account", {}).get("token")
        return None

    async def _sign_in(self, session: aiohttp.ClientSession, token: str) -> Tuple[bool, str, dict]:
        url = f"{BASE_API}/community/task/sign_in"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "POST", url, headers)
        if data and data.get("Code") == 0:
            sign_data = data.get("data", {})
            return True, "签到成功", sign_data
        msg = data.get("Message", "未知错误") if data else "请求失败"
        return False, msg, {}

    async def _get_task_list(self, session: aiohttp.ClientSession, token: str) -> Optional[dict]:
        url = f"{BASE_API}/community/task/get_current_task_list"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        if data and data.get("Code") == 0:
            return data.get("data") or {}
        return None

    async def _get_topic_list(self, session: aiohttp.ClientSession, token: str) -> List[dict]:
        url = (
            f"{BASE_API}/community/topic/list"
            f"?sort_type=2&category_id=5&query_type=1"
            f"&last_tid=0&pub_time=0&reply_time=0&hot_value=0"
        )
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        if data and data.get("Code") == 0:
            raw = data.get("data")
            if isinstance(raw, dict):
                return raw.get("list") or []
            return []
        return []

    async def _view_topic(self, session: aiohttp.ClientSession, token: str, topic_id: int) -> bool:
        url = f"{BASE_API}/community/topic/{topic_id}"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        return bool(data and data.get("Code") == 0)

    async def _like_topic(self, session: aiohttp.ClientSession, token: str, topic_id: int) -> bool:
        url = f"{BASE_API}/community/topic/like/{topic_id}"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        return bool(data and data.get("Code") == 0)

    async def _share_topic(self, session: aiohttp.ClientSession, token: str, topic_id: int) -> bool:
        url = f"{BASE_API}/community/topic/share/{topic_id}"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        return bool(data and data.get("Code") == 0)

    async def _get_exchange_list(self, session: aiohttp.ClientSession, token: str) -> List[dict]:
        url = f"{BASE_API}/community/item/exchange_list"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "GET", url, headers)
        if data and data.get("Code") == 0:
            raw = data.get("data")
            if isinstance(raw, dict):
                return raw.get("list") or []
            return []
        return []

    async def _exchange_item(self, session: aiohttp.ClientSession, token: str, exchange_id: int) -> Tuple[bool, str]:
        """返回 (是否成功, 消息)"""
        url = f"{BASE_API}/community/item/exchange"
        headers = {
            **COMMON_HEADERS,
            "Authorization": token,
            "Content-Type": "application/json",
        }
        data = await self._request(session, "POST", url, headers, {"exchange_id": exchange_id})
        if data and data.get("Code") == 0:
            return True, "兑换成功"
        msg = data.get("Message", "未知错误") if data else "请求失败"
        return False, msg

    async def _get_user_info(self, session: aiohttp.ClientSession, token: str) -> Optional[dict]:
        url = f"{BASE_API}/community/member/info"
        headers = {**COMMON_HEADERS, "Authorization": token}
        data = await self._request(session, "POST", url, headers, {})
        if data and data.get("Code") == 0:
            return data.get("data", {}).get("user", {})
        return None

    def _get_configured_exchange_ids(self) -> set:
        ids = set()
        for i in range(1, 11):
            if self.config.get(f"exchange_{i}", False):
                ids.add(i)
        return ids

    @filter.command("gf2")
    async def gf2(self, event: AstrMessageEvent):
        """少前2社区每日任务 用法: /gf2 - 执行完整每日任务 /gf2 签到 - 仅签到 /gf2 状态 - 查看积分/等级 /gf2 兑换 - 查看商品列表 /gf2 兑换 <ID> - 手动兑换指定商品 /gf2 调试 - 查看原始API数据"""
        account = self.config.get("account", "")
        password = self.config.get("password", "")
        if not account or not password:
            yield event.plain_result("请先在插件配置中填写社区账号和密码")
            return

        args = event.message_str.strip().split()
        if len(args) == 1:
            sub_cmd = "每日"
        else:
            sub_cmd = args[1]

        async with aiohttp.ClientSession() as session:
            token = await self._login(session, account, password)
            if not token:
                yield event.plain_result("登录失败，请检查账号密码")
                return

            if sub_cmd == "签到":
                ok, msg, _ = await self._sign_in(session, token)
                status = "成功" if ok else "失败"
                yield event.plain_result(f"签到{status}: {msg}")
                return

            if sub_cmd == "状态":
                user = await self._get_user_info(session, token)
                if user:
                    yield event.plain_result(
                        f"少前2社区状态\n"
                        f"昵称: {user.get('nick_name')}\n"
                        f"等级: Lv.{user.get('level')}\n"
                        f"经验: {user.get('exp')}/{user.get('next_lv_exp')}\n"
                        f"积分: {user.get('score')}"
                    )
                else:
                    yield event.plain_result("获取状态失败")
                return

            if sub_cmd == "调试":
                task_data = await self._get_task_list(session, token)
                topics = await self._get_topic_list(session, token)
                items = await self._get_exchange_list(session, token)
                debug_info = [
                    "=== GF2 调试信息 ===",
                    f"任务列表原始数据: {task_data}",
                    f"帖子列表数量: {len(topics)}",
                    f"商品列表数量: {len(items)}",
                ]
                # 解析任务完成状态
                if task_data and isinstance(task_data, dict):
                    for key in ("daily_task", "task_list", "tasks", "list"):
                        if key in task_data and isinstance(task_data[key], list):
                            debug_info.append(f"\n任务字段名: {key}")
                            for task in task_data[key]:
                                if isinstance(task, dict):
                                    name = task.get("task_name") or task.get("name") or "未知"
                                    complete = task.get("complete_count", 0)
                                    max_count = task.get("max_complete_count", 0)
                                    status = "已完成" if complete >= max_count else f"未完成({complete}/{max_count})"
                                    debug_info.append(f"  - {name}: {status}")
                            break
                yield event.plain_result("\n".join(debug_info))
                return

            if sub_cmd == "兑换":
                if len(args) > 2 and args[2].isdigit():
                    exchange_id = int(args[2])
                    items = await self._get_exchange_list(session, token)
                    target = next((i for i in items if i["exchange_id"] == exchange_id), None)
                    if not target:
                        yield event.plain_result(f"未找到 ID={exchange_id} 的商品")
                        return
                    user = await self._get_user_info(session, token)
                    score = user.get("score", 0) if user else 0
                    if score < target["use_score"]:
                        yield event.plain_result(f"积分不足(需要 {target['use_score']}, 当前 {score})")
                        return
                    ok, msg = await self._exchange_item(session, token, exchange_id)
                    if ok:
                        yield event.plain_result(f"成功兑换 {target['item_name']}×{target['item_count']}")
                    else:
                        yield event.plain_result(msg)
                    return
                else:
                    items = await self._get_exchange_list(session, token)
                    if not items:
                        yield event.plain_result("获取商品列表失败")
                        return
                    lines = ["可兑换商品列表"]
                    for item in items:
                        remain = item["max_exchange_count"] - item["exchange_count"]
                        status = f"剩余{remain}次" if remain > 0 else "已兑完"
                        cycle_map = {"day": "每日", "month": "每月", "life": "限时"}
                        cycle = cycle_map.get(item["cycle"], item["cycle"])
                        lines.append(
                            f"ID:{item['exchange_id']} {item['item_name']}×{item['item_count']} "
                            f"{item['use_score']}积分 {cycle} {status}"
                        )
                    yield event.plain_result("\n".join(lines))
                    return

            # ===== 每日任务 =====
            messages = []           # 任务日志（浏览/点赞/分享/签到）
            exchange_logs = []     # 兑换日志（独立控制）
            insufficient_points = False  # 标记是否遇到积分不足

            # 1. 检查任务完成状态
            task_data = await self._get_task_list(session, token)
            incomplete_tasks = {}
            if task_data:
                # 尝试多种可能的字段名（daily_task / task_list / tasks）
                task_list = None
                for key in ("daily_task", "task_list", "tasks", "list"):
                    if key in task_data and isinstance(task_data[key], list):
                        task_list = task_data[key]
                        break
                if task_list is None:
                    # 兜底：如果 data 本身就是列表
                    if isinstance(task_data, list):
                        task_list = task_data
                    else:
                        logger.warning(f"GF2 任务列表字段未识别，原始数据: {task_data}")
                if task_list:
                    for task in task_list:
                        if not isinstance(task, dict):
                            continue
                        name = task.get("task_name") or task.get("name") or task.get("title", "未知任务")
                        complete = task.get("complete_count", 0)
                        max_count = task.get("max_complete_count", 0)
                        if complete < max_count:
                            incomplete_tasks[name] = max_count - complete
            logger.info(f"GF2 未完成任务: {incomplete_tasks}")

            if not incomplete_tasks:
                messages.append("今日任务已全部完成✨")

            # 2. 执行未完成的浏览/点赞/分享
            topics = await self._get_topic_list(session, token)
            if not topics:
                messages.append("未获取到帖子")
            else:
                if "浏览帖子" in incomplete_tasks:
                    times = incomplete_tasks["浏览帖子"]
                    for topic in topics[:times]:
                        if await self._view_topic(session, token, topic["topic_id"]):
                            messages.append(f"浏览官方板块主题『{topic['title']}』")
                        await asyncio.sleep(0.5)

                if "点赞帖子" in incomplete_tasks:
                    times = incomplete_tasks["点赞帖子"]
                    for topic in topics[:times]:
                        if topic.get("is_like"):
                            await self._like_topic(session, token, topic["topic_id"])
                            await asyncio.sleep(0.05)
                            await self._like_topic(session, token, topic["topic_id"])
                            messages.append(f"取消并再次点赞官方板块主题『{topic['title']}』")
                        else:
                            await self._like_topic(session, token, topic["topic_id"])
                            messages.append(f"点赞官方板块主题『{topic['title']}』")
                        await asyncio.sleep(0.5)

                if "分享帖子" in incomplete_tasks:
                    times = incomplete_tasks["分享帖子"]
                    for topic in topics[:times]:
                        if await self._share_topic(session, token, topic["topic_id"]):
                            messages.append(f"转发官方板块主题『{topic['title']}』")
                        await asyncio.sleep(0.5)

            # 3. 兑换商品
            items = await self._get_exchange_list(session, token)
            configured_ids = self._get_configured_exchange_ids()
            auto_limited = self.config.get("auto_exchange_limited", True)
            log_exchanged = self.config.get("log_exchanged_items", False)

            # 按优先级分组：非常驻 > 月刷新 > 日刷新
            limited_items = []  # 非常驻（限时/终身）
            month_items = []    # 月刷新
            day_items = []      # 日刷新

            for item in items:
                cycle = item.get("cycle", "")
                if cycle == "day":
                    day_items.append(item)
                elif cycle == "month":
                    month_items.append(item)
                else:
                    limited_items.append(item)

            # 同优先级内按积分降序
            for lst in [limited_items, month_items, day_items]:
                lst.sort(key=lambda x: x["use_score"], reverse=True)

            stop_exchange = False

            async def process_exchange(item: dict):
                nonlocal stop_exchange, insufficient_points
                if stop_exchange:
                    return

                eid = item["exchange_id"]
                cycle = item.get("cycle", "")

                # 检查是否需要兑换
                if cycle == "day" and eid not in configured_ids:
                    return
                if cycle == "month" and eid not in configured_ids:
                    return
                if cycle not in ("day", "month") and not auto_limited:
                    return

                # 检查剩余次数
                remain = item["max_exchange_count"] - item["exchange_count"]
                if remain <= 0:
                    # 已达兑换上限，无条件输出
                    exchange_logs.append(f"已达『{item['item_name']}』兑换上限")
                    return

                # 兑换所有剩余次数
                for _ in range(remain):
                    user_info = await self._get_user_info(session, token)
                    if not user_info:
                        return

                    score = user_info.get("score", 0)
                    if score < item["use_score"]:
                        insufficient_points = True
                        stop_exchange = True
                        return

                    ok, msg = await self._exchange_item(session, token, eid)
                    if ok:
                        exchange_logs.append(
                            f"消耗积分{item['use_score']}，成功兑换『{item['item_name']}×{item['item_count']}』"
                        )
                    else:
                        # 兑换失败，无条件输出
                        exchange_logs.append(f"兑换失败『{item['item_name']}』：{msg}")
                        stop_exchange = True
                        return

                    await asyncio.sleep(0.5)

            for item in limited_items:
                await process_exchange(item)
            for item in month_items:
                await process_exchange(item)
            for item in day_items:
                await process_exchange(item)

            # 4. 签到
            user_info = await self._get_user_info(session, token)
            ok, msg, sign_data = await self._sign_in(session, token)

            # 5. 汇总输出
            # exchange_logs 中有三类消息：
            #   - "已达『xxx』兑换上限"    → 已兑换/已达上限（无需尝试）
            #   - "兑换失败『xxx』：原因"  → 兑换操作失败
            #   - "消耗积分xx，成功兑换..." → 本次新兑换成功
            already_exhausted = [log for log in exchange_logs if log.startswith("已达")]
            failed_logs = [log for log in exchange_logs if log.startswith("兑换失败")]
            new_exchanged = [log for log in exchange_logs if log.startswith("消耗")]

            all_messages = []

            if ok and sign_data:
                # ===== 首次签到成功 =====
                get_item_name = sign_data.get("get_item_name", "奖励")
                get_item_count = sign_data.get("get_item_count", 0)
                all_messages.append(
                    f"{user_info.get('game_nick_name', '用户')}(UID:{user_info.get('game_uid', '?')})"
                    f"签到成功，获得{get_item_name}×{get_item_count}"
                )
                # 任务日志（浏览/点赞/分享/签到奖励）
                all_messages.extend(messages)
                # 积分不足
                if insufficient_points:
                    all_messages.append("积分不足，停止兑换，保留积分")
                # 已兑换商品：OFF时不输出，ON时输出
                if log_exchanged:
                    all_messages.extend(already_exhausted)
                # 新兑换成功和失败总是输出（失败需告知用户）
                all_messages.extend(new_exchanged)
                all_messages.extend(failed_logs)
            else:
                # ===== 重复签到 =====
                all_messages.append("今天已经签到过了✨")
                # 已兑换商品：OFF时不输出，ON时输出
                if log_exchanged:
                    all_messages.extend(already_exhausted)
                # 重复签到时积分不足/兑换失败不输出（会通过已达上限体现）
                if log_exchanged:
                    all_messages.extend(new_exchanged)
                    all_messages.extend(failed_logs)

            yield event.plain_result("\n".join(all_messages))

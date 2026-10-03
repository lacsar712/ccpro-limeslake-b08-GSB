"""石灰熟化池业务规则。"""

from __future__ import annotations

from app.models import Pond, SlakeBatch, utcnow

MIN_PEAK_TEMP_FOR_DRAWN = 60.0


class RuleError(ValueError):
    """业务规则校验失败。"""


class PeakConflictError(RuleError):
    """并发冲突：该班峰值已被他人先行修改（HTTP 409）。"""


# 峰值输入框留空且未勾选清空时，表示「本次不改峰值」。
PEAK_UNCHANGED = object()


def latest_batch_for_pond(pond: Pond) -> SlakeBatch | None:
    if not pond.batches:
        return None
    return max(pond.batches, key=lambda b: b.started_at)


def latest_batch_for_update(pond_id: int) -> SlakeBatch | None:
    """取最近一班并对该行加写锁（SELECT ... FOR UPDATE）。

    两人几乎同时改同一班峰值时，后到的事务在此阻塞，等先到者提交后
    看到最新 lock_version，再由版本校验拒绝（只许一版生效）。
    """
    return (
        SlakeBatch.query.filter_by(pond_id=pond_id)
        .order_by(SlakeBatch.started_at.desc())
        .with_for_update()
        .first()
    )


def parse_peak(peak_raw: str | None, clear: bool = False):
    """解析抽屉里的峰值输入。

    - 勾选「清空为未测」→ None（空峰值，显示为「未测」）
    - 未勾选且留空 → PEAK_UNCHANGED（保留库值，不写死任何数字）
    - 未勾选且填值 → float
    """
    if clear:
        return None
    peak_raw = (peak_raw or "").strip()
    if not peak_raw:
        return PEAK_UNCHANGED
    try:
        return float(peak_raw)
    except ValueError as exc:
        raise RuleError("峰值温度格式无效") from exc


def apply_peak(batch: SlakeBatch, value, actor: str | None) -> bool:
    """把解析后的峰值落到批次上，并留痕登记人/时间。返回是否发生变化。"""
    if value is PEAK_UNCHANGED:
        return False
    if value == batch.peak_temp_c:
        return False
    batch.peak_temp_c = value
    if value is None:
        # 回到「未测」状态，抹掉上一次登记留痕。
        batch.peak_recorded_by = None
        batch.peak_recorded_at = None
    else:
        batch.peak_recorded_by = actor
        batch.peak_recorded_at = utcnow()
    return True


def assert_version(batch: SlakeBatch, submitted_version: int | None) -> None:
    """乐观锁版本校验：表单必须基于当前版本提交。"""
    if submitted_version is None or submitted_version != batch.lock_version:
        raise PeakConflictError(
            "该班峰值刚被他人修改，本页已是旧版本，已为你刷新最新数据，请确认后重新提交"
        )


def can_mark_pond_drawn(pond: Pond) -> tuple[bool, str]:
    """
    熟化池转为「已出灰」(drawn) 的前提：
    最近一条熟化批次的峰值温度已记录，且 >= 60℃。
    """
    latest = latest_batch_for_pond(pond)
    if latest is None:
        return False, "该池尚无熟化批次，不能标记为已出灰"
    if latest.peak_temp_c is None:
        return False, "最近批次尚未测量峰值（未测），不能标记为已出灰"
    if latest.peak_temp_c < MIN_PEAK_TEMP_FOR_DRAWN:
        return (
            False,
            f"最近批次峰值温度 {latest.peak_temp_c}℃ 低于 {MIN_PEAK_TEMP_FOR_DRAWN:.0f}℃，不能标记为已出灰",
        )
    return True, ""


def assert_can_set_pond_status(pond: Pond, new_status: str) -> None:
    if new_status not in Pond.STATUS_CHOICES:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Pond.STATUS_DRAWN:
        ok, msg = can_mark_pond_drawn(pond)
        if not ok:
            raise RuleError(msg)

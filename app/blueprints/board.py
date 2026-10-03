from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Plant, Pond
from app.services.rules import (
    PeakConflictError,
    RuleError,
    apply_peak,
    assert_can_set_pond_status,
    assert_version,
    latest_batch_for_pond,
    latest_batch_for_update,
    parse_peak,
)

bp = Blueprint("board", __name__, url_prefix="/board")

STATUS_LABELS = {
    Pond.STATUS_FILLING: "注水中",
    Pond.STATUS_SLAKING: "熟化中",
    Pond.STATUS_DRAWN: "已出灰",
}


def _floor_context(active_plant, selected_id=None):
    """构造平面图模板上下文。

    瓦片与抽屉取数都走这里，保证三边（瓦片 / 抽屉 / 履历页）
    看到的是同一份库值。
    """
    plants = Plant.query.order_by(Plant.name).all()

    pond_cards = []
    if active_plant:
        ponds = (
            Pond.query.filter_by(plant_id=active_plant.id)
            .order_by(Pond.code)
            .all()
        )
        for pond in ponds:
            pond_cards.append({"pond": pond, "batch": latest_batch_for_pond(pond)})

    selected = None
    selected_batch = None
    if selected_id:
        selected = next(
            (c["pond"] for c in pond_cards if c["pond"].id == selected_id), None
        )
        if selected:
            selected_batch = latest_batch_for_pond(selected)

    return {
        "plants": plants,
        "active_plant": active_plant,
        "pond_cards": pond_cards,
        "selected": selected,
        "selected_batch": selected_batch,
        "status_labels": STATUS_LABELS,
    }


def _resolve_active_plant():
    plants = Plant.query.order_by(Plant.name).all()
    plant_id_raw = request.args.get("plant_id", "").strip()
    active_plant = None
    if plant_id_raw.isdigit():
        active_plant = db.session.get(Plant, int(plant_id_raw))
    if active_plant is None and plants:
        active_plant = plants[0]
    return active_plant


@bp.route("/")
@login_required
def floor_plan():
    active_plant = _resolve_active_plant()
    selected_id = request.args.get("pond", type=int)
    return render_template(
        "board/floor.html", **_floor_context(active_plant, selected_id)
    )


@bp.route("/ponds/<int:pond_id>/ops", methods=["POST"])
@login_required
def pond_ops(pond_id: int):
    pond = Pond.query.get_or_404(pond_id)
    status = request.form.get("status") or pond.status
    notes = (request.form.get("batch_notes") or "").strip()
    clear_peak = request.form.get("clear_peak") in ("1", "true", "on")
    version_raw = request.form.get("lock_version", "").strip()

    # 行锁 + 版本校验都必须在同一事务内，先锁行再判版本。
    try:
        batch = latest_batch_for_update(pond.id)
        if batch is None:
            flash("该池尚无熟化批次，无法登记峰值或出灰", "error")
            return redirect(
                url_for("board.floor_plan", plant_id=pond.plant_id, pond=pond.id)
            )

        try:
            submitted_version = int(version_raw) if version_raw else None
        except ValueError:
            submitted_version = None
        assert_version(batch, submitted_version)

        value = parse_peak(request.form.get("peak_temp_c"), clear=clear_peak)
        peak_changed = apply_peak(batch, value, current_user.username)

        batch.notes = notes
        assert_can_set_pond_status(pond, status)
        pond.status = status
        db.session.commit()
    except PeakConflictError as exc:
        # 他人已先行改完同一班峰值：本次整单作废，库值保持先提交的一版。
        db.session.rollback()
        active_plant = db.session.get(Plant, pond.plant_id)
        flash(str(exc), "error")
        return (
            render_template(
                "board/floor.html", **_floor_context(active_plant, pond.id)
            ),
            409,
        )
    except RuleError as exc:
        db.session.rollback()
        active_plant = db.session.get(Plant, pond.plant_id)
        flash(str(exc), "error")
        return (
            render_template(
                "board/floor.html", **_floor_context(active_plant, pond.id)
            ),
            422,
        )

    if peak_changed:
        flash(f"{pond.code} 本班峰值已更新，瓦片与峰值履历同步刷新", "ok")
    else:
        flash(f"{pond.code} 作业记录已更新", "ok")
    return redirect(
        url_for("board.floor_plan", plant_id=pond.plant_id, pond=pond.id)
    )

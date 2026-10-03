"""峰值履历条：按时间列出每口池各班峰值。

与平面图瓦片读的是同一张 slake_batches 表、同一套取数规则
（每池按 started_at 取各班），因此履历最新一行 == 瓦片最近一班
== 库值，差值恒为 0；空峰值一律显示「未测」，不写死数字。
"""

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.extensions import db
from app.models import Plant, Pond, SlakeBatch

bp = Blueprint("history", __name__, url_prefix="/history")


@bp.route("/")
@login_required
def peak_history():
    plants = Plant.query.order_by(Plant.name).all()

    plant_id = request.args.get("plant_id", type=int)
    pond_id = request.args.get("pond_id", type=int)

    active_plant = db.session.get(Plant, plant_id) if plant_id else None
    if active_plant is None and plants and pond_id is None:
        # 与平面图一致：未指定厂时默认落在第一个厂。
        active_plant = plants[0]

    ponds = []
    if active_plant:
        ponds = (
            Pond.query.filter_by(plant_id=active_plant.id)
            .order_by(Pond.code)
            .all()
        )

    selected_pond = db.session.get(Pond, pond_id) if pond_id else None
    if selected_pond is not None:
        # 直接按池筛时，厂跟随该池，保证厂/池两个筛选器自洽。
        active_plant = selected_pond.plant
        ponds = (
            Pond.query.filter_by(plant_id=active_plant.id)
            .order_by(Pond.code)
            .all()
        )

    query = SlakeBatch.query.join(Pond)
    if active_plant:
        query = query.filter(Pond.plant_id == active_plant.id)
    if selected_pond is not None:
        query = query.filter(SlakeBatch.pond_id == selected_pond.id)
    # 按时间倒序：最新一班永远在第一行，与瓦片最近一班对齐。
    rows = (
        query.order_by(SlakeBatch.started_at.desc(), SlakeBatch.id.desc())
        .all()
    )

    return render_template(
        "history/peak_history.html",
        plants=plants,
        active_plant=active_plant,
        ponds=ponds,
        selected_pond=selected_pond,
        rows=rows,
    )

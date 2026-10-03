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

    # 支持只带 pond_id 的深链：厂区自动跟随该池
    selected_pond = db.session.get(Pond, pond_id) if pond_id else None
    if selected_pond is not None and (
        active_plant is None or selected_pond.plant_id != active_plant.id
    ):
        active_plant = selected_pond.plant

    ponds = []
    if active_plant:
        ponds = (
            Pond.query.filter_by(plant_id=active_plant.id)
            .order_by(Pond.code)
            .all()
        )

    query = SlakeBatch.query.join(Pond)
    if active_plant:
        query = query.filter(Pond.plant_id == active_plant.id)
    if selected_pond:
        query = query.filter(SlakeBatch.pond_id == selected_pond.id)
    rows = query.order_by(
        SlakeBatch.started_at.desc(), SlakeBatch.id.desc()
    ).all()

    return render_template(
        "peaks/history.html",
        plants=plants,
        active_plant=active_plant,
        ponds=ponds,
        selected_pond=selected_pond,
        rows=rows,
    )

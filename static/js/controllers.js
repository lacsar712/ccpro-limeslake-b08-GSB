import { Application, Controller } from "https://unpkg.com/@hotwired/stimulus@3.2.2/dist/stimulus.js"

const application = Application.start()

class FlashController extends Controller {
  static targets = ["item"]
  connect() {
    window.setTimeout(() => {
      this.itemTargets.forEach((el) => {
        el.style.opacity = "0"
        el.style.transition = "opacity .4s"
      })
    }, 4000)
  }
}

class FormHintController extends Controller {
  static targets = ["status", "hint", "clearPeak", "peak"]
  connect() {
    this.update()
    this.statusTarget?.addEventListener("change", () => this.update())
    this.clearPeakTarget?.addEventListener("change", () => this.onToggleClear())
  }
  onToggleClear() {
    // 勾选「未测」后峰值输入作废：清空数值并禁用，避免 0 之类的数字混入库值。
    if (this.hasPeakTarget) {
      this.peakTarget.disabled = this.clearPeakTarget.checked
      if (this.clearPeakTarget.checked) this.peakTarget.value = ""
    }
    this.update()
  }
  update() {
    if (!this.hasHintTarget || !this.hasStatusTarget) return
    const cleared = this.hasClearPeakTarget && this.clearPeakTarget.checked
    if (cleared) {
      this.hintTarget.textContent =
        "已标记本班「未测」：库值为空，履历与瓦片都显示未测，不能出灰。"
    } else if (this.statusTarget.value === "drawn") {
      this.hintTarget.textContent =
        "当前选择「已出灰」：须存在最近班次，且峰值温度已测量并 ≥ 60℃。"
    } else {
      this.hintTarget.textContent =
        "出灰前请确认最近熟化班次已测量峰值温度且不低于 60℃。"
    }
  }
}

class BoardController extends Controller {
  static targets = ["drawer", "backdrop"]
  static values = { open: Boolean }

  connect() {
    if (this.openValue) this._setOpen(true)
  }

  openDrawer() {
    // Navigation still loads selected pond; keep drawer state consistent on SPA-less click
    this._setOpen(true)
  }

  closeDrawer(event) {
    if (event) event.preventDefault()
    this._setOpen(false)
    const closeLink = event?.currentTarget
    if (closeLink?.href) {
      window.location.href = closeLink.href
    } else if (this.hasBackdropTarget) {
      const base = new URL(window.location.href)
      base.searchParams.delete("pond")
      window.location.href = base.toString()
    }
  }

  _setOpen(open) {
    this.openValue = open
    if (this.hasDrawerTarget) {
      this.drawerTarget.classList.toggle("is-open", open)
      this.drawerTarget.setAttribute("aria-hidden", open ? "false" : "true")
    }
    if (this.hasBackdropTarget) {
      this.backdropTarget.classList.toggle("is-open", open)
    }
  }
}

application.register("flash", FlashController)
application.register("form-hint", FormHintController)
application.register("board", BoardController)

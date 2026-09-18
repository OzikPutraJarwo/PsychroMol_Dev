const NS = "http://www.w3.org/2000/svg";

const MIN_TICK_INTERVAL = 0.1;
const Y_TICK_TARGET = 7;
const MIN_FIT_HEIGHT = 220;
const LABEL_CHAR_WIDTH = 5.4;
const LABEL_GAP_Y = 13;

let counter = 0;

const CURVE_STYLE = {
  saturation: { stroke: "var(--accent)", width: 2, dash: "" },
  relative_humidity: { stroke: "var(--line)", width: 1, dash: "" },
  enthalpy: { stroke: "var(--faint)", width: 0.7, dash: "4 3" },
  wet_bulb: { stroke: "var(--faint)", width: 0.7, dash: "2 3" },
  specific_volume: { stroke: "var(--faint)", width: 0.7, dash: "1 4" },
  isotherm: { stroke: "var(--line)", width: 1, dash: "" },
  boundary: { stroke: "var(--line)", width: 1, dash: "" },
};

function el(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  return node;
}

function axisTitle(axis) {
  return `${axis.title} (${axis.unit})`;
}

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (power * factor >= raw * (1 - 1e-9)) return power * factor;
  }
  return power * 10;
}

function ticks(min, max, target) {
  const step = niceStep(max - min, target);
  const start = Math.ceil(min / step) * step;
  const found = [];
  for (let value = start; value <= max + step * 1e-6; value += step) {
    found.push(Math.abs(value) < step * 1e-6 ? 0 : value);
  }
  return found;
}

function fmt(value, digits = 1) {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}


export class Chart {
  constructor(host, options = {}) {
    this.host = host;
    this.fitHeight = Boolean(options.fitHeight);
    this.height = (this.fitHeight && this.measureHeight()) || options.height || 560;
    this.width = this.measureWidth() || options.width || 880;
    this.pad = { top: 18, right: 74, bottom: 46, left: 20 };
    this.interactive = options.interactive !== false;
    this.clip = `clip-${(counter += 1)}`;
    this.geometry = null;
    this.point = null;
    this.view = null;
    this.home = null;
    this.drag = null;
    this.svg = null;
    this.layer = null;
    this.historyRows = [];
    this.historyCoords = [];
    this.playbackPoint = null;

    this.resizeObserver = new ResizeObserver(() => this.handleResize());
    this.resizeObserver.observe(this.host);
  }

  measureWidth() {
    return Math.round(this.host.getBoundingClientRect().width);
  }

  measureHeight() {
    const height = Math.round(this.host.getBoundingClientRect().height);
    return height > 0 ? Math.max(MIN_FIT_HEIGHT, height) : 0;
  }

  handleResize() {
    const width = this.measureWidth();
    const height = this.fitHeight ? this.measureHeight() : this.height;
    if (width > 0 && height > 0 && (width !== this.width || height !== this.height)) {
      this.width = width;
      this.height = height;
      this.render();
    }
  }

  destroy() {
    this.resizeObserver.disconnect();
  }

  setGeometry(geometry) {
    this.geometry = geometry;
    const { x, y } = geometry;
    this.home = { x0: x.min, x1: x.max, y0: y.min, y1: y.max };
    this.view = { ...this.home };
    this.render();
  }

  setCurrent(point) {
    this.point = point ? { ...point, label: "Now" } : null;
    this.render();
  }

  setHistory(points) {
    this.historyRows = points || [];
    this.render();
  }

  setPlaybackPoint(point) {
    this.playbackPoint = point;
    this.render();
  }

  reset() {
    if (!this.home) return;
    this.view = { ...this.home };
    this.render();
  }

  plotWidth() { return this.width - this.pad.left - this.pad.right; }
  plotHeight() { return this.height - this.pad.top - this.pad.bottom; }

  sx(value) {
    const { x0, x1 } = this.view;
    return this.pad.left + ((value - x0) / (x1 - x0)) * this.plotWidth();
  }

  sy(value) {
    const { y0, y1 } = this.view;
    return this.height - this.pad.bottom - ((value - y0) / (y1 - y0)) * this.plotHeight();
  }

  ix(pixel) {
    const { x0, x1 } = this.view;
    return x0 + ((pixel - this.pad.left) / this.plotWidth()) * (x1 - x0);
  }

  iy(pixel) {
    const { y0, y1 } = this.view;
    return y0 + ((this.height - this.pad.bottom - pixel) / this.plotHeight()) * (y1 - y0);
  }

  ensureSvg() {
    if (this.svg) return this.svg;
    const svg = el("svg", {
      width: this.width,
      height: this.height,
      viewBox: `0 0 ${this.width} ${this.height}`,
      role: "img",
    });
    this.svg = svg;
    this.host.textContent = "";
    this.host.appendChild(svg);
    if (this.interactive) this.attach(svg);
    return svg;
  }

  render() {
    if (!this.geometry) return;
    const svg = this.ensureSvg();
    svg.setAttribute("width", this.width);
    svg.setAttribute("height", this.height);
    svg.setAttribute("viewBox", `0 0 ${this.width} ${this.height}`);
    svg.textContent = "";

    const defs = el("defs");
    const clipPath = el("clipPath", { id: this.clip });
    clipPath.appendChild(
      el("rect", {
        x: this.pad.left,
        y: this.pad.top,
        width: this.plotWidth(),
        height: this.plotHeight(),
      })
    );
    defs.appendChild(clipPath);
    svg.appendChild(defs);

    svg.appendChild(
      el("rect", {
        x: this.pad.left,
        y: this.pad.top,
        width: this.plotWidth(),
        height: this.plotHeight(),
        fill: "var(--surface)",
        stroke: "var(--line)",
      })
    );

    this.drawGrid(svg);
    this.drawCurves(svg);
    this.drawHistory(svg);
    this.drawPlayback(svg);
    this.drawPoint(svg);
    this.drawAxisTitles(svg);

    this.layer = el("g");
    svg.appendChild(this.layer);
  }

  xTickTarget() {
    return Math.max(3, Math.round(this.plotWidth() / 65));
  }

  drawGrid(svg) {
    const xt = ticks(this.view.x0, this.view.x1, this.xTickTarget());
    const yt = ticks(this.view.y0, this.view.y1, Y_TICK_TARGET);
    const group = el("g");

    for (const value of xt) {
      const x = this.sx(value);
      if (x < this.pad.left - 0.5 || x > this.width - this.pad.right + 0.5) continue;
      group.appendChild(
        el("line", {
          x1: x, y1: this.pad.top, x2: x, y2: this.height - this.pad.bottom,
          stroke: "var(--line)", "stroke-width": 0.5, opacity: 0.7,
        })
      );
      const label = el("text", {
        x, y: this.height - this.pad.bottom + 17,
        "text-anchor": "middle", "font-size": 11.5, fill: "var(--faint)",
      });
      label.textContent = Number(value.toFixed(2)).toString();
      group.appendChild(label);
    }

    for (const value of yt) {
      const y = this.sy(value);
      if (y < this.pad.top - 0.5 || y > this.height - this.pad.bottom + 0.5) continue;
      group.appendChild(
        el("line", {
          x1: this.pad.left, y1: y, x2: this.width - this.pad.right, y2: y,
          stroke: "var(--line)", "stroke-width": 0.5, opacity: 0.7,
        })
      );
      const label = el("text", {
        x: this.width - this.pad.right + 7, y: y + 4,
        "font-size": 11.5, fill: "var(--faint)",
      });
      label.textContent = Number(value.toFixed(3)).toString();
      group.appendChild(label);
    }
    svg.appendChild(group);
  }

  drawCurves(svg) {
    const group = el("g", { "clip-path": `url(#${this.clip})` });
    const project = ([a, b]) => `${this.sx(a).toFixed(2)},${this.sy(b).toFixed(2)}`;
    const placed = [];
    const roomFor = (x, y, text) => {
      const width = text.length * LABEL_CHAR_WIDTH;
      const clash = placed.some((spot) =>
        Math.abs(spot.y - y) < LABEL_GAP_Y && x < spot.x + spot.width + 6 && spot.x < x + width + 6);
      if (clash) return false;
      placed.push({ x, y, width });
      return true;
    };

    for (const curve of this.geometry.curves) {
      if (curve.family !== "target_zone") continue;
      group.appendChild(
        el("polygon", {
          points: curve.points.map(project).join(" "),
          fill: "rgba(47, 168, 74, 0.14)",
          stroke: "var(--ok)",
          "stroke-width": 1,
          "stroke-dasharray": "4 3",
        })
      );
    }

    for (const curve of this.geometry.curves) {
      if (curve.family === "target_zone") continue;
      const style = CURVE_STYLE[curve.family] || CURVE_STYLE.relative_humidity;
      const points = curve.points.map(project).join(" ");
      group.appendChild(
        el("polyline", {
          points,
          fill: "none",
          stroke: style.stroke,
          "stroke-width": style.width,
          "stroke-dasharray": style.dash || null,
          "stroke-linejoin": "round",
          opacity: curve.family === "relative_humidity" ? 0.9 : 1,
        })
      );
      if (curve.label && curve.points.length) {
        const [ax, ay] = curve.points[curve.points.length - 1];
        const x = this.sx(ax);
        const y = this.sy(ay);
        if (
          x > this.pad.left && x < this.width - this.pad.right &&
          y > this.pad.top && y < this.height - this.pad.bottom &&
          roomFor(x, y, curve.label)
        ) {
          const label = el("text", {
            x: x + 3, y: y - 3, "font-size": 10, fill: "var(--faint)",
          });
          label.textContent = curve.label;
          group.appendChild(label);
        }
      }
    }
    svg.appendChild(group);
  }

  drawHistory(svg) {
    this.historyCoords = [];
    if (!this.historyRows.length) return;
    const coords = this.historyRows.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    if (coords.length < 2) return;

    const group = el("g", { "clip-path": `url(#${this.clip})` });
    const points = coords.map((p) => `${this.sx(p.x).toFixed(2)},${this.sy(p.y).toFixed(2)}`).join(" ");
    group.appendChild(
      el("polyline", {
        points,
        fill: "none",
        stroke: "var(--muted)",
        "stroke-width": 1.3,
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        opacity: 0.5,
      })
    );
    svg.appendChild(group);
    this.historyCoords = coords;
  }

  drawPlayback(svg) {
    if (!this.playbackPoint) return;
    const { x: rawX, y: rawY } = this.playbackPoint;
    if (typeof rawX !== "number" || typeof rawY !== "number") return;
    const x = this.sx(rawX);
    const y = this.sy(rawY);
    if (
      x < this.pad.left || x > this.width - this.pad.right ||
      y < this.pad.top || y > this.height - this.pad.bottom
    ) return;

    const group = el("g", { "clip-path": `url(#${this.clip})` });
    group.appendChild(
      el("circle", { cx: x, cy: y, r: 8, fill: "var(--warning)", opacity: 0.25 })
    );
    group.appendChild(
      el("circle", {
        cx: x, cy: y, r: 4.5, fill: "var(--warning)",
        stroke: "var(--surface-solid)", "stroke-width": 1.6,
      })
    );
    svg.appendChild(group);
  }

  drawPoint(svg) {
    if (!this.point) return;
    if (typeof this.point.x !== "number" || typeof this.point.y !== "number") return;
    const x = this.sx(this.point.x);
    const y = this.sy(this.point.y);
    if (
      x < this.pad.left || x > this.width - this.pad.right ||
      y < this.pad.top || y > this.height - this.pad.bottom
    ) return;

    const group = el("g", { "clip-path": `url(#${this.clip})` });
    group.appendChild(
      el("circle", { cx: x, cy: y, r: 9, fill: "var(--accent)", opacity: 0.18 })
    );
    group.appendChild(
      el("circle", {
        cx: x, cy: y, r: 4.5, fill: "var(--accent)",
        stroke: "var(--surface)", "stroke-width": 1.6,
      })
    );
    if (this.point.label) {
      const label = el("text", {
        x: x + 11, y: y - 8, "font-size": 12, "font-weight": 600, fill: "var(--text)",
      });
      label.textContent = this.point.label;
      group.appendChild(label);
    }
    svg.appendChild(group);
  }

  drawAxisTitles(svg) {
    const x = el("text", {
      x: this.pad.left + this.plotWidth() / 2,
      y: this.height - 8,
      "text-anchor": "middle",
      "font-size": 12,
      fill: "var(--muted)",
    });
    x.textContent = axisTitle(this.geometry.x);
    svg.appendChild(x);

    const yx = this.width - 10;
    const yy = this.pad.top + this.plotHeight() / 2;
    const y = el("text", {
      x: yx,
      y: yy,
      "text-anchor": "middle",
      "font-size": 12,
      fill: "var(--muted)",
      transform: `rotate(-90 ${yx} ${yy})`,
    });
    y.textContent = axisTitle(this.geometry.y);
    svg.appendChild(y);
  }

  clampView(next) {
    const home = this.home;
    const spanX = Math.min(next.x1 - next.x0, home.x1 - home.x0);
    const spanY = Math.min(next.y1 - next.y0, home.y1 - home.y0);

    let x0 = next.x0;
    let y0 = next.y0;
    x0 = Math.min(Math.max(x0, home.x0), home.x1 - spanX);
    y0 = Math.min(Math.max(y0, home.y0), home.y1 - spanY);
    return { x0, x1: x0 + spanX, y0, y1: y0 + spanY };
  }

  attach(svg) {
    svg.style.touchAction = "none";

    svg.addEventListener("wheel", (event) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const scale = rect.width ? this.width / rect.width : 1;
      const px = (event.clientX - rect.left) * scale;
      const py = (event.clientY - rect.top) * scale;
      const anchorX = this.ix(px);
      const anchorY = this.iy(py);
      let factor = event.deltaY > 0 ? 1.18 : 1 / 1.18;
      if (factor < 1) {
        const smallestX = MIN_TICK_INTERVAL * this.xTickTarget();
        const smallestY = MIN_TICK_INTERVAL * Y_TICK_TARGET;
        factor = Math.max(
          factor,
          smallestX / (this.view.x1 - this.view.x0),
          smallestY / (this.view.y1 - this.view.y0),
        );
        if (factor >= 1) return;
      }

      const next = {
        x0: anchorX - (anchorX - this.view.x0) * factor,
        x1: anchorX + (this.view.x1 - anchorX) * factor,
        y0: anchorY - (anchorY - this.view.y0) * factor,
        y1: anchorY + (this.view.y1 - anchorY) * factor,
      };
      this.view = this.clampView(next);
      this.render();
    }, { passive: false });

    svg.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      svg.setPointerCapture(event.pointerId);
      this.drag = { x: event.clientX, y: event.clientY, view: { ...this.view } };
      if (this.layer) this.layer.textContent = "";
    });

    svg.addEventListener("pointermove", (event) => {
      if (this.drag) {
        const rect = svg.getBoundingClientRect();
        const scale = rect.width ? this.width / rect.width : 1;
        const dx = (event.clientX - this.drag.x) * scale;
        const dy = (event.clientY - this.drag.y) * scale;
        const spanX = this.drag.view.x1 - this.drag.view.x0;
        const spanY = this.drag.view.y1 - this.drag.view.y0;
        const shiftX = (dx / this.plotWidth()) * spanX;
        const shiftY = (dy / this.plotHeight()) * spanY;
        this.view = this.clampView({
          x0: this.drag.view.x0 - shiftX,
          x1: this.drag.view.x1 - shiftX,
          y0: this.drag.view.y0 + shiftY,
          y1: this.drag.view.y1 + shiftY,
        });
        this.render();
        return;
      }
      this.hover(event, svg);
    });

    svg.addEventListener("pointerleave", () => {
      if (this.layer) this.layer.textContent = "";
    });

    const release = (event) => {
      if (this.drag && svg.hasPointerCapture(event.pointerId)) {
        svg.releasePointerCapture(event.pointerId);
      }
      this.drag = null;
    };
    svg.addEventListener("pointerup", release);
    svg.addEventListener("pointercancel", release);
  }

  hover(event, svg) {
    if (!this.layer || !this.geometry) return;
    const rect = svg.getBoundingClientRect();
    const scale = rect.width ? this.width / rect.width : 1;
    const px = (event.clientX - rect.left) * scale;
    const py = (event.clientY - rect.top) * scale;
    if (
      px < this.pad.left || px > this.width - this.pad.right ||
      py < this.pad.top || py > this.height - this.pad.bottom
    ) {
      this.layer.textContent = "";
      return;
    }

    let nearest = null;
    let nearestDist = Infinity;
    for (const point of this.historyCoords) {
      const x = this.sx(point.x);
      const y = this.sy(point.y);
      const dist = Math.hypot(x - px, y - py);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = { x, y, point };
      }
    }

    this.layer.textContent = "";
    if (nearest && nearestDist <= 14) {
      this.drawSampleTooltip(nearest);
    } else {
      this.drawCrosshair(px, py);
    }
  }

  drawSampleTooltip(nearest) {
    this.layer.appendChild(
      el("line", {
        x1: nearest.x, y1: this.pad.top, x2: nearest.x, y2: this.height - this.pad.bottom,
        stroke: "var(--faint)", "stroke-width": 1, "stroke-dasharray": "3 3",
      })
    );
    this.layer.appendChild(
      el("circle", {
        cx: nearest.x, cy: nearest.y, r: 5, fill: "var(--accent)",
        stroke: "var(--surface-solid)", "stroke-width": 1.6,
      })
    );
    this.drawTooltip(nearest.x, nearest.y, nearest.point.lines);
  }

  drawCrosshair(px, py) {
    this.layer.appendChild(
      el("line", {
        x1: px, y1: this.pad.top, x2: px, y2: this.height - this.pad.bottom,
        stroke: "var(--faint)", "stroke-width": 1, "stroke-dasharray": "3 3",
      })
    );
    this.layer.appendChild(
      el("line", {
        x1: this.pad.left, y1: py, x2: this.width - this.pad.right, y2: py,
        stroke: "var(--faint)", "stroke-width": 1, "stroke-dasharray": "3 3",
      })
    );
    const xValue = this.ix(px);
    const yValue = this.iy(py);
    const lines = [
      `${fmt(xValue, 1)} ${this.geometry.x.unit}`,
      `${fmt(yValue, 2)} ${this.geometry.y.unit}`,
    ];
    this.drawTooltip(px, py, lines);
  }

  drawTooltip(x, y, lines) {
    const boxWidth = Math.max(120, Math.max(...lines.map((line) => line.length)) * 6.5 + 20);
    const boxHeight = 12 + lines.length * 15;
    let left = x + 12;
    if (left + boxWidth > this.width - this.pad.right) left = x - boxWidth - 12;
    let top = y - boxHeight - 12;
    if (top < this.pad.top) top = Math.min(y + 12, this.height - this.pad.bottom - boxHeight);

    this.layer.appendChild(
      el("rect", {
        x: left, y: top, width: boxWidth, height: boxHeight,
        rx: 8, fill: "var(--surface-solid)", stroke: "var(--line)",
      })
    );
    lines.forEach((line, index) => {
      const text = el("text", {
        x: left + 10, y: top + 18 + index * 15,
        "font-size": 11.5, fill: index === 0 ? "var(--faint)" : "var(--text)",
      });
      text.textContent = line;
      this.layer.appendChild(text);
    });
  }
}

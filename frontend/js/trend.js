const NS = "http://www.w3.org/2000/svg";

const COLOURS = [
  "var(--series-1)", "var(--series-2)", "var(--series-3)",
  "var(--series-4)", "var(--series-5)", "var(--series-6)",
];

function el(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  return node;
}

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (power * factor >= raw) return power * factor;
  }
  return power * 10;
}

function clockLabel(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function dayLabel(date) {
  return date.toLocaleDateString([], { day: "numeric", month: "short" });
}

export class Trend {
  constructor(host, options = {}) {
    this.host = host;
    this.fitHeight = Boolean(options.fitHeight);
    this.height = (this.fitHeight && this.measureHeight()) || options.height || 300;
    this.width = this.measureWidth() || options.width || 880;
    this.pad = { top: 16, right: 54, bottom: 34, left: 52 };
    this.series = [];
    this.rows = [];
    this.svg = null;
    this.layer = null;

    this.resizeObserver = new ResizeObserver(() => this.handleResize());
    this.resizeObserver.observe(this.host);
  }

  measureWidth() {
    return Math.round(this.host.getBoundingClientRect().width);
  }

  measureHeight() {
    const height = Math.round(this.host.getBoundingClientRect().height);
    return height > 0 ? Math.max(200, height) : 0;
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

  setData(rows, series) {
    this.rows = rows;
    this.series = series;
    this.render();
  }

  plotWidth() { return this.width - this.pad.left - this.pad.right; }
  plotHeight() { return this.height - this.pad.top - this.pad.bottom; }

  render() {
    this.host.textContent = "";
    const svg = el("svg", {
      width: this.width,
      height: this.height,
      viewBox: `0 0 ${this.width} ${this.height}`,
    });
    this.svg = svg;

    if (!this.rows.length || !this.series.length) {
      const text = el("text", {
        x: this.width / 2, y: this.height / 2,
        "text-anchor": "middle", "font-size": 13, fill: "var(--faint)",
      });
      text.textContent = "No readings in this range";
      svg.appendChild(text);
      this.host.appendChild(svg);
      return;
    }

    const times = this.rows.map((row) => new Date(row.measured_at).getTime());
    const tMin = Math.min(...times);
    const tMax = Math.max(...times);
    const spanT = Math.max(1, tMax - tMin);

    const bounds = this.series.map((entry) => {
      const values = this.rows
        .map((row) => row[entry.key])
        .filter((value) => typeof value === "number");
      if (!values.length) return { min: 0, max: 1 };
      let min = Math.min(...values);
      let max = Math.max(...values);
      if (max - min < 1e-9) { min -= 1; max += 1; }
      const step = niceStep(max - min, 4);
      return { min: Math.floor(min / step) * step, max: Math.ceil(max / step) * step };
    });

    const sx = (time) =>
      this.pad.left + ((time - tMin) / spanT) * this.plotWidth();
    const sy = (value, index) => {
      const { min, max } = bounds[index];
      return (
        this.height - this.pad.bottom -
        ((value - min) / (max - min || 1)) * this.plotHeight()
      );
    };

    svg.appendChild(
      el("rect", {
        x: this.pad.left, y: this.pad.top,
        width: this.plotWidth(), height: this.plotHeight(),
        fill: "var(--surface)", stroke: "var(--line)",
      })
    );

    const primary = bounds[0];
    const step = niceStep(primary.max - primary.min, 4);
    for (let value = primary.min; value <= primary.max + step * 1e-6; value += step) {
      const y = sy(value, 0);
      svg.appendChild(
        el("line", {
          x1: this.pad.left, y1: y, x2: this.width - this.pad.right, y2: y,
          stroke: "var(--line)", "stroke-width": 0.5, opacity: 0.75,
        })
      );
      const label = el("text", {
        x: this.pad.left - 7, y: y + 4,
        "text-anchor": "end", "font-size": 11, fill: COLOURS[0],
      });
      label.textContent = Number(value.toFixed(2)).toString();
      svg.appendChild(label);
    }

    if (this.series.length > 1) {
      const second = bounds[1];
      const stepB = niceStep(second.max - second.min, 4);
      for (let value = second.min; value <= second.max + stepB * 1e-6; value += stepB) {
        const y = sy(value, 1);
        const label = el("text", {
          x: this.width - this.pad.right + 7, y: y + 4,
          "font-size": 11, fill: COLOURS[1],
        });
        label.textContent = Number(value.toFixed(2)).toString();
        svg.appendChild(label);
      }
    }

    const spanHours = spanT / 3600000;
    const labelCount = Math.max(2, Math.round(this.plotWidth() / 95));
    for (let index = 0; index <= labelCount; index += 1) {
      const time = tMin + (spanT * index) / labelCount;
      const x = sx(time);
      const date = new Date(time);
      const label = el("text", {
        x, y: this.height - this.pad.bottom + 16,
        "text-anchor": "middle", "font-size": 11, fill: "var(--faint)",
      });
      label.textContent = spanHours > 48 ? dayLabel(date) : clockLabel(date);
      svg.appendChild(label);
    }

    this.series.forEach((entry, index) => {
      const points = [];
      this.rows.forEach((row) => {
        const value = row[entry.key];
        if (typeof value !== "number") return;
        points.push(`${sx(new Date(row.measured_at).getTime()).toFixed(2)},${sy(value, index).toFixed(2)}`);
      });
      svg.appendChild(
        el("polyline", {
          points: points.join(" "),
          fill: "none",
          stroke: COLOURS[index % COLOURS.length],
          "stroke-width": 1.8,
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
        })
      );
    });

    const legend = el("g");
    this.series.forEach((entry, index) => {
      const x = this.pad.left + index * 150;
      legend.appendChild(
        el("line", {
          x1: x, y1: this.pad.top - 6, x2: x + 16, y2: this.pad.top - 6,
          stroke: COLOURS[index % COLOURS.length], "stroke-width": 2.5,
        })
      );
      const label = el("text", {
        x: x + 21, y: this.pad.top - 2, "font-size": 11.5, fill: "var(--muted)",
      });
      label.textContent = `${entry.label} (${entry.unit})`;
      legend.appendChild(label);
    });
    svg.appendChild(legend);

    this.layer = el("g");
    svg.appendChild(this.layer);

    svg.addEventListener("pointermove", (event) => {
      const rect = svg.getBoundingClientRect();
      const scale = rect.width ? this.width / rect.width : 1;
      const px = (event.clientX - rect.left) * scale;
      if (px < this.pad.left || px > this.width - this.pad.right) {
        this.layer.textContent = "";
        return;
      }
      const wanted = tMin + ((px - this.pad.left) / this.plotWidth()) * spanT;
      let best = 0;
      let bestGap = Infinity;
      times.forEach((time, index) => {
        const gap = Math.abs(time - wanted);
        if (gap < bestGap) { bestGap = gap; best = index; }
      });
      this.drawMarker(sx, sy, times[best], this.rows[best]);
    });

    svg.addEventListener("pointerleave", () => {
      if (this.layer) this.layer.textContent = "";
    });

    this.host.appendChild(svg);
  }

  drawMarker(sx, sy, time, row) {
    this.layer.textContent = "";
    const x = sx(time);
    this.layer.appendChild(
      el("line", {
        x1: x, y1: this.pad.top, x2: x, y2: this.height - this.pad.bottom,
        stroke: "var(--faint)", "stroke-width": 1, "stroke-dasharray": "3 3",
      })
    );

    const lines = [new Date(time).toLocaleString([], {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    })];
    this.series.forEach((entry, index) => {
      const value = row[entry.key];
      if (typeof value !== "number") return;
      this.layer.appendChild(
        el("circle", {
          cx: x, cy: sy(value, index), r: 4,
          fill: COLOURS[index % COLOURS.length],
          stroke: "var(--surface)", "stroke-width": 1.5,
        })
      );
      lines.push(`${entry.label}  ${value.toFixed(2)} ${entry.unit}`);
    });

    const boxWidth = 176;
    const boxHeight = 16 + lines.length * 15;
    const left = x + boxWidth + 12 > this.width - this.pad.right
      ? x - boxWidth - 10
      : x + 10;

    this.layer.appendChild(
      el("rect", {
        x: left, y: this.pad.top + 6, width: boxWidth, height: boxHeight,
        rx: 8, fill: "var(--surface)", stroke: "var(--line)",
      })
    );
    lines.forEach((line, index) => {
      const text = el("text", {
        x: left + 10,
        y: this.pad.top + 26 + index * 15,
        "font-size": 11.5,
        fill: index === 0 ? "var(--faint)" : "var(--text)",
      });
      text.textContent = line;
      this.layer.appendChild(text);
    });
  }
}

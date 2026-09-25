package ru.kixbox.pulse.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.kixbox.pulse.data.Widget
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChartView(w: Widget.Chart) {
    val p = P
    val n = w.x.size
    var selected by remember(w) { mutableStateOf<Int?>(null) }
    val bars = w.series.filter { it.style != "line" }
    val lines = w.series.filter { it.style == "line" }
    val left = w.series.filter { it.axis != "right" }
    val right = w.series.filter { it.axis == "right" }
    val measurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 9.sp, color = p.faint)

    // Масштабы осей
    fun range(list: List<ru.kixbox.pulse.data.Series>, stack: Boolean): Pair<Double, Double> {
        var lo = 0.0
        var hi = 0.0
        if (stack) {
            for (i in 0 until n) {
                var pos = 0.0
                var neg = 0.0
                list.filter { it.style != "line" }.forEach { s ->
                    val v = s.values.getOrNull(i) ?: 0.0
                    if (v >= 0) pos += v else neg += v
                }
                hi = max(hi, pos); lo = min(lo, neg)
            }
            list.filter { it.style == "line" }.forEach { s -> s.values.forEach { v -> if (v != null) { hi = max(hi, v); lo = min(lo, v) } } }
        } else {
            list.forEach { s -> s.values.forEach { v -> if (v != null) { hi = max(hi, v); lo = min(lo, v) } } }
        }
        if (hi == lo) hi = lo + 1.0
        return lo to hi * 1.08
    }
    val (lLo, lHi) = range(left, w.stacked)
    val (rLo, rHi) = range(right, false)
    val leftFormat = left.firstOrNull()?.format ?: "money"
    val rightFormat = right.firstOrNull()?.format ?: "pct"

    Column {
        // Подсказка по выбранной точке
        Box(Modifier.fillMaxWidth().heightIn(min = 34.dp), contentAlignment = Alignment.CenterStart) {
            val idx = selected
            if (idx == null) {
                Text("Нажмите на график, чтобы увидеть значения", color = p.faint, fontSize = 11.sp)
            } else {
                FlowRow(
                    Modifier.background(p.cardAlt, RoundedCornerShape(10.dp)).padding(horizontal = 10.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Text(w.x.getOrElse(idx) { "" }, color = p.ink, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    w.series.forEach { s ->
                        Text(
                            "${s.name}: ${formatValue(s.values.getOrNull(idx), s.format)}",
                            color = p.seriesColor(s.color).let { if (it == p.series[1] && !p.dark) p.accent else it },
                            fontSize = 11.sp, fontWeight = FontWeight.SemiBold
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Canvas(
            Modifier.fillMaxWidth().height(190.dp).pointerInput(w) {
                detectTapGestures { o ->
                    val padL = 44.dp.toPx()
                    val padR = (if (right.isNotEmpty()) 40.dp else 6.dp).toPx()
                    val plotW = size.width - padL - padR
                    if (n > 0 && o.x >= padL - 10 && o.x <= size.width - padR + 10) {
                        val i = ((o.x - padL) / (plotW / n)).toInt().coerceIn(0, n - 1)
                        selected = if (selected == i) null else i
                    }
                }
            }
        ) {
            val padL = 44.dp.toPx()
            val padR = (if (right.isNotEmpty()) 40.dp else 6.dp).toPx()
            val padT = 6.dp.toPx()
            val slotGuess = (size.width - padL - padR) / n.coerceAtLeast(1)
            val twoLines = n <= 10 && w.x.any { measurer.measure(it, labelStyle).size.width > slotGuess - 2 }
            val padB = (if (twoLines) 28.dp else 18.dp).toPx()
            val plotW = size.width - padL - padR
            val plotH = size.height - padT - padB
            if (n == 0 || plotW <= 0) return@Canvas
            fun yL(v: Double) = padT + plotH * (1 - ((v - lLo) / (lHi - lLo))).toFloat()
            fun yR(v: Double) = padT + plotH * (1 - ((v - rLo) / (rHi - rLo))).toFloat()
            val slot = plotW / n

            // сетка и подписи оси
            for (k in 0..3) {
                val v = lLo + (lHi - lLo) / 1.08 * k / 3
                val y = yL(v)
                drawLine(p.line, Offset(padL, y), Offset(padL + plotW, y), strokeWidth = 1f,
                    pathEffect = if (k == 0) null else PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
                val t = measurer.measure(axisValue(v, leftFormat), labelStyle)
                drawText(t, topLeft = Offset(padL - t.size.width - 4.dp.toPx(), y - t.size.height / 2))
                if (right.isNotEmpty()) {
                    val rv = rLo + (rHi - rLo) / 1.08 * k / 3
                    val rt = measurer.measure(axisValue(rv, rightFormat), labelStyle)
                    drawText(rt, topLeft = Offset(padL + plotW + 4.dp.toPx(), yR(rv) - rt.size.height / 2))
                }
            }
            if (lLo < 0) drawLine(p.muted, Offset(padL, yL(0.0)), Offset(padL + plotW, yL(0.0)), strokeWidth = 1.5f)

            selected?.let { i ->
                drawRoundRect(p.accent.copy(alpha = 0.08f), Offset(padL + i * slot, padT), Size(slot, plotH),
                    CornerRadius(6f, 6f))
            }

            // столбцы
            val barSeries = bars
            if (barSeries.isNotEmpty()) {
                val group = slot * (if (n > 20) 0.8f else 0.7f)
                for (i in 0 until n) {
                    val x0 = padL + i * slot + (slot - group) / 2
                    val dim = selected != null && selected != i
                    if (w.stacked) {
                        var pos = 0.0
                        var neg = 0.0
                        barSeries.forEach { s ->
                            val v = s.values.getOrNull(i) ?: 0.0
                            val scale: (Double) -> Float = if (s.axis == "right") ::yR else ::yL
                            val (a, b) = if (v >= 0) (pos to pos + v).also { pos += v } else (neg + v to neg).also { neg += v }
                            val top = scale(b)
                            val bottom = scale(a)
                            drawRect(p.seriesColor(s.color).copy(alpha = if (dim) .35f else 1f), Offset(x0, top),
                                Size(group, max(bottom - top, 0f)))
                        }
                    } else {
                        val bw = group / barSeries.size
                        barSeries.forEachIndexed { j, s ->
                            val v = s.values.getOrNull(i) ?: return@forEachIndexed
                            val scale: (Double) -> Float = if (s.axis == "right") ::yR else ::yL
                            val zero = scale(0.0)
                            val y = scale(v)
                            val top = min(y, zero)
                            val h = abs(zero - y)
                            val gap = if (bw > 6.dp.toPx()) 1.5.dp.toPx() else 0.5f
                            drawRoundRect(
                                p.seriesColor(s.color).copy(alpha = if (dim) .35f else 1f),
                                Offset(x0 + j * bw + gap / 2, top), Size(max(bw - gap, 1f), max(h, 1f)),
                                CornerRadius(min(bw / 4, 6f), min(bw / 4, 6f))
                            )
                        }
                    }
                }
            }
            // линии
            lines.forEach { s ->
                val scale: (Double) -> Float = if (s.axis == "right") ::yR else ::yL
                val path = Path()
                var started = false
                s.values.forEachIndexed { i, v ->
                    if (v == null) { started = false; return@forEachIndexed }
                    val x = padL + i * slot + slot / 2
                    val y = scale(v)
                    if (!started) { path.moveTo(x, y); started = true } else path.lineTo(x, y)
                }
                val c = p.seriesColor(s.color)
                drawPath(path, c, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                s.values.forEachIndexed { i, v ->
                    if (v != null && (n <= 14 || i == selected)) {
                        val x = padL + i * slot + slot / 2
                        drawCircle(c, radius = if (i == selected) 4.5.dp.toPx() else 2.5.dp.toPx(), center = Offset(x, scale(v)))
                    }
                }
            }
            // подписи X
            val every = if (twoLines) 1 else max(1, (n + 6) / 7)
            for (i in 0 until n step every) {
                val t = if (twoLines) measurer.measure(w.x[i], labelStyle.copy(color = p.muted, textAlign = androidx.compose.ui.text.style.TextAlign.Center),
                    maxLines = 2, overflow = TextOverflow.Ellipsis,
                    constraints = androidx.compose.ui.unit.Constraints(maxWidth = (slot - 2).toInt().coerceAtLeast(10)))
                else measurer.measure(w.x[i], labelStyle.copy(color = p.muted), maxLines = 1)
                val cx = padL + i * slot + slot / 2
                drawText(t, topLeft = Offset((cx - t.size.width / 2).coerceIn(0f, size.width - t.size.width),
                    size.height - t.size.height))
            }
        }
        Spacer(Modifier.height(8.dp))
        Legend(w.series.map { it.name to p.seriesColor(it.color) }, w.series.map { it.style == "line" })
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Legend(items: List<Pair<String, Color>>, lines: List<Boolean> = emptyList()) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items.forEachIndexed { i, (name, c) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (lines.getOrElse(i) { false }) Box(Modifier.size(12.dp, 3.dp).background(c, RoundedCornerShape(2.dp)))
                else Box(Modifier.size(9.dp).background(c, RoundedCornerShape(3.dp)))
                Spacer(Modifier.width(6.dp))
                Text(name, color = P.muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
fun Sparkline(values: List<Double>, color: Color, modifier: Modifier = Modifier) {
    if (values.size < 2) return
    Canvas(modifier) {
        val lo = values.min()
        val hi = values.max().let { if (it == lo) lo + 1 else it }
        val step = size.width / (values.size - 1)
        val path = Path()
        values.forEachIndexed { i, v ->
            val x = i * step
            val y = size.height - (size.height * ((v - lo) / (hi - lo))).toFloat()
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        val fill = Path().apply {
            addPath(path)
            lineTo(size.width, size.height)
            lineTo(0f, size.height)
            close()
        }
        drawPath(fill, color.copy(alpha = 0.10f))
        drawPath(path, color, style = Stroke(width = 1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

@Composable
fun HeatmapView(w: Widget.Heatmap) {
    val p = P
    var sel by remember(w) { mutableStateOf<Pair<Int, Int>?>(null) }
    val flat = w.values.flatten().filterNotNull()
    val scaleMax = (if (w.format == "pct") flat.filter { it < 0.999 } else flat).maxOrNull()?.takeIf { it > 0 } ?: 1.0
    val measurer = rememberTextMeasurer()
    val labelW = if (w.y.maxOfOrNull { it.length } ?: 0 > 9) 96.dp else 34.dp
    Column {
        Box(Modifier.fillMaxWidth().heightIn(min = 28.dp), contentAlignment = Alignment.CenterStart) {
            val s = sel
            if (s == null) Text("Нажмите на ячейку", color = p.faint, fontSize = 11.sp)
            else Text(
                "${w.y.getOrElse(s.first) { "" }} · ${w.x.getOrElse(s.second) { "" }}: " +
                    formatValue(w.values.getOrNull(s.first)?.getOrNull(s.second), w.format),
                color = p.ink, fontSize = 12.sp, fontWeight = FontWeight.SemiBold
            )
        }
        val rows = w.y.size
        val cellH = if (rows > 8) 22.dp else 26.dp
        Canvas(
            Modifier.fillMaxWidth().height(cellH * rows + 16.dp).pointerInput(w) {
                detectTapGestures { o ->
                    val lw = labelW.toPx()
                    val cw = (size.width - lw) / w.x.size.coerceAtLeast(1)
                    val ch = cellH.toPx()
                    val r = ((o.y - 16.dp.toPx()) / ch).toInt()
                    val c = ((o.x - lw) / cw).toInt()
                    if (r in 0 until rows && c in w.x.indices) sel = if (sel == r to c) null else r to c
                }
            }
        ) {
            val lw = labelW.toPx()
            val top = 16.dp.toPx()
            val cw = (size.width - lw) / w.x.size.coerceAtLeast(1)
            val ch = cellH.toPx()
            val style = TextStyle(fontSize = 9.sp, color = p.muted)
            val every = max(1, (w.x.size + 11) / 12)
            w.x.forEachIndexed { c, lab ->
                if (c % every == 0) {
                    val t = measurer.measure(lab, style, maxLines = 1)
                    drawText(t, topLeft = Offset(lw + c * cw + cw / 2 - t.size.width / 2, 0f))
                }
            }
            w.y.forEachIndexed { r, lab ->
                val t = measurer.measure(lab, style.copy(fontSize = 10.sp), maxLines = 1,
                    overflow = TextOverflow.Ellipsis, constraints = androidx.compose.ui.unit.Constraints(maxWidth = (lw - 6).toInt().coerceAtLeast(1)))
                drawText(t, topLeft = Offset(0f, top + r * ch + ch / 2 - t.size.height / 2))
                w.values.getOrNull(r)?.forEachIndexed { c, v ->
                    val color = if (v == null) p.bg.copy(alpha = 0f)
                    else lerp(p.cardAlt, p.accent, (v / scaleMax).toFloat().coerceIn(0f, 1f).let { 0.08f + 0.92f * it })
                    drawRoundRect(color, Offset(lw + c * cw + 1f, top + r * ch + 1f), Size(cw - 2f, ch - 2f),
                        CornerRadius(4f, 4f))
                    if (sel == r to c) drawRoundRect(p.ink, Offset(lw + c * cw + 1f, top + r * ch + 1f),
                        Size(cw - 2f, ch - 2f), CornerRadius(4f, 4f), style = Stroke(2f))
                    if (v != null && cw > 19.dp.toPx() && w.format == "pct") {
                        val t = measurer.measure(pct(v).replace(",0%", "%"), TextStyle(fontSize = 7.5.sp,
                            color = if (v / scaleMax > 0.55) Color.White else p.ink), maxLines = 1)
                        drawText(t, topLeft = Offset(lw + c * cw + cw / 2 - t.size.width / 2, top + r * ch + ch / 2 - t.size.height / 2))
                    }
                }
            }
        }
    }
}

@Composable
fun FunnelView(w: Widget.Funnel) {
    val p = P
    val first = w.steps.firstOrNull()?.second?.takeIf { it > 0 } ?: 1.0
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        w.steps.forEachIndexed { i, (label, v) ->
            val prev = if (i > 0) w.steps[i - 1].second else null
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(label, color = p.ink, fontSize = 13.sp, modifier = Modifier.weight(1f))
                    Text(formatValue(v, "int"), color = p.ink, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                    if (prev != null && prev > 0 && v != null) {
                        Spacer(Modifier.width(8.dp))
                        Text(pct(v / prev), color = p.muted, fontSize = 11.sp, modifier = Modifier.width(52.dp),
                            textAlign = androidx.compose.ui.text.style.TextAlign.End)
                    } else Spacer(Modifier.width(60.dp))
                }
                Spacer(Modifier.height(4.dp))
                Box(Modifier.fillMaxWidth().height(10.dp).background(p.cardAlt, RoundedCornerShape(5.dp))) {
                    Box(
                        Modifier.fillMaxWidth(((v ?: 0.0) / first).toFloat().coerceIn(0.005f, 1f)).height(10.dp)
                            .background(p.seriesColor(i % 3), RoundedCornerShape(5.dp))
                    )
                }
            }
        }
        val last = w.steps.lastOrNull()?.second
        if (last != null) Text("Сквозная конверсия ${pct(last / first)}", color = p.muted, fontSize = 12.sp)
    }
}

@Composable
fun ShareView(w: Widget.Share) {
    val p = P
    var sel by remember(w) { mutableStateOf<Int?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Canvas(Modifier.fillMaxWidth().height(16.dp).pointerInput(w) {
            detectTapGestures { o ->
                var acc = 0f
                w.items.forEachIndexed { i, it ->
                    val wd = size.width * it.share.toFloat()
                    if (o.x >= acc && o.x <= acc + wd) sel = if (sel == i) null else i
                    acc += wd
                }
            }
        }) {
            var x = 0f
            val r = size.height / 2
            w.items.forEachIndexed { i, it ->
                val wd = size.width * it.share.toFloat()
                drawRoundRect(p.seriesColor(i).copy(alpha = if (sel == null || sel == i) 1f else .3f),
                    Offset(x, 0f), Size(max(wd - 2f, 1f), size.height), CornerRadius(r, r))
                x += wd
            }
        }
        w.items.forEachIndexed { i, it ->
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Box(Modifier.size(10.dp).background(p.seriesColor(i), RoundedCornerShape(3.dp)))
                Spacer(Modifier.width(8.dp))
                Text(it.label, color = if (sel == null || sel == i) p.ink else p.faint, fontSize = 13.sp,
                    modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(formatValue(it.value, w.format), color = p.ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                Text(pct(it.share), color = p.muted, fontSize = 12.sp, modifier = Modifier.width(58.dp),
                    textAlign = androidx.compose.ui.text.style.TextAlign.End)
            }
        }
    }
}
